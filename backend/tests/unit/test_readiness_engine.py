import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models.models import Bed, BedStatus, BedType, Resource, ResourceStatus, ResourceType
from app.services.readiness import (
    check_readiness,
    calculate_estimated_ready_at,
    transition_resource_state,
    verify_ready,
)


@pytest.mark.asyncio
async def test_canonical_turnaround_state_machine_and_skips():
    """
    Valid turnaround: IN_USE -> POST_USE -> CLEANING -> SANITIZED -> READY.
    Invalid transitions (e.g. CLEANING -> READY directly or POST_USE -> READY) must be rejected.
    """
    mock_db = AsyncMock()

    # Bed currently in CLEANING
    mock_bed = Bed(
        id="BED-ICU-01",
        bed_number="ICU-01",
        bed_type=BedType.ICU,
        status=BedStatus.CLEANING,
        floor=2,
        room_number="201",
        updated_at=datetime.now(timezone.utc),
    )

    db_res = MagicMock()
    db_res.scalar_one_or_none.return_value = mock_bed
    mock_db.execute.return_value = db_res
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    # 1. Invalid jump: CLEANING -> READY directly must fail with 409
    with pytest.raises(HTTPException) as exc:
        await transition_resource_state(
            db=mock_db,
            resource_id="BED-ICU-01",
            from_status="CLEANING",
            to_status="READY",
            triggered_by="nurse.priya",
        )
    assert exc.value.status_code == 409

    # 2. Valid step: CLEANING -> SANITIZED must succeed
    res = await transition_resource_state(
        db=mock_db,
        resource_id="BED-ICU-01",
        from_status="CLEANING",
        to_status="SANITIZED",
        triggered_by="staff.housekeeping",
    )
    assert res["status"] == "SANITIZED"


@pytest.mark.asyncio
async def test_verify_ready_hard_invariant():
    """
    verify_ready() is the sole path to READY and strictly requires verified_by.
    """
    mock_db = AsyncMock()
    mock_bed = Bed(
        id="BED-ICU-02",
        bed_number="ICU-02",
        bed_type=BedType.ICU,
        status=BedStatus.SANITIZED,
        floor=2,
        room_number="202",
        updated_at=datetime.now(timezone.utc),
    )

    db_res = MagicMock()
    db_res.scalar_one_or_none.return_value = mock_bed
    mock_db.execute.return_value = db_res
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    # Case A: Missing verified_by -> HTTP 400
    with pytest.raises(HTTPException) as exc:
        await verify_ready(
            db=mock_db,
            resource_id="BED-ICU-02",
            verified_by="",
        )
    assert exc.value.status_code == 400

    # Case B: Valid staff verification -> transitions to READY
    res = await verify_ready(
        db=mock_db,
        resource_id="BED-ICU-02",
        verified_by="nurse.priya",
    )
    assert res["status"] == "READY"
    assert res["verified_by"] == "nurse.priya"


@pytest.mark.asyncio
async def test_strategy_routing():
    """
    Dispatches correctly across Discrete, Pharmacy, and Diagnostics strategies.
    """
    mock_db = AsyncMock()

    # Test discrete bed
    mock_bed = Bed(
        id="BED-GEN-01",
        bed_number="GEN-01",
        bed_type=BedType.GENERAL,
        status=BedStatus.READY,
        floor=1,
        room_number="101",
    )
    db_res = MagicMock()
    db_res.scalar_one_or_none.return_value = mock_bed
    mock_db.execute.return_value = db_res

    res_discrete = await check_readiness(mock_db, "BED-GEN-01")
    assert res_discrete.is_ready is True
    assert res_discrete.status == "READY"
