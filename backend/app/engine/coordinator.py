from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException, status
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import publish_event
from app.engine.arbiter import detect_and_arbitrate
from app.engine.compensation import initiate_compensation
from app.engine.locking import attempt_single_resource_lock, release_single_resource
from app.engine.two_phase_commit import commit_bundle, prepare_bundle, rollback_bundle
from app.models.models import (
    HoldState,
    RequestType,
    Resource,
    ResourceStatus,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
    User,
    UserRole,
)
from app.services.audit import create_audit_event
from app.services.bed import BedService
from app.services.pharmacy import PharmacyService, PHARMACY_RESOURCE_TYPES
from app.services.diagnostics_scheduling import DiagnosticsSchedulingService, DIAGNOSTIC_RESOURCE_TYPES
from app.services.lab_queue import LabQueueService

logger = get_logger(__name__)

BED_RESOURCE_TYPES = {"BED_ICU", "BED_GENERAL", "BED_STEP_DOWN", "BED_EMERGENCY"}
LAB_RESOURCE_TYPES = {"LAB_SLOT"}


VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "CREATED": {"QUEUED"},
    "QUEUED": {"ARBITRATING", "PREPARING"},  # PREPARING if no conflict
    "ARBITRATING": {"PREPARING", "ABORTED"},  # ABORTED if lost arbitration
    "NO_CONFLICT": {"PREPARING"},
    "PREPARING": {"COMMITTING", "ROLLINGBACK"},
    "COMMITTING": {"COMMITTED", "ROLLINGBACK"},
    "ROLLINGBACK": {"ABORTED"},
    "COMMITTED": {"ACTIVE"},
    "ACTIVE": {"COMPLETED", "CANCELLED"},
    "ABORTED": {"CLOSED"},
    "COMPLETED": {"CLOSED"},
    "CANCELLED": {"COMPENSATING", "CLOSED"},
    "COMPENSATING": {"RELEASED"},
    "RELEASED": {"CLOSED"},
    "CLOSED": set(),  # terminal
}

TERMINAL_STATES: Set[str] = {"CLOSED", "ABORTED"}


def _state_to_str(state: Any) -> str:
    if hasattr(state, "value"):
        return str(state.value)
    return str(state)


def is_valid_transition(from_state: Any, to_state: Any) -> bool:
    """
    Validates whether a transaction can transition from from_state to to_state.
    Supports both TxState enum instances and plain strings.
    """
    from_s = _state_to_str(from_state)
    to_s = _state_to_str(to_state)

    if from_s == to_s:
        return False

    allowed = VALID_TRANSITIONS.get(from_s, set())
    return to_s in allowed


def is_terminal_state(state: Any) -> bool:
    """
    Checks if a state is terminal in the transaction lifecycle.
    Supports both TxState enum instances and plain strings.
    """
    state_s = _state_to_str(state)
    return state_s in TERMINAL_STATES


async def process_transaction(db: AsyncSession, tx_id: str) -> None:
    """
    Main state machine orchestrator for clinical resource transactions.
    Routes transactions synchronously based on request_type (single_resource vs care_bundle).
    """
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    state_str = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
    if state_str != "QUEUED":
        logger.info(
            f"Transaction {tx_id} already in state {state_str}, skipping coordinator processing",
            extra={"tx_id": tx_id, "state": state_str},
        )
        return

    req_type_str = (
        tx.request_type.value
        if hasattr(tx.request_type, "value")
        else str(tx.request_type)
    )

    if req_type_str == "single_resource":
        await _process_single_resource(db, tx)
    elif req_type_str == "care_bundle":
        await _process_bundle(db, tx)
    elif req_type_str in ["patient_transfer", "PATIENT_TRANSFER"]:
        logger.info(f"Transaction {tx_id} is a patient_transfer, managed via TransferService")


