"""
LabQueueService — throughput-capacity based lab slot and sample lifecycle allocator.

Responsibilities:
  • Sample lifecycle: SAMPLE_COLLECTED -> IN_TRANSIT -> PROCESSING -> RESULT_READY -> RESULT_DELIVERED
  • Capacity gating: current_load vs max_concurrent
  • STAT priority queue jumping for high-acuity patients
  • Automatic queue draining upon result delivery
  • Stuck sample detection
  • WebSocket & Audit event publishing
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy import select, update, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagnostics import (
    LabSample,
    LabSlot,
    LabSlotStatus,
    SamplePriority,
    SampleStatus,
)
from app.services.audit import create_audit_event

logger = logging.getLogger(__name__)

VALID_SAMPLE_TRANSITIONS = {
    SampleStatus.SAMPLE_COLLECTED.value: [SampleStatus.IN_TRANSIT.value, SampleStatus.PROCESSING.value, SampleStatus.REJECTED.value],
    SampleStatus.IN_TRANSIT.value: [SampleStatus.PROCESSING.value, SampleStatus.REJECTED.value],
    SampleStatus.PROCESSING.value: [SampleStatus.RESULT_READY.value, SampleStatus.REJECTED.value],
    SampleStatus.RESULT_READY.value: [SampleStatus.RESULT_DELIVERED.value],
    SampleStatus.RESULT_DELIVERED.value: [],
    SampleStatus.REJECTED.value: [],
}


class LabStationUnavailableError(Exception):
    """Raised when a lab station is offline or in maintenance."""
    pass


class InvalidSampleTransitionError(Exception):
    """Raised when a sample status transition is illegal."""
    pass


class LabQueueService:

    def __init__(
        self,
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis] = None,
    ):
        self.db = db
        self.redis = redis_client

    # ─────────────────────────────────────────
    # SUBMIT SAMPLE (Entry point)
    # ─────────────────────────────────────────

    async def submit_sample(
        self,
        lab_slot_id: uuid.UUID,
        tx_id: str,
        patient_id: str,
        test_type: str,
        priority: str = "ROUTINE",
        turnaround_estimate_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        Submits a lab sample:
          - If capacity available (current_load < max_concurrent): transitions immediately to PROCESSING.
          - Else: queued as SAMPLE_COLLECTED.
          - STAT samples jump queue ahead of ROUTINE samples when capacity frees up.
        """
        now_utc = datetime.now(timezone.utc)

        # Lock lab slot row
        stmt = (
            select(LabSlot)
            .where(LabSlot.id == lab_slot_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        lab_slot = result.scalar_one_or_none()

        if not lab_slot:
            raise ValueError(f"Lab slot {lab_slot_id} not found")

        if lab_slot.status in [LabSlotStatus.MAINTENANCE.value, LabSlotStatus.OFFLINE.value]:
            raise LabStationUnavailableError(
                f"Lab station {lab_slot.lab_station_code} is currently {lab_slot.status}"
            )

        # Determine initial status based on capacity
        priority_upper = (priority or "ROUTINE").upper()
        if lab_slot.current_load < lab_slot.max_concurrent:
            sample_status = SampleStatus.PROCESSING.value
            lab_slot.current_load += 1
            if lab_slot.current_load >= lab_slot.max_concurrent:
                lab_slot.status = LabSlotStatus.AT_CAPACITY.value
        else:
            sample_status = SampleStatus.SAMPLE_COLLECTED.value

        lab_slot.updated_at = now_utc

        sample_id = uuid.uuid4()
        sample = LabSample(
            id=sample_id,
            tx_id=tx_id,
            lab_slot_id=lab_slot_id,
            patient_id=patient_id,
            test_type=test_type,
            status=sample_status,
            priority=priority_upper,
            submitted_at=now_utc,
            turnaround_estimate_minutes=turnaround_estimate_minutes,
            updated_at=now_utc,
        )
        self.db.add(sample)
        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="SAMPLE_SUBMITTED",
            tx_id=tx_id,
            detail={
                "sample_id": str(sample_id),
                "lab_station_code": lab_slot.lab_station_code,
                "test_type": test_type,
                "priority": priority_upper,
                "status": sample_status,
                "current_load": lab_slot.current_load,
                "max_concurrent": lab_slot.max_concurrent,
            },
        )

        await self._publish_lab_update(lab_slot, sample, "SAMPLE_SUBMITTED")

        return {
            "sample_id": str(sample_id),
            "lab_slot_id": str(lab_slot_id),
            "lab_station_code": lab_slot.lab_station_code,
            "tx_id": tx_id,
            "patient_id": patient_id,
            "test_type": test_type,
            "status": sample_status,
            "priority": priority_upper,
            "submitted_at": now_utc.isoformat(),
            "turnaround_estimate_minutes": turnaround_estimate_minutes,
            "current_load": lab_slot.current_load,
            "max_concurrent": lab_slot.max_concurrent,
        }

    # ─────────────────────────────────────────
    # ADVANCE SAMPLE STATUS
    # ─────────────────────────────────────────

    async def advance_sample_status(
        self,
        sample_id: uuid.UUID,
        new_status: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Advances sample state machine.
        If moving out of PROCESSING (to RESULT_READY, RESULT_DELIVERED, or REJECTED),
        frees load on the lab station and promotes next queued sample (STAT first).
        """
        now_utc = datetime.now(timezone.utc)

        stmt = select(LabSample).where(LabSample.id == sample_id).with_for_update()
        result = await self.db.execute(stmt)
        sample = result.scalar_one_or_none()

        if not sample:
            raise ValueError(f"Lab sample {sample_id} not found")

        old_status = sample.status
        allowed = VALID_SAMPLE_TRANSITIONS.get(old_status, [])
        if new_status not in allowed and new_status != old_status:
            raise InvalidSampleTransitionError(
                f"Cannot transition sample from '{old_status}' to '{new_status}'. Allowed: {allowed}"
            )

        sample.status = new_status
        sample.updated_at = now_utc

        if new_status in [SampleStatus.RESULT_READY.value, SampleStatus.RESULT_DELIVERED.value]:
            sample.result_ready_at = now_utc

        # Load adjustment if leaving PROCESSING
        slot_stmt = select(LabSlot).where(LabSlot.id == sample.lab_slot_id).with_for_update()
        slot_res = await self.db.execute(slot_stmt)
        lab_slot = slot_res.scalar_one()

        if old_status == SampleStatus.PROCESSING.value and new_status in [
            SampleStatus.RESULT_READY.value,
            SampleStatus.RESULT_DELIVERED.value,
            SampleStatus.REJECTED.value,
        ]:
            lab_slot.current_load = max(0, lab_slot.current_load - 1)
            if lab_slot.status == LabSlotStatus.AT_CAPACITY.value:
                lab_slot.status = LabSlotStatus.READY.value
            lab_slot.updated_at = now_utc

            # Automatically drain queue for next sample
            await self._promote_next_queued_sample(lab_slot)

        await self.db.flush()

        event_name = "SAMPLE_RESULT_READY" if new_status == SampleStatus.RESULT_READY.value else (
            "SAMPLE_REJECTED" if new_status == SampleStatus.REJECTED.value else "SAMPLE_STATUS_ADVANCED"
        )

        await create_audit_event(
            db=self.db,
            event_type=event_name,
            tx_id=sample.tx_id,
            detail={
                "sample_id": str(sample_id),
                "lab_station_code": lab_slot.lab_station_code,
                "old_status": old_status,
                "new_status": new_status,
                "notes": notes,
            },
        )

        await self._publish_lab_update(lab_slot, sample, event_name)

        return {
            "sample_id": str(sample_id),
            "status": new_status,
            "result_ready_at": sample.result_ready_at.isoformat() if sample.result_ready_at else None,
            "current_load": lab_slot.current_load,
            "max_concurrent": lab_slot.max_concurrent,
        }

    # ─────────────────────────────────────────
    # QUEUE PROMOTION (STAT priority jumps queue)
    # ─────────────────────────────────────────

    async def _promote_next_queued_sample(self, lab_slot: LabSlot) -> Optional[LabSample]:
        """
        Selects next queued sample (STAT first, then oldest submitted_at) and promotes to PROCESSING.
        """
        if lab_slot.current_load >= lab_slot.max_concurrent:
            return None

        # Priority sort: STAT first ('STAT' > 'ROUTINE' alphabetically or via CASE), submitted_at ASC
        stmt = (
            select(LabSample)
            .where(
                LabSample.lab_slot_id == lab_slot.id,
                LabSample.status.in_([
                    SampleStatus.SAMPLE_COLLECTED.value,
                    SampleStatus.IN_TRANSIT.value,
                ]),
            )
            .order_by(
                desc(LabSample.priority == SamplePriority.STAT.value),
                asc(LabSample.submitted_at),
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        next_sample = result.scalars().first()

        if next_sample:
            next_sample.status = SampleStatus.PROCESSING.value
            next_sample.updated_at = datetime.now(timezone.utc)
            lab_slot.current_load += 1
            if lab_slot.current_load >= lab_slot.max_concurrent:
                lab_slot.status = LabSlotStatus.AT_CAPACITY.value

            await create_audit_event(
                db=self.db,
                event_type="SAMPLE_PROCESSING_STARTED",
                tx_id=next_sample.tx_id,
                detail={
                    "sample_id": str(next_sample.id),
                    "priority": next_sample.priority,
                    "promoted_from_queue": True,
                },
            )
            await self._publish_lab_update(lab_slot, next_sample, "SAMPLE_PROMOTED")

        return next_sample

    # ─────────────────────────────────────────
    # READINESS ENGINE INTEGRATION
    # ─────────────────────────────────────────

    async def check_lab_readiness(self, lab_slot_id: uuid.UUID) -> Tuple[bool, str]:
        """
        Lab is ready if status == READY and current_load < max_concurrent.
        """
        stmt = select(LabSlot).where(LabSlot.id == lab_slot_id)
        result = await self.db.execute(stmt)
        slot = result.scalar_one_or_none()

        if not slot:
            return False, "LAB_SLOT_NOT_FOUND"

        if slot.status in [LabSlotStatus.MAINTENANCE.value, LabSlotStatus.OFFLINE.value]:
            return False, slot.status

        if slot.current_load >= slot.max_concurrent:
            return False, "AT_CAPACITY"

        return True, "READY"

    # ─────────────────────────────────────────
    # READ / STATS / QUEUE BREAKDOWN
    # ─────────────────────────────────────────

    async def get_lab_queue(self) -> Dict[str, Any]:
        """
        Returns real-time capacity and sample counts across all lab stations.
        """
        slots_stmt = select(LabSlot).order_by(LabSlot.lab_station_code.asc())
        slots_res = await self.db.execute(slots_stmt)
        slots = list(slots_res.scalars().all())

        samples_stmt = select(LabSample).where(
            LabSample.status.in_([
                SampleStatus.SAMPLE_COLLECTED.value,
                SampleStatus.IN_TRANSIT.value,
                SampleStatus.PROCESSING.value,
                SampleStatus.RESULT_READY.value,
            ])
        ).order_by(
            desc(LabSample.priority == SamplePriority.STAT.value),
            asc(LabSample.submitted_at),
        )
        samples_res = await self.db.execute(samples_stmt)
        active_samples = list(samples_res.scalars().all())

        stations_data = []
        for s in slots:
            station_samples = [sm for sm in active_samples if sm.lab_slot_id == s.id]
            processing_count = sum(1 for sm in station_samples if sm.status == SampleStatus.PROCESSING.value)
            stat_queued = sum(1 for sm in station_samples if sm.priority == "STAT" and sm.status in ["SAMPLE_COLLECTED", "IN_TRANSIT"])
            routine_queued = sum(1 for sm in station_samples if sm.priority == "ROUTINE" and sm.status in ["SAMPLE_COLLECTED", "IN_TRANSIT"])

            stations_data.append({
                "id": str(s.id),
                "lab_station_code": s.lab_station_code,
                "status": s.status,
                "current_load": s.current_load,
                "max_concurrent": s.max_concurrent,
                "utilization_pct": round((s.current_load / s.max_concurrent) * 100, 1) if s.max_concurrent > 0 else 0,
                "processing_count": processing_count,
                "stat_queued_count": stat_queued,
                "routine_queued_count": routine_queued,
                "location": s.location,
            })

        sample_items = [
            {
                "id": str(sm.id),
                "tx_id": sm.tx_id,
                "lab_slot_id": str(sm.lab_slot_id),
                "patient_id": sm.patient_id,
                "test_type": sm.test_type,
                "status": sm.status,
                "priority": sm.priority,
                "submitted_at": sm.submitted_at.isoformat(),
                "result_ready_at": sm.result_ready_at.isoformat() if sm.result_ready_at else None,
                "turnaround_estimate_minutes": sm.turnaround_estimate_minutes,
            }
            for sm in active_samples
        ]

        return {
            "stations": stations_data,
            "samples": sample_items,
            "total_active_samples": len(active_samples),
        }

    # ─────────────────────────────────────────
    # STUCK SAMPLE SWEEP
    # ─────────────────────────────────────────

    async def sweep_stuck_samples(self) -> List[str]:
        """
        Flags PROCESSING samples past 2x turnaround_estimate_minutes.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(LabSample)
            .where(
                LabSample.status == SampleStatus.PROCESSING.value,
            )
        )
        result = await self.db.execute(stmt)
        processing_samples = list(result.scalars().all())

        stuck_ids = []
        for sm in processing_samples:
            est_min = sm.turnaround_estimate_minutes or 30
            threshold = (sm.submitted_at if sm.submitted_at.tzinfo else sm.submitted_at.replace(tzinfo=timezone.utc)) + timedelta(minutes=est_min * 2)
            if now_utc > threshold:
                stuck_ids.append(str(sm.id))
                await create_audit_event(
                    db=self.db,
                    event_type="SAMPLE_PROCESSING_DELAYED",
                    tx_id=sm.tx_id,
                    detail={
                        "sample_id": str(sm.id),
                        "test_type": sm.test_type,
                        "elapsed_minutes": int((now_utc - (sm.submitted_at if sm.submitted_at.tzinfo else sm.submitted_at.replace(tzinfo=timezone.utc))).total_seconds() / 60),
                        "estimate_minutes": est_min,
                    },
                )

        return stuck_ids

    # ─────────────────────────────────────────
    # REALTIME PUBLISHING
    # ─────────────────────────────────────────

    async def _publish_lab_update(
        self,
        slot: LabSlot,
        sample: LabSample,
        event_type: str,
    ) -> None:
        if not self.redis:
            return

        payload = {
            "event": "LAB_QUEUE_UPDATE",
            "event_type": event_type,
            "lab_station_code": slot.lab_station_code,
            "slot_id": str(slot.id),
            "current_load": slot.current_load,
            "max_concurrent": slot.max_concurrent,
            "slot_status": slot.status,
            "sample_id": str(sample.id),
            "test_type": sample.test_type,
            "sample_status": sample.status,
            "priority": sample.priority,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            msg = json.dumps(payload, default=str)
            await self.redis.publish("diagnostics_updates", msg)
            await self.redis.publish("pubsub:dashboard", msg)
        except Exception as e:
            logger.warning(f"Failed to publish lab queue event: {e}")
