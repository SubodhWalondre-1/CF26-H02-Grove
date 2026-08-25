import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.diagnostics import (
    LabSample,
    LabSlot,
    LabSlotStatus,
    SamplePriority,
    SampleStatus,
)
from app.services.lab_queue import (
    InvalidSampleTransitionError,
    LabQueueService,
    LabStationUnavailableError,
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
def lab_service(mock_db, mock_redis):
    return LabQueueService(mock_db, mock_redis)


@pytest.mark.asyncio
async def test_lab_capacity_under_limit_processes_immediately(lab_service, mock_db):
    """
    Station: max_concurrent=6, current_load=2
    Submitting sample -> immediately set to PROCESSING and load incremented to 3.
    """
    slot_id = uuid.uuid4()
    station = LabSlot(
        id=slot_id,
        lab_station_code="LAB-STATION-1",
        max_concurrent=6,
        current_load=2,
        status="READY",
    )

    mock_slot_result = MagicMock()
    mock_slot_result.scalar_one_or_none.return_value = station
    mock_db.execute.return_value = mock_slot_result

    result = await lab_service.submit_sample(
        lab_slot_id=slot_id,
        tx_id="TX-LAB-01",
        patient_id="PT-0001",
        test_type="CBC",
        priority="ROUTINE",
    )

    assert result["status"] == "PROCESSING"
    assert result["current_load"] == 3
    assert station.current_load == 3


@pytest.mark.asyncio
async def test_lab_capacity_at_limit_queues_sample(lab_service, mock_db):
    """
    Station: max_concurrent=6, current_load=6 (at limit)
    Submitting sample #7 -> queued as SAMPLE_COLLECTED, load stays 6.
    """
    slot_id = uuid.uuid4()
    station = LabSlot(
        id=slot_id,
        lab_station_code="LAB-STATION-1",
        max_concurrent=6,
        current_load=6,
        status="AT_CAPACITY",
    )

    mock_slot_result = MagicMock()
    mock_slot_result.scalar_one_or_none.return_value = station
    mock_db.execute.return_value = mock_slot_result

    result = await lab_service.submit_sample(
        lab_slot_id=slot_id,
        tx_id="TX-LAB-07",
        patient_id="PT-0007",
        test_type="TROPONIN",
        priority="STAT",
    )

    assert result["status"] == "SAMPLE_COLLECTED"
    assert result["current_load"] == 6
    assert station.current_load == 6


@pytest.mark.asyncio
async def test_sample_status_lifecycle_validation(lab_service, mock_db):
    """
    Advancing from PROCESSING to RESULT_READY is valid.
    Illegal jump from SAMPLE_COLLECTED directly to RESULT_DELIVERED must raise InvalidSampleTransitionError.
    """
    sample_id = uuid.uuid4()
    slot_id = uuid.uuid4()

    sample = LabSample(
        id=sample_id,
        tx_id="TX-01",
        lab_slot_id=slot_id,
        patient_id="PT-0001",
        test_type="CBC",
        status="SAMPLE_COLLECTED",
        priority="ROUTINE",
        submitted_at=datetime.now(timezone.utc),
    )

    mock_sample_result = MagicMock()
    mock_sample_result.scalar_one_or_none.return_value = sample
    mock_db.execute.return_value = mock_sample_result

    with pytest.raises(InvalidSampleTransitionError):
        await lab_service.advance_sample_status(
            sample_id=sample_id,
            new_status="RESULT_DELIVERED",
        )
