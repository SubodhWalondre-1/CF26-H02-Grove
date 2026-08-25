"""
Diagnostics & Lab API routes.

Separate router to keep existing routes untouched.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, require_admin
from app.core.redis import get_redis
from app.models.models import User
from app.schemas.schemas import (
    AppointmentCreateRequest,
    AppointmentResponse,
    DiagnosticEquipmentListResponse,
    DiagnosticEquipmentResponse,
    DiagnosticPreemptRequest,
    DiagnosticPreemptResponse,
    EquipmentAvailabilityResponse,
    EquipmentStatusUpdateRequest,
    LabQueueResponse,
    LabSampleResponse,
    LabSampleStatusUpdateRequest,
    LabSampleSubmitRequest,
)
from app.services.diagnostics_scheduling import (
    DiagnosticsSchedulingService,
    EquipmentNotReadyError,
    WindowConflictError,
)
from app.services.lab_queue import (
    InvalidSampleTransitionError,
    LabQueueService,
    LabStationUnavailableError,
)

router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])


# =============================================================================
# 1. LIST EQUIPMENT
# =============================================================================
@router.get(
    "/equipment",
    response_model=DiagnosticEquipmentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List diagnostic equipment with live status and next free window",
)
async def list_diagnostic_equipment(
    resource_type: Optional[str] = Query(None, description="Filter by type (DIAGNOSTIC_MRI, DIAGNOSTIC_CT, DIAGNOSTIC_XRAY)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = DiagnosticsSchedulingService(db, redis)
    items = await service.get_equipment_list(
        resource_type=resource_type,
        status_filter=status_filter,
    )
    return {"items": items, "total": len(items)}


# =============================================================================
# 2. EQUIPMENT AVAILABILITY (Day free/busy)
# =============================================================================
@router.get(
    "/equipment/{equipment_id}/availability",
    response_model=EquipmentAvailabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get day schedule for diagnostic equipment",
)
async def get_equipment_availability(
    equipment_id: str,
    query_date: Optional[str] = Query(None, alias="date", description="Date YYYY-MM-DD (defaults to today)"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = DiagnosticsSchedulingService(db, redis)
    target_date = date.fromisoformat(query_date) if query_date else date.today()
    try:
        data = await service.get_equipment_availability(
            equipment_id=uuid.UUID(equipment_id),
            query_date=target_date,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return data


# =============================================================================
# 3. REQUEST APPOINTMENT (PENDING_CONFIRM)
# =============================================================================
@router.post(
    "/appointments",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a scan window (PENDING_CONFIRM with TTL hold)",
)
async def request_appointment(
    payload: AppointmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = DiagnosticsSchedulingService(db, redis)
    try:
        start_dt = datetime.fromisoformat(payload.scheduled_start)
        end_dt = datetime.fromisoformat(payload.scheduled_end)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timestamp format. Use ISO-8601 (e.g. 2026-08-25T10:00:00Z)",
        )

    try:
        result = await service.request_appointment(
            equipment_id=uuid.UUID(payload.equipment_id),
            tx_id=payload.tx_id,
            patient_id=payload.patient_id,
            start=start_dt,
            end=end_dt,
            ttl_seconds=payload.ttl_seconds,
        )
    except WindowConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WINDOW_CONFLICT",
                "message": str(e),
                "conflicts": e.conflicts,
                "suggested_next_free_window": e.next_free_window,
            },
        )
    except EquipmentNotReadyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    await db.commit()
    return result


# =============================================================================
# 4. CONFIRM APPOINTMENT (2PC Commit)
# =============================================================================
@router.post(
    "/appointments/{appointment_id}/confirm",
    status_code=status.HTTP_200_OK,
    summary="Confirm an appointment within TTL window",
)
async def confirm_appointment(
    appointment_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = DiagnosticsSchedulingService(db, redis)
    try:
        result = await service.confirm_appointment(uuid.UUID(appointment_id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 5. CANCEL APPOINTMENT
# =============================================================================
@router.post(
    "/appointments/{appointment_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a diagnostic appointment and release resources",
)
async def cancel_appointment(
    appointment_id: str,
    reason: str = Query(default="MANUAL_CANCEL"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = DiagnosticsSchedulingService(db, redis)
    try:
        result = await service.cancel_appointment(uuid.UUID(appointment_id), reason=reason)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 6. ADMIN: UPDATE EQUIPMENT STATUS
# =============================================================================
@router.patch(
    "/equipment/{equipment_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Admin: Set equipment to MAINTENANCE / OFFLINE / CALIBRATING / READY",
)
async def update_equipment_status(
    equipment_id: str,
    payload: EquipmentStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _admin: User = Depends(require_admin),
):
    service = DiagnosticsSchedulingService(db, redis)
    try:
        result = await service.update_equipment_status(
            equipment_id=uuid.UUID(equipment_id),
            new_status=payload.status,
            reason=payload.reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 7. PREEMPT APPOINTMENT (High Acuity Override)
# =============================================================================
@router.post(
    "/appointments/preempt",
    response_model=DiagnosticPreemptResponse,
    status_code=status.HTTP_200_OK,
    summary="Preempt a CONFIRMED appointment for a high-acuity critical patient",
)
async def preempt_diagnostic_appointment(
    payload: DiagnosticPreemptRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = DiagnosticsSchedulingService(db, redis)
    try:
        result = await service.preempt_appointment(
            target_appointment_id=uuid.UUID(payload.target_appointment_id),
            preempting_tx_id=payload.preempting_tx_id,
            preempting_patient_id=payload.preempting_patient_id,
            preempting_acuity=payload.preempting_acuity,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 8. SUBMIT LAB SAMPLE
# =============================================================================
@router.post(
    "/lab/samples",
    response_model=LabSampleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a lab sample for processing (STAT priority supported)",
)
async def submit_lab_sample(
    payload: LabSampleSubmitRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = LabQueueService(db, redis)
    try:
        result = await service.submit_sample(
            lab_slot_id=uuid.UUID(payload.lab_slot_id),
            tx_id=payload.tx_id,
            patient_id=payload.patient_id,
            test_type=payload.test_type,
            priority=payload.priority,
            turnaround_estimate_minutes=payload.turnaround_estimate_minutes,
        )
    except LabStationUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 9. ADVANCE LAB SAMPLE STATUS
# =============================================================================
@router.patch(
    "/lab/samples/{sample_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Advance lab sample lifecycle status",
)
async def advance_lab_sample_status(
    sample_id: str,
    payload: LabSampleStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = LabQueueService(db, redis)
    try:
        result = await service.advance_sample_status(
            sample_id=uuid.UUID(sample_id),
            new_status=payload.status,
            notes=payload.notes,
        )
    except InvalidSampleTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    await db.commit()
    return result


# =============================================================================
# 10. GET LAB QUEUE & CAPACITY
# =============================================================================
@router.get(
    "/lab/queue",
    response_model=LabQueueResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current lab load, capacity utilization, and sample queue",
)
async def get_lab_queue(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: User = Depends(get_current_active_user),
):
    service = LabQueueService(db, redis)
    return await service.get_lab_queue()
