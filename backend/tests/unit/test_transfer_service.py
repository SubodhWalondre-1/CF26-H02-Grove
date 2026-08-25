import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.models import (
    Bed,
    BedStatus,
    BedType,
    Patient,
    RequestType,
    Resource,
    ResourceStatus,
    Transaction,
    TxState,
)
from app.models.transfer import PatientTransfer, TransferStatus, TransferType
from app.services.transfer import (
    PreflightValidationError,
    TransferDestinationUnavailableError,
    TransferService,
    TransferTransportUnavailableError,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def transfer_service(mock_db, mock_redis):
    return TransferService(mock_db, mock_redis)


@pytest.mark.asyncio
async def test_preflight_fails_if_source_not_occupied_by_patient(transfer_service, mock_db):
    """
    Source bed has patient PT-0002, but transfer requested for PT-0001.
    Must raise PreflightValidationError.
    """
    source_bed = Bed(
        id="BED-ICU-01",
        bed_number="ICU-01",
        ward="ICU",
        bed_type=BedType.ICU,
        status=BedStatus.IN_USE,
        current_patient_id="PT-0002",  # Different patient!
        floor=1,
        room_number="101",
    )

    mock_db.get.return_value = Patient(patient_id="PT-0001", name="Patient A")
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = source_bed
    mock_db.execute.return_value = mock_res

    with pytest.raises(PreflightValidationError) as exc_info:
        await transfer_service.initiate_transfer(
            patient_id="PT-0001",
            source_bed_id="BED-ICU-01",
            destination_bed_id="BED-GEN-01",
        )

    assert "occupied by patient 'PT-0002', not 'PT-0001'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_initiate_fails_if_destination_not_ready(transfer_service, mock_db):
    """
    Destination bed is CLEANING (not READY).
    Must raise TransferDestinationUnavailableError without modifying source bed.
    """
    source_bed = Bed(
        id="BED-ICU-01",
        bed_number="ICU-01",
        ward="ICU",
        bed_type=BedType.ICU,
        status=BedStatus.IN_USE,
        current_patient_id="PT-0001",
        floor=1,
        room_number="101",
    )
    dest_bed = Bed(
        id="BED-GEN-01",
        bed_number="GW-01",
        ward="General Ward",
        bed_type=BedType.GENERAL,
        status=BedStatus.CLEANING,  # NOT READY!
        floor=2,
        room_number="201",
    )

    mock_db.get.return_value = Patient(patient_id="PT-0001", name="Patient A")

    mock_s_res = MagicMock()
    mock_s_res.scalar_one_or_none.return_value = source_bed

    mock_d_res = MagicMock()
    mock_d_res.scalar_one_or_none.return_value = dest_bed

    mock_db.execute.side_effect = [
        mock_s_res,  # source bed select
        mock_d_res,  # dest bed select
    ]

    with pytest.raises(TransferDestinationUnavailableError) as exc_info:
        await transfer_service.initiate_transfer(
            patient_id="PT-0001",
            source_bed_id="BED-ICU-01",
            destination_bed_id="BED-GEN-01",
        )

    assert "expected READY" in str(exc_info.value)
    # Source bed must remain IN_USE
    assert source_bed.status == BedStatus.IN_USE
    assert source_bed.current_patient_id == "PT-0001"


@pytest.mark.asyncio
async def test_happy_path_initiate_and_commit(transfer_service, mock_db):
    """
    Happy path:
      1. Initiate: source -> POST_USE, dest -> TENTATIVE_HOLD
      2. Commit: dest -> IN_USE (patient attached), source -> CLEANING
    """
    source_bed = Bed(
        id="BED-ICU-01",
        bed_number="ICU-01",
        ward="ICU",
        bed_type=BedType.ICU,
        status=BedStatus.IN_USE,
        current_patient_id="PT-0001",
        floor=1,
        room_number="101",
    )
    dest_bed = Bed(
        id="BED-GEN-01",
        bed_number="GW-01",
        ward="General Ward",
        bed_type=BedType.GENERAL,
        status=BedStatus.READY,
        floor=2,
        room_number="201",
    )

    mock_db.get.return_value = Patient(patient_id="PT-0001", name="Patient A")

    mock_s_res = MagicMock()
    mock_s_res.scalar_one_or_none.return_value = source_bed

    mock_d_res = MagicMock()
    mock_d_res.scalar_one_or_none.return_value = dest_bed

    mock_db.execute.side_effect = [
        mock_s_res,
        mock_d_res,
    ]

    # Initiate
    init_res = await transfer_service.initiate_transfer(
        patient_id="PT-0001",
        source_bed_id="BED-ICU-01",
        destination_bed_id="BED-GEN-01",
    )

    assert init_res["status"] == TransferStatus.DESTINATION_HELD.value
    assert source_bed.status == BedStatus.POST_USE
    assert dest_bed.status == BedStatus.TENTATIVE_HOLD

    # Setup for Commit
    tx_id = init_res["tx_id"]
    transfer_record = PatientTransfer(
        id=uuid.uuid4(),
        tx_id=tx_id,
        patient_id="PT-0001",
        source_bed_id="BED-ICU-01",
        destination_bed_id="BED-GEN-01",
        status=TransferStatus.IN_TRANSIT.value,
        hold_ttl_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        initiated_by="dr.mehta",
    )

    mock_t_res = MagicMock()
    mock_t_res.scalar_one_or_none.return_value = transfer_record

    mock_d_scalar = MagicMock()
    mock_d_scalar.scalar_one.return_value = dest_bed

    mock_s_scalar = MagicMock()
    mock_s_scalar.scalar_one_or_none.return_value = source_bed

    mock_tr_res = MagicMock()
    mock_tr_res.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        mock_t_res,     # get transfer
        mock_d_scalar,  # dest bed
        mock_s_scalar,  # source bed
        mock_tr_res,    # transaction resources
    ]

    mock_tx = Transaction(tx_id=tx_id, state=TxState.PREPARING)
    mock_db.get.return_value = mock_tx

    commit_res = await transfer_service.commit_transfer(tx_id)

    assert commit_res["status"] == TransferStatus.COMMITTED.value
    assert dest_bed.status == BedStatus.IN_USE
    assert dest_bed.current_patient_id == "PT-0001"
    assert source_bed.status == BedStatus.CLEANING


