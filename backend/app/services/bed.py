"""
BedService — complete bed lifecycle management.

Responsibilities:
  • State machine transitions (with validation)
  • Allocation via transaction engine hook
  • Release + auto-cleaning trigger
  • Readiness queries (only READY beds for allocation)
  • Floor-wise grid aggregation for dashboard
  • Shortage detection for donation board
  • WebSocket event publishing on every state change
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Bed, BedAssignment, BedCleaningLog, BedStatus, BedType

logger = logging.getLogger(__name__)

# Cleaning duration by bed type (minutes)
CLEANING_DURATION: Dict[str, int] = {
    "ICU": 30,
    "GENERAL": 20,
    "STEP_DOWN": 25,
    "EMERGENCY": 15,
}

# Critical threshold — below this, shortage alert fires
CRITICAL_THRESHOLD: Dict[str, int] = {
    "ICU": 2,
    "GENERAL": 3,
    "STEP_DOWN": 2,
    "EMERGENCY": 2,
}

# Valid transitions — (current_status) → [allowed_next_statuses]
VALID_TRANSITIONS: Dict[BedStatus, List[BedStatus]] = {
    BedStatus.FREE: [BedStatus.CLEANING, BedStatus.MAINTENANCE, BedStatus.READY],
    BedStatus.CLEANING: [BedStatus.SANITIZED, BedStatus.FREE, BedStatus.READY],
    BedStatus.SANITIZED: [BedStatus.READY, BedStatus.CLEANING],
    BedStatus.READY: [BedStatus.TENTATIVE_HOLD, BedStatus.MAINTENANCE, BedStatus.CLEANING],
    BedStatus.TENTATIVE_HOLD: [BedStatus.LOCKED, BedStatus.READY],  # commit or TTL rollback
    BedStatus.LOCKED: [BedStatus.IN_USE, BedStatus.READY],
    BedStatus.IN_USE: [BedStatus.POST_USE],
    BedStatus.POST_USE: [BedStatus.CLEANING, BedStatus.MAINTENANCE],
    BedStatus.MAINTENANCE: [BedStatus.CLEANING, BedStatus.FREE, BedStatus.READY],
    BedStatus.OUT_OF_SERVICE: [BedStatus.MAINTENANCE],
}


class InvalidTransitionError(Exception):
    pass


class BedService:

    def __init__(self, db: AsyncSession, redis_client: Optional[aioredis.Redis] = None):
        self.db = db
        self.redis = redis_client

    # ─────────────────────────────────────────
    # READ OPERATIONS
    # ─────────────────────────────────────────

    async def get_all_beds(
        self,
        bed_type: Optional[str] = None,
        floor: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Bed]:
        query = select(Bed)
        if bed_type:
            query = query.where(Bed.bed_type == bed_type)
        if floor is not None:
            query = query.where(Bed.floor == floor)
        if status:
            query = query.where(Bed.status == status)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_ready_beds(self, bed_type: Optional[str] = None) -> List[Bed]:
        """
        Used by: Transaction Engine, AI Recommendation Engine.
        Returns ONLY READY beds — the single source of truth for allocatable beds.
        """
        query = select(Bed).where(Bed.status == BedStatus.READY)
        if bed_type:
            query = query.where(Bed.bed_type == bed_type)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_bed_by_id(self, bed_id: str) -> Optional[Bed]:
        result = await self.db.execute(select(Bed).where(Bed.id == bed_id))
        return result.scalar_one_or_none()

    async def get_bed_grid(self) -> List[Dict[str, Any]]:
        """
        Floor-wise grouped beds with summary counts.
        Used by: Frontend BedGrid dashboard component.
        """
        all_beds = await self.get_all_beds()
        floors: Dict[int, Dict[str, Any]] = {}

        for bed in all_beds:
            f = bed.floor
            if f not in floors:
                floors[f] = {"floor": f, "beds": [], "summary": {}}
            floors[f]["beds"].append(bed)
            s = bed.status.value if hasattr(bed.status, "value") else str(bed.status)
            floors[f]["summary"][s] = floors[f]["summary"].get(s, 0) + 1

        return sorted(floors.values(), key=lambda x: x["floor"])

    async def get_shortage_summary(self) -> List[Dict[str, Any]]:
        """
        Aggregated readiness counts per bed type.
        Used by: Shortage Detection Service → Donation Board.
        """
        rows = await self.db.execute(
            select(Bed.bed_type, Bed.status, func.count().label("count"))
            .group_by(Bed.bed_type, Bed.status)
        )

        type_counts: Dict[str, Dict[str, Any]] = {}
        for row in rows.all():
            t = row.bed_type.value if hasattr(row.bed_type, "value") else str(row.bed_type)
            if t not in type_counts:
                type_counts[t] = {
                    "bed_type": t,
                    "total": 0,
                    "ready": 0,
                    "in_use": 0,
                    "cleaning": 0,
                    "maintenance": 0,
                }
            type_counts[t]["total"] += row.count
            status_key = (
                row.status.value if hasattr(row.status, "value") else str(row.status)
            ).lower()
            if status_key in type_counts[t]:
                type_counts[t][status_key] += row.count

        result = []
        for t, counts in type_counts.items():
            threshold = CRITICAL_THRESHOLD.get(t, 2)
            counts["is_critical"] = counts["ready"] < threshold
            counts["threshold"] = threshold
            result.append(counts)

        return result

    # ─────────────────────────────────────────
    # STATE TRANSITIONS
    # ─────────────────────────────────────────

    async def transition_status(
        self,
        bed_id: str,
        new_status: BedStatus,
        employee_id: str,
        reason: Optional[str] = None,
    ) -> Bed:
        """
        Core state machine method.
        Always use this — never set bed.status directly elsewhere.
        Validates transition, commits, publishes WebSocket event.
        """
        # Row-level lock to prevent concurrent transitions
        result = await self.db.execute(
            select(Bed).where(Bed.id == bed_id).with_for_update()
        )
        bed = result.scalar_one_or_none()
        if not bed:
            raise ValueError(f"Bed {bed_id} not found")

        allowed = VALID_TRANSITIONS.get(bed.status, [])
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition bed {bed_id}: "
                f"{bed.status.value} → {new_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        old_status = bed.status
        bed.status = new_status
        bed.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(bed)

        logger.info(
            "bed_transition",
            extra={
                "bed_id": bed_id,
                "bed_number": bed.bed_number,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "employee_id": employee_id,
                "reason": reason,
            },
        )

        await self._publish_bed_event(bed, old_status, employee_id, reason)

        # Auto-trigger cleaning when bed goes POST_USE
        if new_status == BedStatus.POST_USE:
            await self._initiate_auto_cleaning(bed)

        return bed

    # ─────────────────────────────────────────
    # ALLOCATION (called by Transaction Engine)
    # ─────────────────────────────────────────

    async def tentative_hold(self, bed_id: str, transaction_id: str) -> Bed:
        """
        Called by 2PC PREPARE phase.
        Moves bed READY → TENTATIVE_HOLD.
        TTL is enforced by APScheduler — same as bundle TTL.
        """
        bed = await self.transition_status(
            bed_id,
            BedStatus.TENTATIVE_HOLD,
            employee_id="SYSTEM",
            reason=f"2PC_PREPARE:{transaction_id}",
        )

        # Store in Redis so TTL expiry can find it
        if self.redis:
            try:
                await self.redis.set(
                    f"bed_hold:{bed_id}",
                    json.dumps({"bed_id": bed_id, "transaction_id": transaction_id}),
                    ex=30,  # 30-second TTL — match your bundle TTL
                )
            except Exception as e:
                logger.warning(f"Failed to set bed hold in Redis for {bed_id}: {e}")

        return bed

    async def release_tentative_hold(
        self, bed_id: str, reason: str = "ROLLBACK"
    ) -> Bed:
        """
        Called by 2PC ROLLBACK or TTL expiry.
        Moves bed TENTATIVE_HOLD → READY.
        """
        if self.redis:
            try:
                await self.redis.delete(f"bed_hold:{bed_id}")
            except Exception as e:
                logger.warning(f"Failed to delete bed hold in Redis for {bed_id}: {e}")

        return await self.transition_status(
            bed_id,
            BedStatus.READY,
            employee_id="SYSTEM",
            reason=reason,
        )

    async def commit_allocation(
        self,
        bed_id: str,
        patient_id: str,
        transaction_id: str,
        employee_id: str,
    ) -> Bed:
        """
        Called by Transaction Engine after 2PC COMMIT.
        Moves bed TENTATIVE_HOLD → LOCKED, records assignment.
        """
        bed = await self.transition_status(
            bed_id,
            BedStatus.LOCKED,
            employee_id=employee_id,
            reason=f"2PC_COMMIT:{transaction_id}",
        )

        # Record the assignment
        assignment = BedAssignment(
            bed_id=bed_id,
            patient_id=patient_id,
            transaction_id=transaction_id,
            assigned_by=employee_id,
        )
        self.db.add(assignment)

        # Update bed occupancy
        bed.current_patient_id = patient_id
        bed.current_transaction_id = transaction_id

        await self.db.commit()
        await self.db.refresh(bed)

        # Move to IN_USE (patient is physically placed)
        return await self.transition_status(
            bed_id,
            BedStatus.IN_USE,
            employee_id=employee_id,
            reason="PATIENT_PLACED",
        )

    # ─────────────────────────────────────────
    # RELEASE
    # ─────────────────────────────────────────

    async def release_bed(
        self,
        bed_id: str,
        release_reason: str,
        released_by: str,
    ) -> Bed:
        """
        Called on patient discharge, transfer, or expiry.
        Closes assignment record, triggers POST_USE → CLEANING flow.
        """
        # Close the open assignment record
        result = await self.db.execute(
            select(BedAssignment).where(
                BedAssignment.bed_id == bed_id,
                BedAssignment.released_at.is_(None),
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            assignment.released_at = datetime.now(timezone.utc)
            assignment.release_reason = release_reason

        # Clear occupancy on bed
        bed_result = await self.db.execute(
            select(Bed).where(Bed.id == bed_id).with_for_update()
        )
        bed = bed_result.scalar_one()
        bed.current_patient_id = None
        bed.current_transaction_id = None
        await self.db.commit()

        # POST_USE → auto-triggers cleaning
        return await self.transition_status(
            bed_id,
            BedStatus.POST_USE,
            employee_id=released_by,
            reason=release_reason,
        )

    # ─────────────────────────────────────────
    # CLEANING WORKFLOW
    # ─────────────────────────────────────────

    async def start_cleaning(
        self,
        bed_id: str,
        cleaned_by: str,
        estimated_minutes: Optional[int] = None,
    ) -> BedCleaningLog:
        """Housekeeping staff marks cleaning started."""
        bed_result = await self.db.execute(select(Bed).where(Bed.id == bed_id))
        bed = bed_result.scalar_one()

        bed_type_val = (
            bed.bed_type.value if hasattr(bed.bed_type, "value") else str(bed.bed_type)
        )
        duration = estimated_minutes or CLEANING_DURATION.get(bed_type_val, 20)
        bed.estimated_ready_at = datetime.now(timezone.utc) + timedelta(minutes=duration)
        bed.status = BedStatus.CLEANING

        log = BedCleaningLog(
            bed_id=bed_id,
            cleaned_by=cleaned_by,
            status="IN_PROGRESS",
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)

        if self.redis:
            try:
                await self.redis.publish(
                    "bed_updates",
                    json.dumps(
                        {
                            "event": "CLEANING_STARTED",
                            "bed_id": bed_id,
                            "bed_number": bed.bed_number,
                            "estimated_ready_at": bed.estimated_ready_at.isoformat()
                            if bed.estimated_ready_at
                            else None,
                            "cleaned_by": cleaned_by,
                        }
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to publish cleaning started to Redis: {e}")

        logger.info(f"Cleaning started for bed {bed_id} by {cleaned_by}")
        return log

    async def complete_cleaning(
        self,
        cleaning_log_id: str,
        verified_by: str,
        notes: Optional[str] = None,
    ) -> Bed:
        """
        Housekeeping verifies cleaning is done.
        Bed transitions CLEANING → SANITIZED → READY.
        WebSocket event fires — dashboard updates instantly.
        """
        log_result = await self.db.execute(
            select(BedCleaningLog).where(BedCleaningLog.id == cleaning_log_id)
        )
        log = log_result.scalar_one()
        now_dt = datetime.now(timezone.utc)
        log.completed_at = now_dt
        log.verified_at = now_dt
        log.verified_by = verified_by
        log.status = "VERIFIED"
        log.notes = notes

        bed_result = await self.db.execute(
            select(Bed).where(Bed.id == log.bed_id).with_for_update()
        )
        bed = bed_result.scalar_one()
        bed.last_cleaned_at = now_dt
        bed.last_verified_at = now_dt
        bed.estimated_ready_at = None
        bed.status = BedStatus.READY

        await self.db.commit()
        await self.db.refresh(bed)

        await self._publish_bed_event(
            bed, BedStatus.CLEANING, verified_by, "CLEANING_VERIFIED"
        )

        bed_type_val = (
            bed.bed_type.value if hasattr(bed.bed_type, "value") else str(bed.bed_type)
        )
        # Check shortage — maybe this newly READY bed resolves an alert
        await self._check_and_update_shortage(bed_type_val)

        logger.info(f"Bed {bed.id} ({bed.bed_number}) is now READY after cleaning")
        return bed

    # ─────────────────────────────────────────
    # MAINTENANCE
    # ─────────────────────────────────────────

    async def set_maintenance(
        self,
        bed_id: str,
        reason: str,
        employee_id: str,
    ) -> Bed:
        bed_result = await self.db.execute(
            select(Bed).where(Bed.id == bed_id).with_for_update()
        )
        bed = bed_result.scalar_one()
        bed.maintenance_reason = reason
        bed.maintenance_started_at = datetime.now(timezone.utc)
        await self.db.commit()

        return await self.transition_status(
            bed_id,
            BedStatus.MAINTENANCE,
            employee_id=employee_id,
            reason=reason,
        )

    async def resolve_maintenance(self, bed_id: str, employee_id: str) -> Bed:
        """Maintenance done → start cleaning → eventually READY."""
        return await self.transition_status(
            bed_id,
            BedStatus.CLEANING,
            employee_id=employee_id,
            reason="MAINTENANCE_RESOLVED",
        )

    # ─────────────────────────────────────────
    # INTERNAL HELPERS
    # ─────────────────────────────────────────

    async def _initiate_auto_cleaning(self, bed: Bed):
        """Auto-triggered when bed goes POST_USE."""
        bed_type_val = (
            bed.bed_type.value if hasattr(bed.bed_type, "value") else str(bed.bed_type)
        )
        duration = CLEANING_DURATION.get(bed_type_val, 20)
        bed.estimated_ready_at = datetime.now(timezone.utc) + timedelta(minutes=duration)
        bed.status = BedStatus.CLEANING

        log = BedCleaningLog(
            bed_id=bed.id,
            cleaned_by="SYSTEM_AUTO",
            status="IN_PROGRESS",
        )
        self.db.add(log)
        await self.db.commit()

        if self.redis:
            try:
                await self.redis.publish(
                    "bed_updates",
                    json.dumps(
                        {
                            "event": "AUTO_CLEANING_TRIGGERED",
                            "bed_id": bed.id,
                            "bed_number": bed.bed_number,
                            "estimated_ready_at": bed.estimated_ready_at.isoformat()
                            if bed.estimated_ready_at
                            else None,
                        }
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to publish auto cleaning to Redis: {e}")

    async def _publish_bed_event(
        self,
        bed: Bed,
        old_status: Optional[BedStatus],
        changed_by: str,
        reason: Optional[str],
    ):
        """Publishes to Redis pub/sub → WebSocket → Frontend."""
        if not self.redis:
            return

        bed_type_val = (
            bed.bed_type.value if hasattr(bed.bed_type, "value") else str(bed.bed_type)
        )
        old_status_val = (
            old_status.value
            if old_status and hasattr(old_status, "value")
            else str(old_status)
            if old_status
            else None
        )
        new_status_val = (
            bed.status.value if hasattr(bed.status, "value") else str(bed.status)
        )

        payload = {
            "event": "BED_STATUS_CHANGED",
            "bed_id": bed.id,
            "bed_number": bed.bed_number,
            "ward": bed.ward,
            "bed_type": bed_type_val,
            "floor": bed.floor,
            "room_number": bed.room_number,
            "old_status": old_status_val,
            "new_status": new_status_val,
            "current_patient_id": bed.current_patient_id,
            "estimated_ready_at": bed.estimated_ready_at.isoformat()
            if bed.estimated_ready_at
            else None,
            "changed_by": changed_by,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.redis.publish("bed_updates", json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to publish bed event to Redis: {e}")

    async def _check_and_update_shortage(self, bed_type: str):
        """
        After every status change, check if shortage alert needs to
        be raised or cleared. Publishes to 'shortage_alerts' channel.
        """
        ready_count_result = await self.db.execute(
            select(func.count()).where(
                Bed.bed_type == bed_type, Bed.status == BedStatus.READY
            )
        )
        count = ready_count_result.scalar() or 0
        threshold = CRITICAL_THRESHOLD.get(bed_type, 2)
        is_critical = count < threshold

        if self.redis:
            try:
                await self.redis.publish(
                    "shortage_alerts",
                    json.dumps(
                        {
                            "resource_type": f"BED_{bed_type}",
                            "ready_count": count,
                            "threshold": threshold,
                            "is_critical": is_critical,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to publish shortage alert to Redis: {e}")
