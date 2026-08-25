"""
PharmacyService — quantity-based consumable resource allocator.

Responsibilities:
  • Atomic quantity-safe reserve / dispense / release
  • Status derivation (STOCKED / LOW_STOCK / DEPLETED / EXPIRED)
  • Batch expiry sweep
  • Shortage detection & WebSocket alert publishing
  • CRUD for admin restock / recall
"""

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pharmacy import (
    PharmacyReservation,
    PharmacyReservationStatus,
    PharmacyResource,
    PharmacyResourceStatus,
    PharmacyResourceType,
)
from app.services.audit import create_audit_event

logger = logging.getLogger(__name__)

# Resource types routed to pharmacy allocator
PHARMACY_RESOURCE_TYPES = {"MEDICATION_SLOT", "BLOOD_UNIT", "OXYGEN_UNIT"}


class InsufficientStockError(Exception):
    """Raised when available_quantity < requested quantity."""
    pass


class InvalidReservationStateError(Exception):
    """Raised when a reservation cannot transition to the requested state."""
    pass


class PharmacyService:

    def __init__(
        self,
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis] = None,
    ):
        self.db = db
        self.redis = redis_client

    # ─────────────────────────────────────────
    # STATUS DERIVATION
    # ─────────────────────────────────────────

    @staticmethod
    def derive_status(resource: PharmacyResource) -> PharmacyResourceStatus:
        """
        Compute status from quantity + expiry state.
        Precedence: EXPIRED > RECALLED > DEPLETED > LOW_STOCK > STOCKED.
        """
        current_status = (
            resource.status.value
            if hasattr(resource.status, "value")
            else str(resource.status)
        )
        if current_status == "RECALLED":
            return PharmacyResourceStatus.RECALLED

        if resource.expiry_date < date.today():
            return PharmacyResourceStatus.EXPIRED

        if resource.available_quantity <= 0:
            return PharmacyResourceStatus.DEPLETED

        if resource.available_quantity <= resource.critical_threshold:
            return PharmacyResourceStatus.LOW_STOCK

        return PharmacyResourceStatus.STOCKED

    async def _update_derived_status(self, resource: PharmacyResource) -> None:
        """Recompute and persist the derived status."""
        new_status = self.derive_status(resource)
        resource.status = new_status
        await self.db.flush()

    # ─────────────────────────────────────────
    # CORE OPERATIONS
    # ─────────────────────────────────────────

    async def reserve_quantity(
        self,
        resource_id: uuid.UUID,
        tx_id: str,
        quantity: int,
        ttl_seconds: int = 30,
        is_emergency: bool = False,
    ) -> Dict[str, Any]:
        """
        Atomic reservation: UPDATE ... WHERE available_quantity >= qty.
        Emergency override (acuity >= 9.5) can draw below critical_threshold
        but never below 0.

        Returns dict with reservation details and partial_fulfillment flag.
        """
        now_utc = datetime.now(timezone.utc)

        # 1. Lock the resource row
        stmt = (
            select(PharmacyResource)
            .where(PharmacyResource.id == resource_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        resource = result.scalar_one_or_none()

        if not resource:
            raise ValueError(f"Pharmacy resource {resource_id} not found")

        # Check expiry
        if resource.expiry_date < date.today():
            resource.status = PharmacyResourceStatus.EXPIRED
            await self.db.flush()
            raise InsufficientStockError(
                f"Batch {resource.batch_id} has expired ({resource.expiry_date})"
            )

        # 2. Determine fulfillable quantity
        actual_quantity = quantity
        partial_fulfillment = False

        if resource.available_quantity >= quantity:
            actual_quantity = quantity
        elif is_emergency and resource.available_quantity > 0:
            # Emergency: take whatever is available
            actual_quantity = resource.available_quantity
            partial_fulfillment = True
            logger.warning(
                f"Emergency override: fulfilling {actual_quantity}/{quantity} "
                f"units from resource {resource_id} (batch {resource.batch_id})",
                extra={
                    "resource_id": str(resource_id),
                    "tx_id": tx_id,
                    "requested": quantity,
                    "fulfilled": actual_quantity,
                },
            )
        else:
            raise InsufficientStockError(
                f"Insufficient stock: available={resource.available_quantity}, "
                f"requested={quantity}"
            )

        # 3. Atomic decrement
        resource.available_quantity -= actual_quantity
        resource.reserved_quantity += actual_quantity
        await self._update_derived_status(resource)

        # 4. Create reservation row
        reservation = PharmacyReservation(
            id=uuid.uuid4(),
            tx_id=tx_id,
            pharmacy_resource_id=resource_id,
            quantity=actual_quantity,
            status=PharmacyReservationStatus.RESERVED,
            reserved_at=now_utc,
            ttl_expires_at=now_utc + timedelta(seconds=ttl_seconds),
        )
        self.db.add(reservation)
        await self.db.flush()

        # 5. Audit
        await create_audit_event(
            db=self.db,
            event_type="PHARMACY_RESERVED",
            tx_id=tx_id,
            detail={
                "resource_id": str(resource_id),
                "batch_id": resource.batch_id,
                "sub_type": resource.sub_type,
                "quantity": actual_quantity,
                "available_quantity_after": resource.available_quantity,
                "partial_fulfillment": partial_fulfillment,
                "emergency_override": is_emergency and partial_fulfillment,
            },
        )

        # 6. Check shortage
        await self.check_and_alert_shortage(resource)

        # 7. Publish update
        await self._publish_pharmacy_update(resource, "PHARMACY_RESERVED")

        return {
            "reservation_id": str(reservation.id),
            "resource_id": str(resource_id),
            "tx_id": tx_id,
            "quantity_fulfilled": actual_quantity,
            "quantity_requested": quantity,
            "partial_fulfillment": partial_fulfillment,
            "available_quantity_after": resource.available_quantity,
            "ttl_expires_at": reservation.ttl_expires_at.isoformat(),
        }

    async def dispense_reservation(
        self, reservation_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        RESERVED → DISPENSED. Permanently consumed.
        Decrements reserved_quantity (quantity already removed from available).
        """
        now_utc = datetime.now(timezone.utc)

        stmt = (
            select(PharmacyReservation)
            .where(PharmacyReservation.id == reservation_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        reservation = result.scalar_one_or_none()

        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        res_status = (
            reservation.status.value
            if hasattr(reservation.status, "value")
            else str(reservation.status)
        )
        if res_status != "RESERVED":
            raise InvalidReservationStateError(
                f"Reservation {reservation_id} is {res_status}, cannot dispense"
            )

        # Update reservation
        reservation.status = PharmacyReservationStatus.DISPENSED
        reservation.dispensed_at = now_utc

        # Update resource: reserved_quantity -= quantity (permanently consumed)
        res_stmt = (
            select(PharmacyResource)
            .where(PharmacyResource.id == reservation.pharmacy_resource_id)
            .with_for_update()
        )
        res_result = await self.db.execute(res_stmt)
        resource = res_result.scalar_one()
        resource.reserved_quantity -= reservation.quantity
        await self._update_derived_status(resource)
        await self.db.flush()

        # Audit
        await create_audit_event(
            db=self.db,
            event_type="PHARMACY_DISPENSED",
            tx_id=reservation.tx_id,
            detail={
                "reservation_id": str(reservation_id),
                "resource_id": str(resource.id),
                "batch_id": resource.batch_id,
                "quantity": reservation.quantity,
                "available_quantity_after": resource.available_quantity,
            },
        )

        await self._publish_pharmacy_update(resource, "PHARMACY_DISPENSED")

        return {
            "reservation_id": str(reservation_id),
            "status": "DISPENSED",
            "quantity": reservation.quantity,
        }

    async def release_reservation(
        self,
        reservation_id: uuid.UUID,
        reason: str = "MANUAL",
    ) -> Dict[str, Any]:
        """
        RESERVED → RELEASED. Restores available_quantity.
        """
        now_utc = datetime.now(timezone.utc)

        stmt = (
            select(PharmacyReservation)
            .where(PharmacyReservation.id == reservation_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        reservation = result.scalar_one_or_none()

        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        res_status = (
            reservation.status.value
            if hasattr(reservation.status, "value")
            else str(reservation.status)
        )
        if res_status != "RESERVED":
            raise InvalidReservationStateError(
                f"Reservation {reservation_id} is {res_status}, cannot release"
            )

        # Update reservation
        reservation.status = PharmacyReservationStatus.RELEASED
        reservation.released_at = now_utc

        # Restore quantities
        res_stmt = (
            select(PharmacyResource)
            .where(PharmacyResource.id == reservation.pharmacy_resource_id)
            .with_for_update()
        )
        res_result = await self.db.execute(res_stmt)
        resource = res_result.scalar_one()
        resource.available_quantity += reservation.quantity
        resource.reserved_quantity -= reservation.quantity
        await self._update_derived_status(resource)
        await self.db.flush()

        # Audit
        await create_audit_event(
            db=self.db,
            event_type="PHARMACY_RELEASED",
            tx_id=reservation.tx_id,
            detail={
                "reservation_id": str(reservation_id),
                "resource_id": str(resource.id),
                "batch_id": resource.batch_id,
                "quantity": reservation.quantity,
                "reason": reason,
                "available_quantity_after": resource.available_quantity,
            },
        )

        # Re-check shortage (may auto-clear if restocked above threshold)
        await self.check_and_alert_shortage(resource)
        await self._publish_pharmacy_update(resource, "PHARMACY_RELEASED")

        return {
            "reservation_id": str(reservation_id),
            "status": "RELEASED",
            "quantity_restored": reservation.quantity,
            "available_quantity_after": resource.available_quantity,
        }

    # ─────────────────────────────────────────
    # SHORTAGE CHECK
    # ─────────────────────────────────────────

    async def check_and_alert_shortage(
        self, resource: PharmacyResource
    ) -> None:
        """
        Publish shortage alert to WebSocket if below threshold,
        or clear alert if back above threshold.
        """
        is_critical = resource.available_quantity <= resource.critical_threshold
        resource_type = (
            resource.resource_type.value
            if hasattr(resource.resource_type, "value")
            else str(resource.resource_type)
        )
        status_str = (
            resource.status.value
            if hasattr(resource.status, "value")
            else str(resource.status)
        )

        # Trigger central Shortage Detection Engine
        try:
            from app.services.shortage import check_shortage
            subtype = resource.item_code or resource.sub_type or ""
            if subtype:
                await check_shortage(
                    resource_type=resource_type,
                    subtype=subtype,
                    db=self.db,
                    redis_client=self.redis,
                )
        except Exception as err:
            logger.warning(f"Error in shortage engine check: {err}")

        if self.redis:
            alert_data = {
                "event": "PHARMACY_SHORTAGE_UPDATE",
                "resource_id": str(resource.id),
                "resource_type": resource_type,
                "sub_type": resource.sub_type,
                "batch_id": resource.batch_id,
                "available_quantity": resource.available_quantity,
                "critical_threshold": resource.critical_threshold,
                "is_critical": is_critical,
                "status": status_str,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            try:
                await self.redis.publish(
                    "pharmacy_alerts", json.dumps(alert_data, default=str)
                )
                # Also publish to main dashboard channel
                await self.redis.publish(
                    "pubsub:dashboard", json.dumps(alert_data, default=str)
                )
            except Exception as e:
                logger.warning(f"Failed to publish pharmacy alert: {e}")

    # ─────────────────────────────────────────
    # BATCH EXPIRY SWEEP
    # ─────────────────────────────────────────

    async def expire_stale_batches(self) -> List[str]:
        """
        Bulk-expire all batches past expiry_date.
        Zeroes available_quantity, triggers shortage recheck.
        Returns list of expired batch_ids.
        """
        today = date.today()
        stmt = (
            select(PharmacyResource)
            .where(
                PharmacyResource.expiry_date < today,
                PharmacyResource.status.notin_([
                    PharmacyResourceStatus.EXPIRED,
                    PharmacyResourceStatus.RECALLED,
                ]),
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        resources = list(result.scalars().all())

        expired_batch_ids = []
        for resource in resources:
            resource.status = PharmacyResourceStatus.EXPIRED
            resource.available_quantity = 0
            expired_batch_ids.append(resource.batch_id)

            await create_audit_event(
                db=self.db,
                event_type="PHARMACY_BATCH_EXPIRED",
                detail={
                    "resource_id": str(resource.id),
                    "batch_id": resource.batch_id,
                    "sub_type": resource.sub_type,
                    "expiry_date": str(resource.expiry_date),
                },
            )
            await self.check_and_alert_shortage(resource)
            await self._publish_pharmacy_update(resource, "PHARMACY_BATCH_EXPIRED")

        if expired_batch_ids:
            await self.db.flush()
            logger.info(
                f"Pharmacy expiry sweep: {len(expired_batch_ids)} batch(es) expired",
                extra={"expired_batch_ids": expired_batch_ids},
            )

        return expired_batch_ids

    # ─────────────────────────────────────────
    # TTL SWEEP (stale reservations)
    # ─────────────────────────────────────────

    async def sweep_expired_reservations(self) -> int:
        """
        Release all RESERVED pharmacy reservations past ttl_expires_at.
        Returns count of released reservations.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(PharmacyReservation)
            .where(
                PharmacyReservation.status == PharmacyReservationStatus.RESERVED,
                PharmacyReservation.ttl_expires_at < now_utc,
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        reservations = list(result.scalars().all())

        count = 0
        for reservation in reservations:
            reservation.status = PharmacyReservationStatus.EXPIRED
            reservation.released_at = now_utc

            # Restore quantities
            res_stmt = (
                select(PharmacyResource)
                .where(PharmacyResource.id == reservation.pharmacy_resource_id)
                .with_for_update()
            )
            res_result = await self.db.execute(res_stmt)
            resource = res_result.scalar_one()
            resource.available_quantity += reservation.quantity
            resource.reserved_quantity -= reservation.quantity
            await self._update_derived_status(resource)

            await create_audit_event(
                db=self.db,
                event_type="PHARMACY_RELEASED",
                tx_id=reservation.tx_id,
                detail={
                    "reservation_id": str(reservation.id),
                    "resource_id": str(resource.id),
                    "reason": "TTL_EXPIRED",
                    "quantity": reservation.quantity,
                    "available_quantity_after": resource.available_quantity,
                },
            )
            await self.check_and_alert_shortage(resource)
            await self._publish_pharmacy_update(resource, "PHARMACY_TTL_RELEASED")
            count += 1

        if count:
            await self.db.flush()
            logger.info(
                f"Pharmacy TTL sweep: {count} reservation(s) released",
            )

        return count

    # ─────────────────────────────────────────
    # CRUD / READ OPERATIONS
    # ─────────────────────────────────────────

    async def get_resources(
        self,
        resource_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> List[PharmacyResource]:
        """List pharmacy resources with optional filtering."""
        stmt = select(PharmacyResource)
        if resource_type:
            stmt = stmt.where(PharmacyResource.resource_type == resource_type)
        if sub_type:
            stmt = stmt.where(PharmacyResource.sub_type == sub_type)
        if status_filter:
            stmt = stmt.where(PharmacyResource.status == status_filter)
        stmt = stmt.order_by(
            PharmacyResource.resource_type,
            PharmacyResource.sub_type,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_resource_by_id(
        self, resource_id: uuid.UUID
    ) -> Optional[PharmacyResource]:
        """Get a single pharmacy resource by ID."""
        stmt = select(PharmacyResource).where(
            PharmacyResource.id == resource_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_resource(
        self, data: Dict[str, Any]
    ) -> PharmacyResource:
        """Admin: create or restock a pharmacy batch."""
        resource = PharmacyResource(
            id=uuid.uuid4(),
            resource_type=data["resource_type"],
            sub_type=data.get("sub_type"),
            batch_id=data["batch_id"],
            total_quantity=data["total_quantity"],
            available_quantity=data["total_quantity"],
            reserved_quantity=0,
            unit=data["unit"],
            expiry_date=data["expiry_date"],
            storage_location=data.get("storage_location"),
            critical_threshold=data["critical_threshold"],
            status=PharmacyResourceStatus.STOCKED,
        )
        self.db.add(resource)
        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="PHARMACY_RESTOCKED",
            detail={
                "resource_id": str(resource.id),
                "batch_id": resource.batch_id,
                "sub_type": resource.sub_type,
                "total_quantity": resource.total_quantity,
            },
        )
        await self._publish_pharmacy_update(resource, "PHARMACY_RESTOCKED")

        return resource

    async def update_resource(
        self,
        resource_id: uuid.UUID,
        updates: Dict[str, Any],
    ) -> PharmacyResource:
        """Admin: update threshold, recall batch, etc."""
        stmt = (
            select(PharmacyResource)
            .where(PharmacyResource.id == resource_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        resource = result.scalar_one_or_none()
        if not resource:
            raise ValueError(f"Pharmacy resource {resource_id} not found")

        if "critical_threshold" in updates:
            resource.critical_threshold = updates["critical_threshold"]

        if "storage_location" in updates:
            resource.storage_location = updates["storage_location"]

        if updates.get("recall"):
            resource.status = PharmacyResourceStatus.RECALLED
            resource.available_quantity = 0

        await self._update_derived_status(resource)
        await self.db.flush()

        await self._publish_pharmacy_update(resource, "PHARMACY_UPDATED")
        return resource

    async def get_shortage_status(self) -> List[Dict[str, Any]]:
        """
        Returns all resources at or below critical threshold
        (feeds Donation Board / shortage dashboard).
        """
        stmt = select(PharmacyResource).where(
            PharmacyResource.status.in_([
                PharmacyResourceStatus.LOW_STOCK,
                PharmacyResourceStatus.DEPLETED,
                PharmacyResourceStatus.EXPIRED,
            ])
        )
        result = await self.db.execute(stmt)
        resources = list(result.scalars().all())

        items = []
        for r in resources:
            rt = r.resource_type.value if hasattr(r.resource_type, "value") else str(r.resource_type)
            st = r.status.value if hasattr(r.status, "value") else str(r.status)
            items.append({
                "resource_id": str(r.id),
                "resource_type": rt,
                "sub_type": r.sub_type,
                "batch_id": r.batch_id,
                "available_quantity": r.available_quantity,
                "total_quantity": r.total_quantity,
                "critical_threshold": r.critical_threshold,
                "status": st,
                "expiry_date": str(r.expiry_date),
            })

        return items

    # ─────────────────────────────────────────
    # READINESS CHECK (for coordinator)
    # ─────────────────────────────────────────

    async def check_readiness(
        self,
        resource_id: uuid.UUID,
        requested_quantity: int,
    ) -> Tuple[bool, str]:
        """
        Quantity + expiry aware readiness check.
        Returns (is_ready, reason).
        """
        resource = await self.get_resource_by_id(resource_id)
        if not resource:
            return False, "RESOURCE_NOT_FOUND"

        if resource.expiry_date < date.today():
            return False, "EXPIRED"

        current_status = (
            resource.status.value
            if hasattr(resource.status, "value")
            else str(resource.status)
        )
        if current_status == "RECALLED":
            return False, "RECALLED"

        if resource.available_quantity >= requested_quantity:
            return True, "READY"

        return False, f"INSUFFICIENT_STOCK (available={resource.available_quantity})"

    # ─────────────────────────────────────────
    # INTERNAL HELPERS
    # ─────────────────────────────────────────

    async def _publish_pharmacy_update(
        self, resource: PharmacyResource, event_type: str
    ) -> None:
        """Publish real-time update to pharmacy_alerts and pubsub:dashboard."""
        if not self.redis:
            return

        resource_type = (
            resource.resource_type.value
            if hasattr(resource.resource_type, "value")
            else str(resource.resource_type)
        )
        status_str = (
            resource.status.value
            if hasattr(resource.status, "value")
            else str(resource.status)
        )

        payload = {
            "event": event_type,
            "resource_id": str(resource.id),
            "resource_type": resource_type,
            "sub_type": resource.sub_type,
            "batch_id": resource.batch_id,
            "available_quantity": resource.available_quantity,
            "total_quantity": resource.total_quantity,
            "reserved_quantity": resource.reserved_quantity,
            "status": status_str,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            msg = json.dumps(payload, default=str)
            await self.redis.publish("pharmacy_alerts", msg)
            await self.redis.publish("pubsub:dashboard", msg)
        except Exception as e:
            logger.warning(f"Failed to publish pharmacy update: {e}")
