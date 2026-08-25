"""
DiagnosticsSchedulingService — duration-bound and schedule-based diagnostic equipment allocator.

Responsibilities:
  • Time-window overlap checking & scheduling
  • Next-free-window finder
  • Appointment lifecycle: PENDING_CONFIRM -> CONFIRMED -> IN_PROGRESS -> COMPLETED
  • Contrast agent reservation cascade (Feature #13 integration)
  • Calibration schedule & readiness checking
  • Automatic TTL rollback & No-Show sweeps
  • WebSocket event publishing
"""

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.diagnostics import (
    AppointmentStatus,
    DiagnosticAppointment,
    DiagnosticEquipment,
    DiagnosticResourceType,
    EquipmentStatus,
)
from app.models.pharmacy import PharmacyResource, PharmacyReservationStatus
from app.services.audit import create_audit_event
from app.services.pharmacy import PharmacyService

logger = logging.getLogger(__name__)

DIAGNOSTIC_RESOURCE_TYPES = {
    "DIAGNOSTIC_MRI",
    "DIAGNOSTIC_CT",
    "DIAGNOSTIC_XRAY",
}


class WindowConflictError(Exception):
    """Raised when a requested diagnostic window overlaps with existing bookings."""
    def __init__(self, message: str, conflicts: List[Dict[str, Any]], next_free_window: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.conflicts = conflicts
        self.next_free_window = next_free_window


class EquipmentNotReadyError(Exception):
    """Raised when diagnostic equipment is offline, in maintenance, or calibration due."""
    pass


class DiagnosticsSchedulingService:

    def __init__(
        self,
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis] = None,
    ):
        self.db = db
        self.redis = redis_client

    # ─────────────────────────────────────────
    # OVERLAP CHECKING & NEXT-FREE WINDOW
    # ─────────────────────────────────────────

    async def check_window_overlap(
        self,
        equipment_id: uuid.UUID,
        start: datetime,
        end: datetime,
        exclude_appointment_id: Optional[uuid.UUID] = None,
    ) -> List[DiagnosticAppointment]:
        """
        Returns all appointments for equipment_id in active states that overlap [start, end].
        Overlap condition: appointment.scheduled_start < end AND appointment.scheduled_end > start
        """
        stmt = (
            select(DiagnosticAppointment)
            .where(
                DiagnosticAppointment.equipment_id == equipment_id,
                DiagnosticAppointment.status.in_([
                    AppointmentStatus.PENDING_CONFIRM.value,
                    AppointmentStatus.CONFIRMED.value,
                    AppointmentStatus.IN_PROGRESS.value,
                ]),
                DiagnosticAppointment.scheduled_start < end,
                DiagnosticAppointment.scheduled_end > start,
            )
        )
        if exclude_appointment_id:
            stmt = stmt.where(DiagnosticAppointment.id != exclude_appointment_id)

        stmt = stmt.order_by(DiagnosticAppointment.scheduled_start.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_next_free_window(
        self,
        equipment_id: uuid.UUID,
        duration_minutes: int,
        after: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Scans diagnostic_appointments for the earliest gap >= duration_minutes after `after`.
        """
        now_utc = datetime.now(timezone.utc)
        start_search = after if after and after >= now_utc else now_utc

        # Round up start_search to nearest 5 minutes
        minute_mod = start_search.minute % 5
        if minute_mod != 0:
            start_search = start_search + timedelta(minutes=(5 - minute_mod))
        start_search = start_search.replace(second=0, microsecond=0)

        # Get all future active bookings
        stmt = (
            select(DiagnosticAppointment)
            .where(
                DiagnosticAppointment.equipment_id == equipment_id,
                DiagnosticAppointment.status.in_([
                    AppointmentStatus.PENDING_CONFIRM.value,
                    AppointmentStatus.CONFIRMED.value,
                    AppointmentStatus.IN_PROGRESS.value,
                ]),
                DiagnosticAppointment.scheduled_end > start_search,
            )
            .order_by(DiagnosticAppointment.scheduled_start.asc())
        )
        result = await self.db.execute(stmt)
        bookings = list(result.scalars().all())

        candidate_start = start_search
        required_duration = timedelta(minutes=duration_minutes)

        for b in bookings:
            # Check gap between candidate_start and b.scheduled_start
            b_start = b.scheduled_start if b.scheduled_start.tzinfo else b.scheduled_start.replace(tzinfo=timezone.utc)
            b_end = b.scheduled_end if b.scheduled_end.tzinfo else b.scheduled_end.replace(tzinfo=timezone.utc)

            if b_start > candidate_start:
                gap = b_start - candidate_start
                if gap >= required_duration:
                    return {
                        "scheduled_start": candidate_start.isoformat(),
                        "scheduled_end": (candidate_start + required_duration).isoformat(),
                        "duration_minutes": duration_minutes,
                    }
            # Move candidate start past this booking if needed
            if b_end > candidate_start:
                candidate_start = b_end

        # No gap found within existing bookings, candidate_start is immediately after last booking
        return {
            "scheduled_start": candidate_start.isoformat(),
            "scheduled_end": (candidate_start + required_duration).isoformat(),
            "duration_minutes": duration_minutes,
        }

    # ─────────────────────────────────────────
    # READINESS ENGINE INTEGRATION
    # ─────────────────────────────────────────

    async def check_equipment_readiness(
        self,
        equipment_id: uuid.UUID,
        start: datetime,
        end: datetime,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Evaluates machine readiness:
          1. Calibration not overdue (now < calibration_due_at)
          2. Machine not in MAINTENANCE / OFFLINE / CALIBRATING
          3. No overlapping appointment in requested window
        Returns (is_ready, reason, next_free_window_if_conflict)
        """
        now_utc = datetime.now(timezone.utc)
        stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == equipment_id)
        result = await self.db.execute(stmt)
        equipment = result.scalar_one_or_none()

        if not equipment:
            return False, "EQUIPMENT_NOT_FOUND", None

        cal_due = (
            equipment.calibration_due_at
            if equipment.calibration_due_at.tzinfo
            else equipment.calibration_due_at.replace(tzinfo=timezone.utc)
        )
        if now_utc >= cal_due:
            return False, "CALIBRATION_DUE", None

        if equipment.status in [
            EquipmentStatus.MAINTENANCE.value,
            EquipmentStatus.OFFLINE.value,
            EquipmentStatus.CALIBRATING.value,
        ]:
            return False, equipment.status, None

        overlaps = await self.check_window_overlap(equipment_id, start, end)
        if overlaps:
            duration_min = int((end - start).total_seconds() / 60)
            next_free = await self.find_next_free_window(equipment_id, duration_min, after=now_utc)
            return False, "WINDOW_CONFLICT", next_free

        return True, "READY", None

    # ─────────────────────────────────────────
    # APPOINTMENT ALLOCATION & LIFECYCLE
    # ─────────────────────────────────────────

    async def request_appointment(
        self,
        equipment_id: uuid.UUID,
        tx_id: str,
        patient_id: str,
        start: datetime,
        end: datetime,
        ttl_seconds: int = 30,
    ) -> Dict[str, Any]:
        """
        Atomic appointment hold (PENDING_CONFIRM):
          1. Lock equipment row
          2. Verify readiness & check overlap
          3. Cascade contrast reservation if requires_contrast = True
          4. Insert diagnostic_appointments row with hold_ttl_expires_at
          5. Publish WebSocket update & log audit event
        """
        now_utc = datetime.now(timezone.utc)

        # Lock equipment
        stmt = (
            select(DiagnosticEquipment)
            .where(DiagnosticEquipment.id == equipment_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        equipment = result.scalar_one_or_none()

        if not equipment:
            raise ValueError(f"Diagnostic equipment {equipment_id} not found")

        # Check calibration
        cal_due = (
            equipment.calibration_due_at
            if equipment.calibration_due_at.tzinfo
            else equipment.calibration_due_at.replace(tzinfo=timezone.utc)
        )
        if now_utc >= cal_due:
            raise EquipmentNotReadyError(
                f"Equipment {equipment.equipment_code} calibration overdue (due {equipment.calibration_due_at})"
            )

        if equipment.status in [
            EquipmentStatus.MAINTENANCE.value,
            EquipmentStatus.OFFLINE.value,
            EquipmentStatus.CALIBRATING.value,
        ]:
            raise EquipmentNotReadyError(
                f"Equipment {equipment.equipment_code} is currently {equipment.status}"
            )

        # Check window overlap
        overlaps = await self.check_window_overlap(equipment_id, start, end)
        if overlaps:
            conflict_details = [
                {
                    "appointment_id": str(o.id),
                    "tx_id": o.tx_id,
                    "scheduled_start": o.scheduled_start.isoformat(),
                    "scheduled_end": o.scheduled_end.isoformat(),
                    "status": o.status,
                }
                for o in overlaps
            ]
            duration_min = int((end - start).total_seconds() / 60)
            next_free = await self.find_next_free_window(equipment_id, duration_min, after=now_utc)
            raise WindowConflictError(
                f"Window {start.isoformat()} to {end.isoformat()} conflicts with {len(overlaps)} existing booking(s)",
                conflicts=conflict_details,
                next_free_window=next_free,
            )

        # Contrast agent cascade if required
        contrast_reservation_id = None
        if equipment.requires_contrast:
            contrast_res = await self._reserve_contrast_agent(tx_id, ttl_seconds)
            if contrast_res:
                contrast_reservation_id = uuid.UUID(contrast_res["reservation_id"])
            else:
                logger.warning(
                    f"Equipment {equipment.equipment_code} requires contrast dye but none could be reserved for TX {tx_id}"
                )

        # Create appointment
        appointment_id = uuid.uuid4()
        ttl_expires = now_utc + timedelta(seconds=ttl_seconds)

        appointment = DiagnosticAppointment(
            id=appointment_id,
            tx_id=tx_id,
            equipment_id=equipment_id,
            patient_id=patient_id,
            scheduled_start=start,
            scheduled_end=end,
            status=AppointmentStatus.PENDING_CONFIRM.value,
            hold_ttl_expires_at=ttl_expires,
            contrast_reservation_id=contrast_reservation_id,
            created_at=now_utc,
            updated_at=now_utc,
        )
        self.db.add(appointment)
        await self.db.flush()

        # Audit
        await create_audit_event(
            db=self.db,
            event_type="SCAN_SCHEDULED",
            tx_id=tx_id,
            detail={
                "appointment_id": str(appointment_id),
                "equipment_code": equipment.equipment_code,
                "resource_type": equipment.resource_type,
                "scheduled_start": start.isoformat(),
                "scheduled_end": end.isoformat(),
                "contrast_reservation_id": str(contrast_reservation_id) if contrast_reservation_id else None,
            },
        )

        # Publish realtime update
        await self._publish_equipment_update(equipment, "SCAN_SCHEDULED")

        return {
            "appointment_id": str(appointment_id),
            "equipment_id": str(equipment_id),
            "equipment_code": equipment.equipment_code,
            "tx_id": tx_id,
            "patient_id": patient_id,
            "scheduled_start": start.isoformat(),
            "scheduled_end": end.isoformat(),
            "status": AppointmentStatus.PENDING_CONFIRM.value,
            "hold_ttl_expires_at": ttl_expires.isoformat(),
            "contrast_reserved": contrast_reservation_id is not None,
            "contrast_reservation_id": str(contrast_reservation_id) if contrast_reservation_id else None,
        }

    async def confirm_appointment(self, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        Confirms appointment (PENDING_CONFIRM -> CONFIRMED).
        2PC commit path.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(DiagnosticAppointment)
            .where(DiagnosticAppointment.id == appointment_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        appointment = result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {appointment_id} not found")

        if appointment.status != AppointmentStatus.PENDING_CONFIRM.value:
            raise ValueError(
                f"Appointment {appointment_id} is in status '{appointment.status}', expected PENDING_CONFIRM"
            )

        appointment.status = AppointmentStatus.CONFIRMED.value
        appointment.updated_at = now_utc

        # Get equipment for publishing
        eq_stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == appointment.equipment_id)
        eq_res = await self.db.execute(eq_stmt)
        equipment = eq_res.scalar_one()

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="SCAN_CONFIRMED",
            tx_id=appointment.tx_id,
            detail={
                "appointment_id": str(appointment_id),
                "equipment_code": equipment.equipment_code,
                "scheduled_start": appointment.scheduled_start.isoformat(),
                "scheduled_end": appointment.scheduled_end.isoformat(),
            },
        )

        await self._publish_equipment_update(equipment, "SCAN_CONFIRMED")

        return {
            "appointment_id": str(appointment_id),
            "status": AppointmentStatus.CONFIRMED.value,
            "equipment_code": equipment.equipment_code,
        }

    async def cancel_appointment(
        self,
        appointment_id: uuid.UUID,
        reason: str = "MANUAL_CANCEL",
    ) -> Dict[str, Any]:
        """
        Cancels appointment & releases contrast reservation if held.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(DiagnosticAppointment)
            .where(DiagnosticAppointment.id == appointment_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        appointment = result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {appointment_id} not found")

        old_status = appointment.status
        appointment.status = AppointmentStatus.CANCELLED.value
        appointment.updated_at = now_utc

        # Release contrast dye if reserved
        if appointment.contrast_reservation_id:
            try:
                pharmacy_service = PharmacyService(self.db, self.redis)
                await pharmacy_service.release_reservation(
                    appointment.contrast_reservation_id, reason=reason
                )
            except Exception as e:
                logger.warning(f"Could not release contrast reservation {appointment.contrast_reservation_id}: {e}")

        # Re-check equipment status if needed
        eq_stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == appointment.equipment_id)
        eq_res = await self.db.execute(eq_stmt)
        equipment = eq_res.scalar_one()

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="SCAN_CANCELLED",
            tx_id=appointment.tx_id,
            detail={
                "appointment_id": str(appointment_id),
                "equipment_code": equipment.equipment_code,
                "previous_status": old_status,
                "reason": reason,
            },
        )

        await self._publish_equipment_update(equipment, "SCAN_CANCELLED")

        return {
            "appointment_id": str(appointment_id),
            "status": AppointmentStatus.CANCELLED.value,
            "reason": reason,
        }

    async def start_scan(self, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        Starts scan: appointment -> IN_PROGRESS, equipment -> IN_USE.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(DiagnosticAppointment)
            .where(DiagnosticAppointment.id == appointment_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        appointment = result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {appointment_id} not found")

        appointment.status = AppointmentStatus.IN_PROGRESS.value
        appointment.updated_at = now_utc

        eq_stmt = (
            select(DiagnosticEquipment)
            .where(DiagnosticEquipment.id == appointment.equipment_id)
            .with_for_update()
        )
        eq_res = await self.db.execute(eq_stmt)
        equipment = eq_res.scalar_one()
        equipment.status = EquipmentStatus.IN_USE.value
        equipment.updated_at = now_utc

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="SCAN_STARTED",
            tx_id=appointment.tx_id,
            detail={
                "appointment_id": str(appointment_id),
                "equipment_code": equipment.equipment_code,
                "started_at": now_utc.isoformat(),
            },
        )

        await self._publish_equipment_update(equipment, "SCAN_STARTED")

        return {
            "appointment_id": str(appointment_id),
            "status": AppointmentStatus.IN_PROGRESS.value,
            "equipment_status": EquipmentStatus.IN_USE.value,
        }

    async def complete_scan(self, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        Completes scan: appointment -> COMPLETED, equipment -> REPORTING (or READY),
        dispenses contrast dye permanently.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(DiagnosticAppointment)
            .where(DiagnosticAppointment.id == appointment_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        appointment = result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {appointment_id} not found")

        appointment.status = AppointmentStatus.COMPLETED.value
        appointment.updated_at = now_utc

        # Dispense contrast permanently
        if appointment.contrast_reservation_id:
            try:
                pharmacy_service = PharmacyService(self.db, self.redis)
                await pharmacy_service.dispense_reservation(appointment.contrast_reservation_id)
            except Exception as e:
                logger.warning(f"Could not dispense contrast reservation: {e}")

        # Set equipment to REPORTING (transitioning back to READY)
        eq_stmt = (
            select(DiagnosticEquipment)
            .where(DiagnosticEquipment.id == appointment.equipment_id)
            .with_for_update()
        )
        eq_res = await self.db.execute(eq_stmt)
        equipment = eq_res.scalar_one()
        equipment.status = EquipmentStatus.READY.value
        equipment.updated_at = now_utc

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="SCAN_COMPLETED",
            tx_id=appointment.tx_id,
            detail={
                "appointment_id": str(appointment_id),
                "equipment_code": equipment.equipment_code,
                "completed_at": now_utc.isoformat(),
            },
        )

        await self._publish_equipment_update(equipment, "SCAN_COMPLETED")

        return {
            "appointment_id": str(appointment_id),
            "status": AppointmentStatus.COMPLETED.value,
            "equipment_status": equipment.status,
        }

    async def mark_no_show(self, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        Flags appointment as NO_SHOW and releases contrast agent.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(DiagnosticAppointment)
            .where(DiagnosticAppointment.id == appointment_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        appointment = result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {appointment_id} not found")

        appointment.status = AppointmentStatus.NO_SHOW.value
        appointment.updated_at = now_utc

        if appointment.contrast_reservation_id:
            try:
                pharmacy_service = PharmacyService(self.db, self.redis)
                await pharmacy_service.release_reservation(
                    appointment.contrast_reservation_id, reason="NO_SHOW"
                )
            except Exception as e:
                logger.warning(f"Could not release contrast on no-show: {e}")

        eq_stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == appointment.equipment_id)
        eq_res = await self.db.execute(eq_stmt)
        equipment = eq_res.scalar_one()

        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="SCAN_NO_SHOW",
            tx_id=appointment.tx_id,
            detail={
                "appointment_id": str(appointment_id),
                "equipment_code": equipment.equipment_code,
                "scheduled_start": appointment.scheduled_start.isoformat(),
            },
        )

        await self._publish_equipment_update(equipment, "SCAN_NO_SHOW")

        return {
            "appointment_id": str(appointment_id),
            "status": AppointmentStatus.NO_SHOW.value,
        }

    # ─────────────────────────────────────────
    # PREEMPTION (Critical acuity override)
    # ─────────────────────────────────────────

    async def preempt_appointment(
        self,
        target_appointment_id: uuid.UUID,
        preempting_tx_id: str,
        preempting_patient_id: str,
        preempting_acuity: float,
    ) -> Dict[str, Any]:
        """
        Allows higher-acuity transaction to preempt a CONFIRMED (not yet IN_PROGRESS) appointment.
        Preempted appointment is cancelled with reason 'PREEMPTED_BY_CRITICAL_PATIENT'.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(DiagnosticAppointment)
            .where(DiagnosticAppointment.id == target_appointment_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        target = result.scalar_one_or_none()

        if not target:
            raise ValueError(f"Appointment {target_appointment_id} not found")

        if target.status == AppointmentStatus.IN_PROGRESS.value:
            raise ValueError("Cannot preempt an IN_PROGRESS scan (machine physically occupied)")

        if target.status != AppointmentStatus.CONFIRMED.value:
            raise ValueError(f"Target appointment is in state '{target.status}', only CONFIRMED can be preempted")

        # Save window parameters
        start = target.scheduled_start
        end = target.scheduled_end
        equipment_id = target.equipment_id
        old_tx_id = target.tx_id

        # Cancel target appointment
        await self.cancel_appointment(target.id, reason=f"PREEMPTED_BY_TX_{preempting_tx_id}")

        # Allocate to preempting patient
        new_booking = await self.request_appointment(
            equipment_id=equipment_id,
            tx_id=preempting_tx_id,
            patient_id=preempting_patient_id,
            start=start,
            end=end,
        )
        # Auto-confirm new booking
        await self.confirm_appointment(uuid.UUID(new_booking["appointment_id"]))

        duration_min = int((end - start).total_seconds() / 60)
        suggested_next_free = await self.find_next_free_window(equipment_id, duration_min, after=now_utc)

        await create_audit_event(
            db=self.db,
            event_type="SCAN_PREEMPTED",
            tx_id=preempting_tx_id,
            decision="PREEMPT",
            effective_score=preempting_acuity,
            detail={
                "preempted_appointment_id": str(target_appointment_id),
                "preempted_tx_id": old_tx_id,
                "new_appointment_id": new_booking["appointment_id"],
                "suggested_next_free": suggested_next_free,
            },
        )

        return {
            "preempted_appointment_id": str(target_appointment_id),
            "preempted_tx_id": old_tx_id,
            "new_appointment_id": new_booking["appointment_id"],
            "suggested_next_free_window": suggested_next_free,
        }

    # ─────────────────────────────────────────
    # PERIODIC SWEEPS
    # ─────────────────────────────────────────

    async def sweep_expired_appointment_holds(self) -> int:
        """
        Auto-cancels PENDING_CONFIRM appointments past hold_ttl_expires_at.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(DiagnosticAppointment)
            .where(
                DiagnosticAppointment.status == AppointmentStatus.PENDING_CONFIRM.value,
                DiagnosticAppointment.hold_ttl_expires_at < now_utc,
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        expired = list(result.scalars().all())

        count = 0
        for appt in expired:
            await self.cancel_appointment(appt.id, reason="TTL_EXPIRED")
            count += 1

        if count:
            await self.db.flush()
            logger.info(f"Diagnostic appointment TTL sweep: {count} hold(s) expired")

        return count

    async def sweep_no_show_appointments(self, grace_minutes: int = 10) -> int:
        """
        Auto-flags CONFIRMED appointments where scheduled_start + grace_minutes < now and not started.
        """
        now_utc = datetime.now(timezone.utc)
        threshold = now_utc - timedelta(minutes=grace_minutes)

        stmt = (
            select(DiagnosticAppointment)
            .where(
                DiagnosticAppointment.status == AppointmentStatus.CONFIRMED.value,
                DiagnosticAppointment.scheduled_start < threshold,
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        no_shows = list(result.scalars().all())

        count = 0
        for appt in no_shows:
            await self.mark_no_show(appt.id)
            count += 1

        if count:
            await self.db.flush()
            logger.info(f"Diagnostic no-show sweep: {count} appointment(s) marked NO_SHOW")

        return count

    async def check_and_alert_calibrations(self) -> List[str]:
        """
        Checks for equipment nearing calibration (within 24h) or overdue.
        Auto-sets status to CALIBRATING if overdue.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = select(DiagnosticEquipment).with_for_update()
        result = await self.db.execute(stmt)
        all_equipment = list(result.scalars().all())

        alerted = []
        for eq in all_equipment:
            cal_due = (
                eq.calibration_due_at
                if eq.calibration_due_at.tzinfo
                else eq.calibration_due_at.replace(tzinfo=timezone.utc)
            )
            if now_utc >= cal_due and eq.status not in [EquipmentStatus.CALIBRATING.value, EquipmentStatus.OFFLINE.value]:
                eq.status = EquipmentStatus.CALIBRATING.value
                alerted.append(eq.equipment_code)
                await create_audit_event(
                    db=self.db,
                    event_type="EQUIPMENT_CALIBRATION_DUE",
                    detail={"equipment_code": eq.equipment_code, "calibration_due_at": eq.calibration_due_at.isoformat()},
                )
                await self._publish_equipment_update(eq, "CALIBRATION_OVERDUE")

        if alerted:
            await self.db.flush()

        return alerted

    # ─────────────────────────────────────────
    # READ / QUERY OPERATIONS
    # ─────────────────────────────────────────

    async def get_equipment_list(
        self,
        resource_type: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lists equipment with live status and calculated next free window.
        """
        stmt = select(DiagnosticEquipment)
        if resource_type:
            stmt = stmt.where(DiagnosticEquipment.resource_type == resource_type)
        if status_filter:
            stmt = stmt.where(DiagnosticEquipment.status == status_filter)

        stmt = stmt.order_by(DiagnosticEquipment.equipment_code.asc())
        result = await self.db.execute(stmt)
        equipment_list = list(result.scalars().all())

        items = []
        now_utc = datetime.now(timezone.utc)

        for eq in equipment_list:
            next_free = await self.find_next_free_window(eq.id, eq.avg_scan_minutes, after=now_utc)
            items.append({
                "id": str(eq.id),
                "equipment_code": eq.equipment_code,
                "resource_type": eq.resource_type,
                "status": eq.status,
                "avg_scan_minutes": eq.avg_scan_minutes,
                "requires_contrast": eq.requires_contrast,
                "last_calibrated_at": eq.last_calibrated_at.isoformat() if eq.last_calibrated_at else None,
                "calibration_due_at": eq.calibration_due_at.isoformat(),
                "location": eq.location,
                "next_free_window": next_free,
                "created_at": eq.created_at.isoformat() if eq.created_at else None,
                "updated_at": eq.updated_at.isoformat() if eq.updated_at else None,
            })

        return items

    async def get_equipment_availability(
        self,
        equipment_id: uuid.UUID,
        query_date: date,
    ) -> Dict[str, Any]:
        """
        Returns schedule breakdown for a specific equipment and date.
        """
        stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == equipment_id)
        result = await self.db.execute(stmt)
        equipment = result.scalar_one_or_none()
        if not equipment:
            raise ValueError(f"Equipment {equipment_id} not found")

        start_of_day = datetime(query_date.year, query_date.month, query_date.day, 0, 0, 0, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)

        appt_stmt = (
            select(DiagnosticAppointment)
            .where(
                DiagnosticAppointment.equipment_id == equipment_id,
                DiagnosticAppointment.status.in_([
                    AppointmentStatus.PENDING_CONFIRM.value,
                    AppointmentStatus.CONFIRMED.value,
                    AppointmentStatus.IN_PROGRESS.value,
                    AppointmentStatus.COMPLETED.value,
                ]),
                DiagnosticAppointment.scheduled_start < end_of_day,
                DiagnosticAppointment.scheduled_end > start_of_day,
            )
            .order_by(DiagnosticAppointment.scheduled_start.asc())
        )
        appt_res = await self.db.execute(appt_stmt)
        appts = list(appt_res.scalars().all())

        bookings = [
            {
                "appointment_id": str(a.id),
                "tx_id": a.tx_id,
                "patient_id": a.patient_id,
                "scheduled_start": a.scheduled_start.isoformat(),
                "scheduled_end": a.scheduled_end.isoformat(),
                "status": a.status,
            }
            for a in appts
        ]

        return {
            "equipment_id": str(equipment.id),
            "equipment_code": equipment.equipment_code,
            "resource_type": equipment.resource_type,
            "status": equipment.status,
            "date": query_date.isoformat(),
            "bookings": bookings,
        }

    async def update_equipment_status(
        self,
        equipment_id: uuid.UUID,
        new_status: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Admin action: update equipment status (e.g. MAINTENANCE, OFFLINE, CALIBRATING, READY).
        """
        stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == equipment_id).with_for_update()
        result = await self.db.execute(stmt)
        equipment = result.scalar_one_or_none()
        if not equipment:
            raise ValueError(f"Equipment {equipment_id} not found")

        old_status = equipment.status
        equipment.status = new_status
        if new_status == EquipmentStatus.READY.value:
            equipment.last_calibrated_at = datetime.now(timezone.utc)
            equipment.calibration_due_at = datetime.now(timezone.utc) + timedelta(days=30)
        equipment.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        await create_audit_event(
            db=self.db,
            event_type="EQUIPMENT_STATUS_CHANGED",
            detail={
                "equipment_code": equipment.equipment_code,
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason,
            },
        )

        await self._publish_equipment_update(equipment, "STATUS_CHANGED")

        return {
            "equipment_id": str(equipment.id),
            "equipment_code": equipment.equipment_code,
            "status": equipment.status,
        }

    # ─────────────────────────────────────────
    # INTERNAL CONTRAST RESERVATION HELPER
    # ─────────────────────────────────────────

    async def _reserve_contrast_agent(self, tx_id: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
        """
        Finds first available CONTRAST_DYE medication_slot batch and reserves 1 unit.
        """
        stmt = (
            select(PharmacyResource)
            .where(
                PharmacyResource.resource_type == "medication_slot",
                or_(
                    PharmacyResource.sub_type == "CONTRAST_DYE",
                    PharmacyResource.sub_type.ilike("%contrast%"),
                ),
                PharmacyResource.available_quantity > 0,
            )
            .order_by(PharmacyResource.expiry_date.asc())
        )
        result = await self.db.execute(stmt)
        contrast_batch = result.scalars().first()

        if not contrast_batch:
            return None

        pharmacy_service = PharmacyService(self.db, self.redis)
        try:
            return await pharmacy_service.reserve_quantity(
                resource_id=contrast_batch.id,
                tx_id=tx_id,
                quantity=1,
                ttl_seconds=ttl_seconds,
            )
        except Exception as e:
            logger.warning(f"Failed to reserve contrast dye: {e}")
            return None

    # ─────────────────────────────────────────
    # REALTIME PUBLISHING
    # ─────────────────────────────────────────

    async def _publish_equipment_update(
        self,
        equipment: DiagnosticEquipment,
        event_type: str,
    ) -> None:
        if not self.redis:
            return

        payload = {
            "event": "DIAGNOSTICS_EQUIPMENT_UPDATE",
            "event_type": event_type,
            "equipment_id": str(equipment.id),
            "equipment_code": equipment.equipment_code,
            "resource_type": equipment.resource_type,
            "status": equipment.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            msg = json.dumps(payload, default=str)
            await self.redis.publish("diagnostics_updates", msg)
            await self.redis.publish("pubsub:dashboard", msg)
        except Exception as e:
            logger.warning(f"Failed to publish diagnostic equipment event: {e}")
