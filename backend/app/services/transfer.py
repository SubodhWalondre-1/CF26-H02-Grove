"""
TransferService — Patient Transfer transaction coordination.

Implements the 3-leg atomic transfer workflow:
  • Pre-flight reverse readiness verification (source occupied by patient)
  • Sequenced hold: destination bed -> transport unit -> source bed release
  • Critical Rollback Invariant: source bed returns to IN_USE with patient re-attached
  • Commit: destination bed IN_USE, transport released, source enters CLEANING
  • Real-time WebSocket broadcasting & Audit logging
"""

import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Bed,
    BedAssignment,
    BedStatus,
    HoldState,
    Patient,
    RequestType,
    Resource,
    ResourceStatus,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
    User,
)
from app.models.transfer import PatientTransfer, TransferStatus, TransferType
from app.services.audit import create_audit_event
from app.services.bed import BedService
from app.services.transaction import generate_fingerprint

logger = logging.getLogger(__name__)


class PreflightValidationError(Exception):
    """Raised when source bed occupancy check or patient validation fails."""
    pass


class TransferDestinationUnavailableError(Exception):
    """Raised when destination bed is not in READY status."""
    pass


class TransferTransportUnavailableError(Exception):
    """Raised when requested transport resource cannot be held."""
    pass


class TransferService:

    def __init__(
        self,
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis] = None,
    ):
        self.db = db
        self.redis = redis_client

    # ─────────────────────────────────────────
    # 1. INITIATE TRANSFER
    # ─────────────────────────────────────────

    async def initiate_transfer(
        self,
        patient_id: str,
        source_bed_id: str,
        destination_bed_id: str,
        transport_resource_id: Optional[str] = None,
        transfer_type: str = "INTRA_FACILITY",
        reason: Optional[str] = None,
        initiated_by: str = "SYSTEM",
        ttl_seconds: int = 300,
    ) -> Dict[str, Any]:
        """
        Initiates a patient transfer transaction.
        1. Pre-flight: validates source is IN_USE by patient, destination is READY.
        2. Acquires destination bed hold (TENTATIVE_HOLD).
        3. Acquires transport hold if requested.
        4. Releases source bed to POST_USE (detaches patient).
        5. Persists Transaction + PatientTransfer.
        """
        now_utc = datetime.now(timezone.utc)

        # ── Step 1: Pre-flight Validations ──
        if source_bed_id == destination_bed_id:
            raise PreflightValidationError("Source and destination beds cannot be the same")

        # Validate Patient
        patient = await self.db.get(Patient, patient_id)
        if not patient:
            raise PreflightValidationError(f"Patient {patient_id} not found")

        # Validate Source Bed Occupancy (Reverse Readiness)
        source_stmt = select(Bed).where(Bed.id == source_bed_id).with_for_update()
        source_res = await self.db.execute(source_stmt)
        source_bed = source_res.scalar_one_or_none()

        if not source_bed:
            raise PreflightValidationError(f"Source bed {source_bed_id} not found")

        if source_bed.status != BedStatus.IN_USE:
            raise PreflightValidationError(
                f"Source bed {source_bed.bed_number} ({source_bed_id}) is not occupied (current status: {source_bed.status.value})"
            )

        if source_bed.current_patient_id != patient_id:
            raise PreflightValidationError(
                f"Source bed {source_bed.bed_number} is occupied by patient '{source_bed.current_patient_id}', not '{patient_id}'"
            )

        # Validate Destination Bed
        dest_stmt = select(Bed).where(Bed.id == destination_bed_id).with_for_update()
        dest_res = await self.db.execute(dest_stmt)
        dest_bed = dest_res.scalar_one_or_none()

        if not dest_bed:
            raise TransferDestinationUnavailableError(f"Destination bed {destination_bed_id} not found")

        if dest_bed.status != BedStatus.READY:
            raise TransferDestinationUnavailableError(
                f"Destination bed {dest_bed.bed_number} is in '{dest_bed.status.value}' status, expected READY"
            )

        # ── Step 2: Create Transaction ──
        tx_id = f"TX-{secrets.token_hex(2)}"
        resource_ids = [source_bed_id, destination_bed_id]
        if transport_resource_id:
            resource_ids.append(transport_resource_id)

        fingerprint = generate_fingerprint(
            patient_id=patient_id,
            resource_ids=resource_ids,
        )

        ttl_expires = now_utc + timedelta(seconds=ttl_seconds)

        tx = Transaction(
            tx_id=tx_id,
            request_type=RequestType.patient_transfer,
            patient_id=patient_id,
            requested_by=initiated_by,
            state=TxState.PREPARING,
            request_fingerprint=fingerprint,
            hold_ttl_seconds=ttl_seconds,
            hold_expires_at=ttl_expires,
            created_at=now_utc,
            updated_at=now_utc,
        )
        self.db.add(tx)

        history = TransactionStateHistory(
            tx_id=tx_id,
            state=TxState.PREPARING,
            occurred_at=now_utc,
        )
        self.db.add(history)

        # ── Step 3: Sequenced Resource Holds ──
        # Leg A: Destination Bed Hold
        bed_service = BedService(self.db, self.redis)
        try:
            # Move destination to TENTATIVE_HOLD
            dest_bed.status = BedStatus.TENTATIVE_HOLD
            dest_bed.updated_at = now_utc
            if self.redis:
                try:
                    await self.redis.set(
                        f"bed_hold:{destination_bed_id}",
                        json.dumps({"bed_id": destination_bed_id, "transaction_id": tx_id}),
                        ex=ttl_seconds,
                    )
                except Exception:
                    pass
        except Exception as e:
            tx.state = TxState.ABORTED
            raise TransferDestinationUnavailableError(f"Failed to hold destination bed: {e}")

        # Leg B: Transport Resource Hold (if requested)
        transport_held = False
        if transport_resource_id:
            trans_stmt = (
                select(Resource)
                .where(Resource.resource_id == transport_resource_id)
                .with_for_update()
            )
            trans_res = await self.db.execute(trans_stmt)
            transport_res = trans_res.scalar_one_or_none()

            if not transport_res or transport_res.status != ResourceStatus.available:
                # Rollback destination bed hold
                dest_bed.status = BedStatus.READY
                tx.state = TxState.ABORTED
                raise TransferTransportUnavailableError(
                    f"Transport resource {transport_resource_id} is unavailable"
                )

            transport_res.status = ResourceStatus.tentative
            transport_res.held_by_tx = tx_id
            transport_res.updated_at = now_utc
            transport_held = True

        # ── Step 4: Release Source Bed to POST_USE ──
        source_bed.status = BedStatus.POST_USE
        source_bed.current_patient_id = None
        source_bed.current_transaction_id = tx_id
        source_bed.updated_at = now_utc

        # ── Step 5: Persist PatientTransfer Record ──
        transfer_id = uuid.uuid4()
        initial_status = (
            TransferStatus.TRANSPORT_ASSIGNED.value
            if transport_held
            else TransferStatus.DESTINATION_HELD.value
        )

        transfer = PatientTransfer(
            id=transfer_id,
            tx_id=tx_id,
            patient_id=patient_id,
            source_bed_id=source_bed_id,
            destination_bed_id=destination_bed_id,
            transport_resource_id=transport_resource_id,
            transfer_type=transfer_type,
            reason=reason,
            status=initial_status,
            hold_ttl_expires_at=ttl_expires,
            initiated_by=initiated_by,
            initiated_at=now_utc,
            updated_at=now_utc,
        )
        self.db.add(transfer)

        # Record TransactionResource rows
        tr_dest = TransactionResource(
            tx_id=tx_id,
            resource_id=destination_bed_id,
            hold_state=HoldState.tentative,
            updated_at=now_utc,
        )
        self.db.add(tr_dest)

        if transport_resource_id:
            tr_trans = TransactionResource(
                tx_id=tx_id,
                resource_id=transport_resource_id,
                hold_state=HoldState.tentative,
                updated_at=now_utc,
            )
            self.db.add(tr_trans)

        await self.db.flush()

        # Audit
        await create_audit_event(
            db=self.db,
            event_type="TRANSFER_INITIATED",
            tx_id=tx_id,
            detail={
                "transfer_id": str(transfer_id),
                "patient_id": patient_id,
                "source_bed": source_bed.bed_number,
                "destination_bed": dest_bed.bed_number,
                "transport_resource": transport_resource_id,
                "transfer_type": transfer_type,
                "reason": reason,
                "hold_ttl_seconds": ttl_seconds,
            },
        )

        await self._publish_transfer_event(transfer, "TRANSFER_INITIATED")

        return {
            "transfer_id": str(transfer_id),
            "tx_id": tx_id,
            "patient_id": patient_id,
            "source_bed_id": source_bed_id,
            "source_bed_number": source_bed.bed_number,
            "destination_bed_id": destination_bed_id,
            "destination_bed_number": dest_bed.bed_number,
            "transport_resource_id": transport_resource_id,
            "status": initial_status,
            "transfer_type": transfer_type,
            "hold_ttl_expires_at": ttl_expires.isoformat(),
            "reason": reason,
        }

    # ─────────────────────────────────────────
    # 2. CONFIRM TRANSPORT (In-Transit)
    # ─────────────────────────────────────────

    async def confirm_transport(self, tx_id: str) -> Dict[str, Any]:
        """
        Marks patient as in-transit (moving between wards).
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(PatientTransfer)
            .where(PatientTransfer.tx_id == tx_id)
            .with_for_update()
        )
        res = await self.db.execute(stmt)
        transfer = res.scalar_one_or_none()

        if not transfer:
            raise ValueError(f"Transfer for TX {tx_id} not found")

        if transfer.status not in [
            TransferStatus.INITIATED.value,
            TransferStatus.DESTINATION_HELD.value,
            TransferStatus.TRANSPORT_ASSIGNED.value,
            TransferStatus.SOURCE_RELEASE_PENDING.value,
        ]:
            raise ValueError(f"Cannot mark in-transit from current state '{transfer.status}'")

        transfer.status = TransferStatus.IN_TRANSIT.value
        transfer.updated_at = now_utc

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="TRANSFER_IN_TRANSIT",
            tx_id=tx_id,
            detail={"transfer_id": str(transfer.id), "in_transit_at": now_utc.isoformat()},
        )

        await self._publish_transfer_event(transfer, "TRANSFER_IN_TRANSIT")

        return {
            "transfer_id": str(transfer.id),
            "tx_id": tx_id,
            "status": TransferStatus.IN_TRANSIT.value,
        }

    # ─────────────────────────────────────────
    # 3. COMMIT TRANSFER (Physical Arrival)
    # ─────────────────────────────────────────

    async def commit_transfer(self, tx_id: str) -> Dict[str, Any]:
        """
        Finalizes transfer:
          - Destination bed: TENTATIVE_HOLD -> IN_USE (patient attached)
          - Transport (if any): released back to available
          - Source bed: triggers cleaning workflow (POST_USE -> CLEANING)
          - Transfer: COMMITTED
        """
        now_utc = datetime.now(timezone.utc)

        stmt = (
            select(PatientTransfer)
            .where(PatientTransfer.tx_id == tx_id)
            .with_for_update()
        )
        res = await self.db.execute(stmt)
        transfer = res.scalar_one_or_none()

        if not transfer:
            raise ValueError(f"Transfer for TX {tx_id} not found")

        if transfer.status in [TransferStatus.COMMITTED.value, TransferStatus.ROLLED_BACK.value, TransferStatus.FAILED.value]:
            raise ValueError(f"Transfer is already in terminal state '{transfer.status}'")

        # 1. Destination Bed: Assign patient & mark IN_USE
        dest_stmt = select(Bed).where(Bed.id == transfer.destination_bed_id).with_for_update()
        dest_res = await self.db.execute(dest_stmt)
        dest_bed = dest_res.scalar_one()

        dest_bed.status = BedStatus.IN_USE
        dest_bed.current_patient_id = transfer.patient_id
        dest_bed.current_transaction_id = tx_id
        dest_bed.updated_at = now_utc

        # Record BedAssignment for destination
        assignment = BedAssignment(
            bed_id=transfer.destination_bed_id,
            patient_id=transfer.patient_id,
            transaction_id=tx_id,
            assigned_by=transfer.initiated_by,
        )
        self.db.add(assignment)

        # 2. Release Transport Resource if held
        if transfer.transport_resource_id:
            trans_stmt = (
                select(Resource)
                .where(Resource.resource_id == transfer.transport_resource_id)
                .with_for_update()
            )
            trans_res = await self.db.execute(trans_stmt)
            transport_res = trans_res.scalar_one_or_none()
            if transport_res:
                transport_res.status = ResourceStatus.available
                transport_res.held_by_tx = None
                transport_res.updated_at = now_utc

        # 3. Source Bed: Trigger cleaning lifecycle
        source_stmt = select(Bed).where(Bed.id == transfer.source_bed_id).with_for_update()
        source_res = await self.db.execute(source_stmt)
        source_bed = source_res.scalar_one_or_none()

        if source_bed:
            # Transition to CLEANING
            source_bed.status = BedStatus.CLEANING
            source_bed.last_cleaned_at = now_utc
            clean_min = 20
            if hasattr(source_bed, "bed_type") and source_bed.bed_type:
                bt_str = source_bed.bed_type.value if hasattr(source_bed.bed_type, "value") else str(source_bed.bed_type)
                if bt_str == "ICU":
                    clean_min = 30
            source_bed.estimated_ready_at = now_utc + timedelta(minutes=clean_min)
            source_bed.updated_at = now_utc

        # 4. Update Transaction
        tx = await self.db.get(Transaction, tx_id)
        if tx:
            tx.state = TxState.COMMITTED
            tx.closed_at = now_utc
            tx.updated_at = now_utc
            h_comm = TransactionStateHistory(
                tx_id=tx_id,
                state=TxState.COMMITTED,
                occurred_at=now_utc,
            )
            self.db.add(h_comm)

        # 5. Update PatientTransfer
        transfer.status = TransferStatus.COMMITTED.value
        transfer.committed_at = now_utc
        transfer.updated_at = now_utc

        # Update TransactionResources to held/released
        tr_stmt = select(TransactionResource).where(TransactionResource.tx_id == tx_id)
        tr_res = await self.db.execute(tr_stmt)
        for tr in tr_res.scalars().all():
            tr.hold_state = HoldState.held
            tr.updated_at = now_utc

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="TRANSFER_COMMITTED",
            tx_id=tx_id,
            detail={
                "transfer_id": str(transfer.id),
                "patient_id": transfer.patient_id,
                "source_bed": source_bed.bed_number if source_bed else transfer.source_bed_id,
                "destination_bed": dest_bed.bed_number,
                "committed_at": now_utc.isoformat(),
            },
        )

        await self._publish_transfer_event(transfer, "TRANSFER_COMMITTED")

        return {
            "transfer_id": str(transfer.id),
            "tx_id": tx_id,
            "status": TransferStatus.COMMITTED.value,
            "destination_bed_status": dest_bed.status.value,
            "source_bed_status": source_bed.status.value if source_bed else "CLEANING",
        }

    # ─────────────────────────────────────────
    # 4. ROLLBACK TRANSFER (Restores Source IN_USE)
    # ─────────────────────────────────────────

    async def rollback_transfer(
        self,
        tx_id: str,
        reason: str = "MANUAL_CANCEL",
    ) -> Dict[str, Any]:
        """
        Critical Rollback Path:
          - Destination bed: TENTATIVE_HOLD -> READY
          - Transport (if held): released to available
          - CRITICAL INVARIANT: Source bed restored to IN_USE with patient re-attached!
          - Transfer: ROLLED_BACK
        """
        now_utc = datetime.now(timezone.utc)

        stmt = (
            select(PatientTransfer)
            .where(PatientTransfer.tx_id == tx_id)
            .with_for_update()
        )
        res = await self.db.execute(stmt)
        transfer = res.scalar_one_or_none()

        if not transfer:
            raise ValueError(f"Transfer for TX {tx_id} not found")

        if transfer.status in [TransferStatus.COMMITTED.value, TransferStatus.ROLLED_BACK.value]:
            return {
                "transfer_id": str(transfer.id),
                "tx_id": tx_id,
                "status": transfer.status,
                "message": "Already finalized",
            }

        # 1. Release Destination Bed
        dest_stmt = select(Bed).where(Bed.id == transfer.destination_bed_id).with_for_update()
        dest_res = await self.db.execute(dest_stmt)
        dest_bed = dest_res.scalar_one_or_none()
        if dest_bed and dest_bed.status == BedStatus.TENTATIVE_HOLD:
            dest_bed.status = BedStatus.READY
            dest_bed.updated_at = now_utc
            if self.redis:
                try:
                    await self.redis.delete(f"bed_hold:{transfer.destination_bed_id}")
                except Exception:
                    pass

        # 2. Release Transport Resource if held
        if transfer.transport_resource_id:
            trans_stmt = (
                select(Resource)
                .where(Resource.resource_id == transfer.transport_resource_id)
                .with_for_update()
            )
            trans_res = await self.db.execute(trans_stmt)
            transport_res = trans_res.scalar_one_or_none()
            if transport_res:
                transport_res.status = ResourceStatus.available
                transport_res.held_by_tx = None
                transport_res.updated_at = now_utc

        # 3. CRITICAL: Restore Source Bed to IN_USE with Patient
        source_stmt = select(Bed).where(Bed.id == transfer.source_bed_id).with_for_update()
        source_res = await self.db.execute(source_stmt)
        source_bed = source_res.scalar_one_or_none()

        if source_bed:
            source_bed.status = BedStatus.IN_USE
            source_bed.current_patient_id = transfer.patient_id
            source_bed.current_transaction_id = None
            source_bed.updated_at = now_utc

        # 4. Update Transaction
        tx = await self.db.get(Transaction, tx_id)
        if tx:
            tx.state = TxState.ABORTED
            tx.closed_at = now_utc
            tx.updated_at = now_utc
            h_abort = TransactionStateHistory(
                tx_id=tx_id,
                state=TxState.ABORTED,
                occurred_at=now_utc,
            )
            self.db.add(h_abort)

        # 5. Update PatientTransfer
        transfer.status = TransferStatus.ROLLED_BACK.value
        transfer.failed_reason = reason
        transfer.updated_at = now_utc

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="TRANSFER_ROLLED_BACK",
            tx_id=tx_id,
            decision="ROLLBACK",
            detail={
                "transfer_id": str(transfer.id),
                "patient_id": transfer.patient_id,
                "reason": reason,
                "source_bed_restored": source_bed.bed_number if source_bed else transfer.source_bed_id,
            },
        )

        await self._publish_transfer_event(transfer, "TRANSFER_ROLLED_BACK")

        return {
            "transfer_id": str(transfer.id),
            "tx_id": tx_id,
            "status": TransferStatus.ROLLED_BACK.value,
            "reason": reason,
            "source_bed_status": source_bed.status.value if source_bed else "IN_USE",
        }

    # ─────────────────────────────────────────
    # 5. QUERY OPERATIONS
    # ─────────────────────────────────────────

    async def get_transfer_by_tx(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns full transfer detail with source/dest bed metadata.
        """
        stmt = (
            select(PatientTransfer)
            .where(PatientTransfer.tx_id == tx_id)
        )
        res = await self.db.execute(stmt)
        t = res.scalar_one_or_none()
        if not t:
            return None

        # Fetch beds
        s_bed = await self.db.get(Bed, t.source_bed_id)
        d_bed = await self.db.get(Bed, t.destination_bed_id)

        return {
            "transfer_id": str(t.id),
            "tx_id": t.tx_id,
            "patient_id": t.patient_id,
            "source_bed_id": t.source_bed_id,
            "source_bed_number": s_bed.bed_number if s_bed else t.source_bed_id,
            "destination_bed_id": t.destination_bed_id,
            "destination_bed_number": d_bed.bed_number if d_bed else t.destination_bed_id,
            "transport_resource_id": t.transport_resource_id,
            "transfer_type": t.transfer_type,
            "reason": t.reason,
            "status": t.status,
            "hold_ttl_expires_at": t.hold_ttl_expires_at.isoformat(),
            "initiated_by": t.initiated_by,
            "initiated_at": t.initiated_at.isoformat() if t.initiated_at else None,
            "committed_at": t.committed_at.isoformat() if t.committed_at else None,
            "failed_reason": t.failed_reason,
        }

    async def get_active_transfers(self) -> List[Dict[str, Any]]:
        """
        Returns in-flight transfers for dashboard progress widget.
        """
        stmt = (
            select(PatientTransfer)
            .where(
                PatientTransfer.status.in_([
                    TransferStatus.INITIATED.value,
                    TransferStatus.DESTINATION_HELD.value,
                    TransferStatus.TRANSPORT_ASSIGNED.value,
                    TransferStatus.SOURCE_RELEASE_PENDING.value,
                    TransferStatus.IN_TRANSIT.value,
                ])
            )
            .order_by(PatientTransfer.initiated_at.desc())
        )
        res = await self.db.execute(stmt)
        transfers = list(res.scalars().all())

        items = []
        for t in transfers:
            s_bed = await self.db.get(Bed, t.source_bed_id)
            d_bed = await self.db.get(Bed, t.destination_bed_id)
            items.append({
                "transfer_id": str(t.id),
                "tx_id": t.tx_id,
                "patient_id": t.patient_id,
                "source_bed_id": t.source_bed_id,
                "source_bed_number": s_bed.bed_number if s_bed else t.source_bed_id,
                "destination_bed_id": t.destination_bed_id,
                "destination_bed_number": d_bed.bed_number if d_bed else t.destination_bed_id,
                "transport_resource_id": t.transport_resource_id,
                "transfer_type": t.transfer_type,
                "reason": t.reason,
                "status": t.status,
                "hold_ttl_expires_at": t.hold_ttl_expires_at.isoformat(),
                "initiated_by": t.initiated_by,
                "initiated_at": t.initiated_at.isoformat() if t.initiated_at else None,
            })
        return items

    async def get_patient_transfer_history(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Returns historical transfers for a patient (feeds Bed Movement History).
        """
        stmt = (
            select(PatientTransfer)
            .where(PatientTransfer.patient_id == patient_id)
            .order_by(PatientTransfer.initiated_at.desc())
        )
        res = await self.db.execute(stmt)
        transfers = list(res.scalars().all())

        items = []
        for t in transfers:
            s_bed = await self.db.get(Bed, t.source_bed_id)
            d_bed = await self.db.get(Bed, t.destination_bed_id)
            items.append({
                "transfer_id": str(t.id),
                "tx_id": t.tx_id,
                "source_bed_number": s_bed.bed_number if s_bed else t.source_bed_id,
                "destination_bed_number": d_bed.bed_number if d_bed else t.destination_bed_id,
                "transport_resource_id": t.transport_resource_id,
                "transfer_type": t.transfer_type,
                "reason": t.reason,
                "status": t.status,
                "initiated_by": t.initiated_by,
                "initiated_at": t.initiated_at.isoformat() if t.initiated_at else None,
                "committed_at": t.committed_at.isoformat() if t.committed_at else None,
                "failed_reason": t.failed_reason,
            })
        return items

    # ─────────────────────────────────────────
    # 6. PERIODIC SWEEPS
    # ─────────────────────────────────────────

    async def sweep_expired_transfers(self) -> int:
        """
        Auto-rollbacks transfers where hold_ttl_expires_at has elapsed.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(PatientTransfer)
            .where(
                PatientTransfer.status.in_([
                    TransferStatus.INITIATED.value,
                    TransferStatus.DESTINATION_HELD.value,
                    TransferStatus.TRANSPORT_ASSIGNED.value,
                    TransferStatus.SOURCE_RELEASE_PENDING.value,
                    TransferStatus.IN_TRANSIT.value,
                ]),
                PatientTransfer.hold_ttl_expires_at < now_utc,
            )
            .with_for_update()
        )
        res = await self.db.execute(stmt)
        expired = list(res.scalars().all())

        count = 0
        for t in expired:
            await self.rollback_transfer(t.tx_id, reason="TTL_EXPIRED")
            count += 1

        if count:
            await self.db.flush()
            logger.info(f"Transfer TTL sweep: {count} transfer(s) rolled back")

        return count

    # ─────────────────────────────────────────
    # REALTIME PUBLISHING
    # ─────────────────────────────────────────

    async def _publish_transfer_event(
        self,
        transfer: PatientTransfer,
        event_type: str,
    ) -> None:
        if not self.redis:
            return

        payload = {
            "event": "PATIENT_TRANSFER_UPDATE",
            "event_type": event_type,
            "transfer_id": str(transfer.id),
            "tx_id": transfer.tx_id,
            "patient_id": transfer.patient_id,
            "source_bed_id": transfer.source_bed_id,
            "destination_bed_id": transfer.destination_bed_id,
            "status": transfer.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            msg = json.dumps(payload, default=str)
            await self.redis.publish("transfer_updates", msg)
            await self.redis.publish("pubsub:dashboard", msg)
        except Exception as e:
            logger.warning(f"Failed to publish transfer event: {e}")
