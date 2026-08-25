import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.bed import BedService, InvalidTransitionError
from app.models.models import BedStatus


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    redis_client = AsyncMock()
    return redis_client


@pytest.fixture
def bed_service(mock_db, mock_redis):
    return BedService(db=mock_db, redis_client=mock_redis)


@pytest.mark.parametrize("from_status,to_status,should_pass", [
    (BedStatus.FREE,           BedStatus.CLEANING,       True),
    (BedStatus.CLEANING,       BedStatus.SANITIZED,      True),
    (BedStatus.SANITIZED,      BedStatus.READY,          True),
    (BedStatus.READY,          BedStatus.TENTATIVE_HOLD, True),
    (BedStatus.TENTATIVE_HOLD, BedStatus.LOCKED,         True),
    (BedStatus.LOCKED,         BedStatus.IN_USE,         True),
    (BedStatus.IN_USE,         BedStatus.POST_USE,       True),
    (BedStatus.POST_USE,       BedStatus.CLEANING,       True),
    # Invalid transitions
    (BedStatus.FREE,           BedStatus.IN_USE,         False),   # skip state
    (BedStatus.READY,          BedStatus.IN_USE,         False),   # skip LOCKED
    (BedStatus.IN_USE,         BedStatus.READY,          False),   # backward jump
    (BedStatus.LOCKED,         BedStatus.FREE,           False),   # invalid backward
])
async def test_state_transitions(bed_service, from_status, to_status, should_pass):
    mock_bed = MagicMock()
    mock_bed.id = "BED-TEST01"
    mock_bed.status = from_status
    mock_bed.bed_type = MagicMock(value="GENERAL")
    mock_bed.bed_number = "GW-01"
    mock_bed.floor = 1

    bed_service.db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_bed))
    bed_service.db.commit = AsyncMock()
    bed_service.db.refresh = AsyncMock()
    bed_service.redis.publish = AsyncMock()
    bed_service.db.add = MagicMock()

    if should_pass:
        await bed_service.transition_status("BED-TEST01", to_status, "EMP-001")
        if to_status == BedStatus.POST_USE:
            assert mock_bed.status in (BedStatus.POST_USE, BedStatus.CLEANING)
        else:
            assert mock_bed.status == to_status
    else:
        with pytest.raises(InvalidTransitionError):
            await bed_service.transition_status("BED-TEST01", to_status, "EMP-001")


async def test_post_use_triggers_cleaning(bed_service):
    """POST_USE transition should auto-trigger cleaning."""
    mock_bed = MagicMock(
        id="BED-ICU01",
        status=BedStatus.IN_USE,
        bed_type=MagicMock(value="ICU"),
        bed_number="ICU-01",
        floor=2,
    )
    bed_service.db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_bed))
    bed_service.db.commit = AsyncMock()
    bed_service.db.refresh = AsyncMock()
    bed_service.redis.publish = AsyncMock()
    bed_service.db.add = MagicMock()

    await bed_service.transition_status("BED-ICU01", BedStatus.POST_USE, "EMP-001")

    # Cleaning log should have been created
    bed_service.db.add.assert_called_once()
    assert mock_bed.status == BedStatus.CLEANING


async def test_only_ready_beds_allocatable(bed_service):
    """get_ready_beds must return only READY beds."""
    mock_beds = [
        MagicMock(status=BedStatus.READY, bed_type=MagicMock(value="ICU")),
        MagicMock(status=BedStatus.CLEANING, bed_type=MagicMock(value="ICU")),
        MagicMock(status=BedStatus.IN_USE, bed_type=MagicMock(value="ICU")),
    ]

    # Only first one should be returned
    bed_service.db.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [mock_beds[0]])))
    )
    result = await bed_service.get_ready_beds("ICU")
    assert len(result) == 1
    assert result[0].status == BedStatus.READY