@pytest.mark.asyncio
async def test_rollback_restores_source_bed_in_use_with_patient(transfer_service, mock_db):
    """
    CRITICAL INVARIANT TEST:
    When a transfer rolls back, the source bed MUST return to IN_USE with
    the patient re-attached, never generic READY or homeless!
    """
    tx_id = "TX-TRANSFER-ROLLBACK"
    source_bed = Bed(
        id="BED-ICU-01",
        bed_number="ICU-01",
        ward="ICU",
        bed_type=BedType.ICU,
        status=BedStatus.POST_USE,  # In transit
        current_patient_id=None,
        floor=1,
        room_number="101",
    )
    dest_bed = Bed(
        id="BED-GEN-01",
        bed_number="GW-01",
        ward="General Ward",
        bed_type=BedType.GENERAL,
        status=BedStatus.TENTATIVE_HOLD,
        floor=2,
        room_number="201",
    )

    transfer_record = PatientTransfer(
        id=uuid.uuid4(),
        tx_id=tx_id,
        patient_id="PT-0001",
        source_bed_id="BED-ICU-01",
        destination_bed_id="BED-GEN-01",
        status=TransferStatus.IN_TRANSIT.value,
        hold_ttl_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        initiated_by="nurse.priya",
    )

    mock_t_res = MagicMock()
    mock_t_res.scalar_one_or_none.return_value = transfer_record

    mock_d_res = MagicMock()
    mock_d_res.scalar_one_or_none.return_value = dest_bed

    mock_s_res = MagicMock()
    mock_s_res.scalar_one_or_none.return_value = source_bed

    mock_db.execute.side_effect = [
        mock_t_res,  # select transfer
        mock_d_res,  # select dest bed
        mock_s_res,  # select source bed
    ]

    mock_tx = Transaction(tx_id=tx_id, state=TxState.PREPARING)
    mock_db.get.return_value = mock_tx

    res = await transfer_service.rollback_transfer(tx_id, reason="TTL_EXPIRED")

    assert res["status"] == TransferStatus.ROLLED_BACK.value
    # Destination released to READY
    assert dest_bed.status == BedStatus.READY
    # SOURCE RESTORED TO IN_USE WITH PATIENT!
    assert source_bed.status == BedStatus.IN_USE
    assert source_bed.current_patient_id == "PT-0001"