async def _process_single_resource(db: AsyncSession, tx: Transaction) -> None:
    """
    Executes the single-resource acquisition path (Rule 1: row-level lock only, no 2PC).
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Load target resource_id
    tr_stmt = select(TransactionResource).where(
        TransactionResource.tx_id == tx.tx_id
    )
    tr_result = await db.execute(tr_stmt)
    tr = tr_result.scalar_one_or_none()

    if not tr:
        logger.error(
            f"No resource associated with single_resource TX {tx.tx_id}",
            extra={"tx_id": tx.tx_id},
        )
        return

    resource_id = tr.resource_id

    # 2. Attempt lock
    resource = await attempt_single_resource_lock(db, tx.tx_id, resource_id)

    # 3a. SUCCESS PATH
    if resource is not None:
        # NO_CONFLICT -> COMMITTING -> COMMITTED -> ACTIVE
        for target_state in (
            TxState.NO_CONFLICT,
            TxState.COMMITTING,
            TxState.COMMITTED,
            TxState.ACTIVE,
        ):
            tx.state = target_state
            tx.updated_at = now_utc
            h = TransactionStateHistory(
                tx_id=tx.tx_id,
                state=target_state,
                occurred_at=now_utc,
            )
            db.add(h)

        await create_audit_event(
            db=db,
            event_type="SINGLE_RESOURCE_LOCKED",
            tx_id=tx.tx_id,
            resource_id=resource_id,
            decision="COMMIT",
        )
        await publish_event(
            "pubsub:dashboard",
            {
                "event": "TRANSACTION_UPDATED",
                "tx_id": tx.tx_id,
                "status": "ACTIVE",
                "timestamp": now_utc.isoformat(),
            },
        )
        await db.commit()

        logger.info(
            f"Single-resource TX {tx.tx_id} activated successfully on {resource_id}",
            extra={"tx_id": tx.tx_id, "resource_id": resource_id},
        )

    # 3b. CONFLICT / ESCALATION PATH
    else:
        # Check if Emergency Override (Acuity >= 9.5) hits a held resource
        patient = await get_patient_acuity(db=db, patient_id=tx.patient_id)
        if float(patient.base_acuity) >= 9.5:
            logger.info(
                f"Emergency Override TX {tx.tx_id} (acuity {patient.base_acuity}) hit held resource {resource_id}, routing to Escalation Arbiter",
                extra={"tx_id": tx.tx_id, "resource_id": resource_id},
            )
            from app.engine.escalation import request_escalation
            esc_result = await request_escalation(
                db=db,
                escalating_tx_id=tx.tx_id,
                target_resource_id=resource_id,
                requested_by=tx.requested_by,
                source_feature="EMERGENCY_OVERRIDE_ROUTED",
            )
            if esc_result.get("decision") == "APPROVED":
                for target_state in (
                    TxState.NO_CONFLICT,
                    TxState.COMMITTING,
                    TxState.COMMITTED,
                    TxState.ACTIVE,
                ):
                    tx.state = target_state
                    tx.updated_at = now_utc
                    h = TransactionStateHistory(
                        tx_id=tx.tx_id,
                        state=target_state,
                        occurred_at=now_utc,
                    )
                    db.add(h)
                await create_audit_event(
                    db=db,
                    event_type="SINGLE_RESOURCE_LOCKED",
                    tx_id=tx.tx_id,
                    resource_id=resource_id,
                    decision="COMMIT",
                )
                await publish_event(
                    "pubsub:dashboard",
                    {
                        "event": "TRANSACTION_UPDATED",
                        "tx_id": tx.tx_id,
                        "status": "ACTIVE",
                        "timestamp": now_utc.isoformat(),
                    },
                )
                await db.commit()
                return

        logger.info(
            f"Single-resource lock failed on {resource_id}, routing TX {tx.tx_id} to arbiter",
            extra={"tx_id": tx.tx_id, "resource_id": resource_id},
        )
        winner_tx, conflict_id = await detect_and_arbitrate(
            db=db,
            incoming_tx=tx,
            contested_resource_id=resource_id,
        )

        if winner_tx.tx_id == tx.tx_id:
            # We won: retry lock acquisition
            retry_res = await attempt_single_resource_lock(
                db, tx.tx_id, resource_id
            )
            if retry_res is not None:
                for target_state in (
                    TxState.NO_CONFLICT,
                    TxState.COMMITTING,
                    TxState.COMMITTED,
                    TxState.ACTIVE,
                ):
                    tx.state = target_state
                    tx.updated_at = now_utc
                    h = TransactionStateHistory(
                        tx_id=tx.tx_id,
                        state=target_state,
                        occurred_at=now_utc,
                    )
                    db.add(h)

                await create_audit_event(
                    db=db,
                    event_type="SINGLE_RESOURCE_LOCKED",
                    tx_id=tx.tx_id,
                    resource_id=resource_id,
                    decision="COMMIT",
                )
                await publish_event(
                    "pubsub:dashboard",
                    {
                        "event": "TRANSACTION_UPDATED",
                        "tx_id": tx.tx_id,
                        "status": "ACTIVE",
                        "timestamp": now_utc.isoformat(),
                    },
                )
                await db.commit()
            else:
                # Race occurred: re-queue for client retry
                tx.state = TxState.QUEUED
                tx.updated_at = now_utc
                h_retry_queued = TransactionStateHistory(
                    tx_id=tx.tx_id,
                    state=TxState.QUEUED,
                    occurred_at=now_utc,
                )
                db.add(h_retry_queued)
                await db.commit()


async def _process_bundle(db: AsyncSession, tx: Transaction) -> None:
    """
    Executes the care bundle acquisition path (Rule 1: Two-Phase Commit protocol only).
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Conflict Check: Check primary (first) resource
    tr_stmt = (
        select(TransactionResource)
        .where(TransactionResource.tx_id == tx.tx_id)
        .order_by(TransactionResource.resource_id)
    )
    tr_result = await db.execute(tr_stmt)
    tr_rows = list(tr_result.scalars().all())

    if tr_rows:
        primary_tr = tr_rows[0]
        res = await db.get(Resource, primary_tr.resource_id)
        res_status = (
            res.status.value
            if res and hasattr(res.status, "value")
            else str(res.status if res else "")
        )

        if res and res_status != "available":
            contested = res.resource_id
            winner_tx, conflict_id = await detect_and_arbitrate(
                db=db,
                incoming_tx=tx,
                contested_resource_id=contested,
            )
            if winner_tx.tx_id != tx.tx_id:
                # We lost arbitration: transaction re-queued inside detect_and_arbitrate
                return

    # 2. Write NO_CONFLICT
    tx.state = TxState.NO_CONFLICT
    tx.updated_at = now_utc
    h_no_conflict = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.NO_CONFLICT,
        occurred_at=now_utc,
    )
    db.add(h_no_conflict)
    await db.flush()

    # 3. 2PC Prepare Phase
    all_held, held_ids, failed_ids = await prepare_bundle(db, tx)

    # 4a. 2PC Commit
    if all_held:
        await commit_bundle(db, tx, held_ids)
        await db.commit()
        logger.info(
            f"Care bundle TX {tx.tx_id} committed successfully",
            extra={"tx_id": tx.tx_id, "resources_locked": held_ids},
        )
    # 4b. 2PC Rollback
    else:
        failed_res = failed_ids[0] if failed_ids else "unknown"
        reason = f"Prepare failed: {failed_res} unavailable"
        await rollback_bundle(db, tx, held_ids, reason)
        await db.commit()
        logger.warning(
            f"Care bundle TX {tx.tx_id} rolled back. Reason: {reason}",
            extra={"tx_id": tx.tx_id, "reason": reason, "released": held_ids},
        )


