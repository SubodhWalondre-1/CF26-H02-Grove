import asyncio
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.diagnostics import (
    DiagnosticAppointment,
    DiagnosticEquipment,
)
from app.services.diagnostics_scheduling import (
    DiagnosticsSchedulingService,
    WindowConflictError,
)


@pytest.mark.asyncio
async def test_concurrent_diagnostic_window_booking_prevents_overlap():
    """
    Simulates concurrent requests for the exact same 35-min MRI slot.
    Overlap detection and row locking ensure no double booking.
    """
    equipment_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slot_start = now + timedelta(hours=1)
    slot_end = slot_start + timedelta(minutes=35)

    booked_appointments = []

    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt)

        # If selecting equipment
        if "diagnostic_equipment" in stmt_str:
            eq = DiagnosticEquipment(
                id=equipment_id,
                equipment_code="MRI-1",
                resource_type="DIAGNOSTIC_MRI",
                status="READY",
                avg_scan_minutes=35,
                requires_contrast=False,
                calibration_due_at=now + timedelta(days=30),
            )
            mock_res.scalar_one_or_none.return_value = eq
            return mock_res

        # If checking overlap
        if "diagnostic_appointments" in stmt_str:
            # Return currently booked appointments
            mock_res.scalars.return_value.all.return_value = list(booked_appointments)
            return mock_res

        return mock_res

    def mock_add(appt):
        booked_appointments.append(appt)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.add = MagicMock(side_effect=mock_add)
    mock_db.flush = AsyncMock()

    service = DiagnosticsSchedulingService(mock_db)

    async def book_slot(req_id: int):
        return await service.request_appointment(
            equipment_id=equipment_id,
            tx_id=f"TX-CONCURRENT-{req_id}",
            patient_id=f"PT-{req_id}",
            start=slot_start,
            end=slot_end,
        )

    # 1st request books successfully
    res1 = await book_slot(1)
    assert res1["status"] == "PENDING_CONFIRM"
    assert len(booked_appointments) == 1

    # 2nd concurrent request for same window must raise WindowConflictError
    with pytest.raises(WindowConflictError):
        await book_slot(2)

    # Total booked must remain exactly 1
    assert len(booked_appointments) == 1
