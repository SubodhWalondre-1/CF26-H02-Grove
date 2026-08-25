import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.diagnostics import (
    AppointmentStatus,
    DiagnosticAppointment,
    DiagnosticEquipment,
    EquipmentStatus,
)
from app.services.diagnostics_scheduling import (
    DiagnosticsSchedulingService,
    EquipmentNotReadyError,
    WindowConflictError,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def diag_service(mock_db, mock_redis):
    return DiagnosticsSchedulingService(mock_db, mock_redis)


@pytest.mark.asyncio
async def test_overlap_detection_rejects_intersecting_window(diag_service, mock_db):
    """
    Requested: 10:00 - 10:35
    Existing: 10:15 - 10:50 (overlaps)
    Should raise WindowConflictError.
    """
    equipment_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    start_req = now
    end_req = now + timedelta(minutes=35)

    equipment = DiagnosticEquipment(
        id=equipment_id,
        equipment_code="MRI-1",
        resource_type="DIAGNOSTIC_MRI",
        status="READY",
        avg_scan_minutes=35,
        requires_contrast=False,
        calibration_due_at=now + timedelta(days=30),
    )

    conflicting_appt = DiagnosticAppointment(
        id=uuid.uuid4(),
        tx_id="TX-EXISTING",
        equipment_id=equipment_id,
        patient_id="PT-0001",
        scheduled_start=now + timedelta(minutes=15),
        scheduled_end=now + timedelta(minutes=50),
        status="CONFIRMED",
        hold_ttl_expires_at=now + timedelta(minutes=10),
    )

    # First call: get equipment
    # Second call: check overlap (returns conflicting_appt)
    mock_eq_result = MagicMock()
    mock_eq_result.scalar_one_or_none.return_value = equipment

    mock_overlap_result = MagicMock()
    mock_overlap_result.scalars.return_value.all.return_value = [conflicting_appt]

    mock_db.execute.side_effect = [
        mock_eq_result,      # select equipment
        mock_overlap_result, # check_window_overlap
        mock_overlap_result, # find_next_free_window bookings
    ]

    with pytest.raises(WindowConflictError) as exc_info:
        await diag_service.request_appointment(
            equipment_id=equipment_id,
            tx_id="TX-NEW",
            patient_id="PT-0002",
            start=start_req,
            end=end_req,
        )

    assert "conflicts with 1 existing booking" in str(exc_info.value)


@pytest.mark.asyncio
async def test_adjacent_non_overlapping_windows_succeed(diag_service, mock_db):
    """
    Existing: 10:00 - 10:35
    Requested: 10:35 - 11:10 (adjacent, back-to-back, no overlap)
    Should succeed without conflict.
    """
    equipment_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(hour=10, minute=35, second=0, microsecond=0)
    start_req = now
    end_req = now + timedelta(minutes=35)

    equipment = DiagnosticEquipment(
        id=equipment_id,
        equipment_code="MRI-1",
        resource_type="DIAGNOSTIC_MRI",
        status="READY",
        avg_scan_minutes=35,
        requires_contrast=False,
        calibration_due_at=now + timedelta(days=30),
    )

    mock_eq_result = MagicMock()
    mock_eq_result.scalar_one_or_none.return_value = equipment

    mock_overlap_result = MagicMock()
    mock_overlap_result.scalars.return_value.all.return_value = []  # No overlap

    mock_db.execute.side_effect = [
        mock_eq_result,
        mock_overlap_result,
    ]

    result = await diag_service.request_appointment(
        equipment_id=equipment_id,
        tx_id="TX-NEW",
        patient_id="PT-0002",
        start=start_req,
        end=end_req,
    )

    assert result["status"] == "PENDING_CONFIRM"
    assert result["tx_id"] == "TX-NEW"
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_calibration_overdue_rejects_booking(diag_service, mock_db):
    """
    If calibration_due_at is in the past, equipment must report NOT READY.
    """
    equipment_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    equipment = DiagnosticEquipment(
        id=equipment_id,
        equipment_code="CT-1",
        resource_type="DIAGNOSTIC_CT",
        status="READY",
        avg_scan_minutes=10,
        requires_contrast=False,
        calibration_due_at=now - timedelta(days=1),  # Overdue!
    )

    mock_eq_result = MagicMock()
    mock_eq_result.scalar_one_or_none.return_value = equipment
    mock_db.execute.return_value = mock_eq_result

    with pytest.raises(EquipmentNotReadyError) as exc_info:
        await diag_service.request_appointment(
            equipment_id=equipment_id,
            tx_id="TX-NEW",
            patient_id="PT-0001",
            start=now,
            end=now + timedelta(minutes=10),
        )

    assert "calibration overdue" in str(exc_info.value).lower()