async def cancel_transaction(
    db: AsyncSession,
    tx_id: str,
    requesting_user_id: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Cancels an active or in-flight transaction, triggering dependency-aware cascade compensation if ACTIVE.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Load TX with FOR UPDATE row lock
    stmt = select(Transaction).where(Transaction.tx_id == tx_id).with_for_update()
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    # 2. Authorization
    if requesting_user_id != tx.requested_by:
        user = await db.get(User, requesting_user_id)
        user_role = (
            user.role.value if user and hasattr(user.role, "value") else str(user.role if user else "")
        )
        if not user or user_role not in ("admin", "system"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="not_authorized",
            )

    # 3. Check cancellable states
    state_str = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
    cancellable_states = {"QUEUED", "ACTIVE", "PREPARING", "NO_CONFLICT"}

    if state_str not in cancellable_states:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transaction {tx_id} is in state {state_str} and cannot be cancelled.",
        )

    prev_state = state_str

    # 4. Transition to CANCELLED
    tx.state = TxState.CANCELLED
    tx.updated_at = now_utc
    h_cancel = TransactionStateHistory(
        tx_id=tx_id,
        state=TxState.CANCELLED,
        occurred_at=now_utc,
    )
    db.add(h_cancel)

    await create_audit_event(
        db=db,
        event_type="TRANSACTION_CANCELLED",
        tx_id=tx_id,
        detail={"reason": reason, "cancelled_by": requesting_user_id},
    )

    # 5. Compensation Decision
    if prev_state == "ACTIVE":
        await initiate_compensation(db, tx)
        compensation = "TRIGGERED"
    else:
        if prev_state == "PREPARING":
            tr_stmt = select(TransactionResource).where(
                TransactionResource.tx_id == tx_id,
                TransactionResource.hold_state.in_([HoldState.tentative, "tentative"]),
            )
            tr_res = await db.execute(tr_stmt)
            held_ids = [r.resource_id for r in tr_res.scalars().all()]
            await rollback_bundle(
                db, tx, held_ids, reason="CANCELLED_DURING_PREPARE"
            )
        compensation = "NOT_REQUIRED"
        await db.commit()

    # 7. Publish
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "TRANSACTION_UPDATED",
            "tx_id": tx_id,
            "status": "CANCELLED",
            "timestamp": now_utc.isoformat(),
        },
    )

    return {
        "tx_id": tx_id,
        "status": "CANCELLED",
        "compensation": compensation,
    }


async def complete_transaction(
    db: AsyncSession,
    tx_id: str,
    requesting_user_id: str,
) -> Dict[str, Any]:
    """
    Marks an ACTIVE transaction as COMPLETED, releasing all held resources normally.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Load TX with FOR UPDATE row lock
    stmt = select(Transaction).where(Transaction.tx_id == tx_id).with_for_update()
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    # 2. Authorization
    if requesting_user_id != tx.requested_by:
        user = await db.get(User, requesting_user_id)
        user_role = (
            user.role.value if user and hasattr(user.role, "value") else str(user.role if user else "")
        )
        if not user or user_role not in ("admin", "system"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="not_authorized",
            )

    # 3. State verification
    state_str = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
    if state_str != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transaction {tx_id} is in state {state_str}.",
        )

    # 4. Collect held resource_ids
    tr_stmt = select(TransactionResource).where(
        TransactionResource.tx_id == tx_id,
        TransactionResource.hold_state.in_([HoldState.held, "held"]),
    )
    tr_result = await db.execute(tr_stmt)
    held_resources = [r.resource_id for r in tr_result.scalars().all()]

    # 5. Release each held resource
    for rid in held_resources:
        await release_single_resource(db, tx.tx_id, rid)

    # 6. Transition TX to COMPLETED and CLOSED
    tx.state = TxState.COMPLETED
    tx.closed_at = now_utc
    tx.updated_at = now_utc
    h_completed = TransactionStateHistory(
        tx_id=tx_id,
        state=TxState.COMPLETED,
        occurred_at=now_utc,
    )
    db.add(h_completed)

    tx.state = TxState.CLOSED
    h_closed = TransactionStateHistory(
        tx_id=tx_id,
        state=TxState.CLOSED,
        occurred_at=now_utc,
    )
    db.add(h_closed)

    # 7. Audit
    await create_audit_event(
        db=db,
        event_type="TRANSACTION_COMPLETED",
        tx_id=tx_id,
        decision="COMMIT",
        detail={"resources_released": held_resources},
    )

    # 8. Publish
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "TRANSACTION_UPDATED",
            "tx_id": tx_id,
            "status": "COMPLETED",
            "timestamp": now_utc.isoformat(),
        },
    )

    # 9. Commit
    await db.commit()

    # 10. Dispatch Digital Emergency Operation Record generation (async Celery task)
    try:
        from app.workers.tasks import generate_operation_record_pdf
        generate_operation_record_pdf.delay(tx_id)
    except Exception as e:
        logger.warning(f"Could not dispatch generate_operation_record_pdf for tx={tx_id}: {e}")

    return {
        "tx_id": tx_id,
        "status": "COMPLETED",
        "resources_released": held_resources,
    }


# =============================================================================
# COORDINATOR CLASS (EXTENDED WITH BED MANAGEMENT 2PC HOOKS)
# =============================================================================

class Coordinator:
    """
    Coordinates multi-resource clinical transactions across standard resources
    and Bed entities with 2PC readiness, holds, commit and rollback hooks.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis] = None,
    ):
        self.db = db
        self.redis = redis_client

    async def _check_existing_resource(
        self,
        resource_id: str,
        resource_type: str,
    ) -> bool:
        stmt = select(Resource).where(Resource.resource_id == resource_id)
        result = await self.db.execute(stmt)
        res = result.scalar_one_or_none()
        if not res:
            return False
        res_status = (
            res.status.value if hasattr(res.status, "value") else str(res.status)
        )
        return res_status == "available"

    async def check_resource_availability(
        self,
        resource_id: str,
        resource_type: str,
        requested_quantity: int = 1,
    ) -> bool:
        """
        EXTENDED: Bed resources must be READY (not just FREE).
        Pharmacy resources use quantity + expiry check.
        Non-bed resources use existing logic.
        """
        if resource_type in BED_RESOURCE_TYPES:
            bed_service = BedService(self.db, self.redis)
            available_beds = await bed_service.get_ready_beds(
                bed_type=resource_type.replace("BED_", "")
            )
            return any(b.id == resource_id for b in available_beds)
        elif resource_type in PHARMACY_RESOURCE_TYPES:
            import uuid as _uuid
            pharmacy_service = PharmacyService(self.db, self.redis)
            is_ready, _ = await pharmacy_service.check_readiness(
                resource_id=_uuid.UUID(resource_id),
                requested_quantity=requested_quantity,
            )
            return is_ready
        elif resource_type in DIAGNOSTIC_RESOURCE_TYPES:
            import uuid as _uuid
            from datetime import datetime, timezone, timedelta
            diag_service = DiagnosticsSchedulingService(self.db, self.redis)
            now = datetime.now(timezone.utc)
            is_ready, _, _ = await diag_service.check_equipment_readiness(
                equipment_id=_uuid.UUID(resource_id),
                start=now,
                end=now + timedelta(minutes=30),
            )
            return is_ready
        elif resource_type in LAB_RESOURCE_TYPES:
            import uuid as _uuid
            lab_service = LabQueueService(self.db, self.redis)
            is_ready, _ = await lab_service.check_lab_readiness(
                lab_slot_id=_uuid.UUID(resource_id)
            )
            return is_ready
        else:
            # Existing resource availability check
            return await self._check_existing_resource(resource_id, resource_type)

    async def two_pc_prepare(self, transaction: Any) -> bool:
        """
        EXTENDED: For bed resources, call bed_service.tentative_hold().
        For pharmacy resources, call pharmacy_service.reserve_quantity().
        """
        import uuid as _uuid
        bed_service = BedService(self.db, self.redis)
        pharmacy_service = PharmacyService(self.db, self.redis)
        held_beds = []
        pharmacy_reservations = []  # (reservation_id, resource_id)

        resources = getattr(transaction, "resources", [])
        tx_id = getattr(transaction, "id", getattr(transaction, "tx_id", None))

        for resource in resources:
            res_type = getattr(
                resource, "type", getattr(resource, "resource_type", None)
            )
            res_id = getattr(
                resource, "id", getattr(resource, "resource_id", None)
            )
            if res_type in BED_RESOURCE_TYPES:
                try:
                    await bed_service.tentative_hold(res_id, tx_id)
                    held_beds.append(res_id)
                except Exception:
                    # Rollback beds
                    for held_id in held_beds:
                        await bed_service.release_tentative_hold(
                            held_id, "PREPARE_FAILED"
                        )
                    # Rollback pharmacy reservations
                    for rv_id, _ in pharmacy_reservations:
                        try:
                            await pharmacy_service.release_reservation(
                                _uuid.UUID(rv_id), "PREPARE_FAILED"
                            )
                        except Exception:
                            pass
                    return False
            elif res_type in PHARMACY_RESOURCE_TYPES:
                qty = getattr(resource, "quantity", getattr(resource, "requested_quantity", 1))
                is_emergency = getattr(resource, "is_emergency", False)
                try:
                    result = await pharmacy_service.reserve_quantity(
                        resource_id=_uuid.UUID(res_id),
                        tx_id=tx_id,
                        quantity=qty,
                        ttl_seconds=30,
                        is_emergency=is_emergency,
                    )
                    pharmacy_reservations.append((result["reservation_id"], res_id))
                except Exception:
                    # Rollback beds
                    for held_id in held_beds:
                        await bed_service.release_tentative_hold(
                            held_id, "PREPARE_FAILED"
                        )
                    # Rollback pharmacy reservations
                    for rv_id, _ in pharmacy_reservations:
                        try:
                            await pharmacy_service.release_reservation(
                                _uuid.UUID(rv_id), "PREPARE_FAILED"
                            )
                        except Exception:
                            pass
                    return False
            elif res_type in DIAGNOSTIC_RESOURCE_TYPES:
                from datetime import datetime, timezone, timedelta
                diag_service = DiagnosticsSchedulingService(self.db, self.redis)
                start_time = getattr(resource, "scheduled_start", None) or datetime.now(timezone.utc)
                duration = getattr(resource, "duration_minutes", 30)
                end_time = getattr(resource, "scheduled_end", None) or (start_time + timedelta(minutes=duration))
                patient_id = getattr(transaction, "patient_id", "PT-UNKNOWN")
                try:
                    appt = await diag_service.request_appointment(
                        equipment_id=_uuid.UUID(res_id),
                        tx_id=tx_id,
                        patient_id=patient_id,
                        start=start_time,
                        end=end_time,
                        ttl_seconds=30,
                    )
                except Exception:
                    for held_id in held_beds:
                        await bed_service.release_tentative_hold(held_id, "PREPARE_FAILED")
                    for rv_id, _ in pharmacy_reservations:
                        try:
                            await pharmacy_service.release_reservation(_uuid.UUID(rv_id), "PREPARE_FAILED")
                        except Exception:
                            pass
                    return False
            elif res_type in LAB_RESOURCE_TYPES:
                lab_service = LabQueueService(self.db, self.redis)
                patient_id = getattr(transaction, "patient_id", "PT-UNKNOWN")
                test_type = getattr(resource, "test_type", "CBC")
                priority = getattr(resource, "priority", "ROUTINE")
                try:
                    await lab_service.submit_sample(
                        lab_slot_id=_uuid.UUID(res_id),
                        tx_id=tx_id,
                        patient_id=patient_id,
                        test_type=test_type,
                        priority=priority,
                    )
                except Exception:
                    for held_id in held_beds:
                        await bed_service.release_tentative_hold(held_id, "PREPARE_FAILED")
                    for rv_id, _ in pharmacy_reservations:
                        try:
                            await pharmacy_service.release_reservation(_uuid.UUID(rv_id), "PREPARE_FAILED")
                        except Exception:
                            pass
                    return False

        return True  # Continue with non-bed/non-pharmacy resources via existing logic

    async def two_pc_commit(self, transaction: Any) -> None:
        """
        EXTENDED: Commit bed allocations and dispense pharmacy reservations
        after full 2PC commit.
        """
        import uuid as _uuid
        bed_service = BedService(self.db, self.redis)
        pharmacy_service = PharmacyService(self.db, self.redis)
        resources = getattr(transaction, "resources", [])
        tx_id = getattr(transaction, "id", getattr(transaction, "tx_id", None))
        patient_id = getattr(transaction, "patient_id", None)
        created_by = getattr(
            transaction, "created_by", getattr(transaction, "requested_by", "SYSTEM")
        )

        for resource in resources:
            res_type = getattr(
                resource, "type", getattr(resource, "resource_type", None)
            )
            res_id = getattr(
                resource, "id", getattr(resource, "resource_id", None)
            )
            if res_type in BED_RESOURCE_TYPES:
                await bed_service.commit_allocation(
                    bed_id=res_id,
                    patient_id=patient_id,
                    transaction_id=tx_id,
                    employee_id=created_by,
                )
            elif res_type in PHARMACY_RESOURCE_TYPES:
                # Find RESERVED reservations for this tx + resource and dispense
                from app.models.pharmacy import PharmacyReservation, PharmacyReservationStatus
                stmt = select(PharmacyReservation).where(
                    PharmacyReservation.tx_id == tx_id,
                    PharmacyReservation.pharmacy_resource_id == _uuid.UUID(res_id),
                    PharmacyReservation.status == PharmacyReservationStatus.RESERVED,
                )
                result = await self.db.execute(stmt)
                for reservation in result.scalars().all():
                    await pharmacy_service.dispense_reservation(reservation.id)
            elif res_type in DIAGNOSTIC_RESOURCE_TYPES:
                from app.models.diagnostics import DiagnosticAppointment, AppointmentStatus
                diag_service = DiagnosticsSchedulingService(self.db, self.redis)
                stmt = select(DiagnosticAppointment).where(
                    DiagnosticAppointment.tx_id == tx_id,
                    DiagnosticAppointment.equipment_id == _uuid.UUID(res_id),
                    DiagnosticAppointment.status == AppointmentStatus.PENDING_CONFIRM.value,
                )
                result = await self.db.execute(stmt)
                for appt in result.scalars().all():
                    await diag_service.confirm_appointment(appt.id)

    async def two_pc_rollback(
        self,
        transaction: Any,
        reason: str = "ROLLBACK",
    ) -> None:
        """
        EXTENDED: Release bed tentative holds and pharmacy reservations on rollback.
        """
        import uuid as _uuid
        bed_service = BedService(self.db, self.redis)
        pharmacy_service = PharmacyService(self.db, self.redis)
        resources = getattr(transaction, "resources", [])
        tx_id = getattr(transaction, "id", getattr(transaction, "tx_id", None))

        for resource in resources:
            res_type = getattr(
                resource, "type", getattr(resource, "resource_type", None)
            )
            res_id = getattr(
                resource, "id", getattr(resource, "resource_id", None)
            )
            if res_type in BED_RESOURCE_TYPES:
                await bed_service.release_tentative_hold(res_id, reason)
            elif res_type in PHARMACY_RESOURCE_TYPES:
                # Release RESERVED pharmacy reservations for this tx + resource
                from app.models.pharmacy import PharmacyReservation, PharmacyReservationStatus
                stmt = select(PharmacyReservation).where(
                    PharmacyReservation.tx_id == tx_id,
                    PharmacyReservation.pharmacy_resource_id == _uuid.UUID(res_id),
                    PharmacyReservation.status == PharmacyReservationStatus.RESERVED,
                )
                result = await self.db.execute(stmt)
                for reservation in result.scalars().all():
                    try:
                        await pharmacy_service.release_reservation(
                            reservation.id, reason
                        )
                    except Exception:
                        pass
            elif res_type in DIAGNOSTIC_RESOURCE_TYPES:
                from app.models.diagnostics import DiagnosticAppointment, AppointmentStatus
                diag_service = DiagnosticsSchedulingService(self.db, self.redis)
                stmt = select(DiagnosticAppointment).where(
                    DiagnosticAppointment.tx_id == tx_id,
                    DiagnosticAppointment.equipment_id == _uuid.UUID(res_id),
                    DiagnosticAppointment.status.in_([
                        AppointmentStatus.PENDING_CONFIRM.value,
                        AppointmentStatus.CONFIRMED.value,
                    ]),
                )
                result = await self.db.execute(stmt)
                for appt in result.scalars().all():
                    try:
                        await diag_service.cancel_appointment(appt.id, reason=reason)
                    except Exception:
                        pass


# Convenience module-level aliases
async def check_resource_availability(
    db: AsyncSession,
    resource_id: str,
    resource_type: str,
    redis_client: Optional[aioredis.Redis] = None,
) -> bool:
    coord = Coordinator(db, redis_client)
    return await coord.check_resource_availability(resource_id, resource_type)


async def two_pc_prepare(
    db: AsyncSession,
    transaction: Any,
    redis_client: Optional[aioredis.Redis] = None,
) -> bool:
    coord = Coordinator(db, redis_client)
    return await coord.two_pc_prepare(transaction)


async def two_pc_commit(
    db: AsyncSession,
    transaction: Any,
    redis_client: Optional[aioredis.Redis] = None,
) -> None:
    coord = Coordinator(db, redis_client)
    await coord.two_pc_commit(transaction)


async def two_pc_rollback(
    db: AsyncSession,
    transaction: Any,
    reason: str = "ROLLBACK",
    redis_client: Optional[aioredis.Redis] = None,
) -> None:
    coord = Coordinator(db, redis_client)
    await coord.two_pc_rollback(transaction, reason)

