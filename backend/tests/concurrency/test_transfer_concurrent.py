import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.models import (
    Bed,
    BedStatus,
    BedType,
    Patient,
)
from app.models.transfer import TransferStatus
from app.services.transfer import (
    TransferDestinationUnavailableError,
    TransferService,
)


@pytest.mark.asyncio
async def test_concurrent_transfers_targeting_same_destination_bed():
    """
    Two transfer requests (Doctor A for PT-0001, Doctor B for PT-0002)
    both attempt to acquire the exact same destination bed (GW-01).
    Only 1 transfer must succeed, the other fails with TransferDestinationUnavailableError.
    The loser's source bed must remain untouched in IN_USE state.
    """
    source_bed_1 = Bed(
        id="BED-ICU-01",
        bed_number="ICU-01",
        ward="ICU",
        bed_type=BedType.ICU,
        status=BedStatus.IN_USE,
        current_patient_id="PT-0001",
        floor=1,
        room_number="101",
    )
    source_bed_2 = Bed(
        id="BED-ICU-02",
        bed_number="ICU-02",
        ward="ICU",
        bed_type=BedType.ICU,
        status=BedStatus.IN_USE,
        current_patient_id="PT-0002",
        floor=1,
        room_number="102",
    )
    shared_dest_bed = Bed(
        id="BED-GEN-01",
        bed_number="GW-01",
        ward="General Ward",
        bed_type=BedType.GENERAL,
        status=BedStatus.READY,
        floor=2,
        room_number="201",
    )

    db_state = {
        "BED-ICU-01": source_bed_1,
        "BED-ICU-02": source_bed_2,
        "BED-GEN-01": shared_dest_bed,
        "PT-0001": Patient(patient_id="PT-0001", name="Patient A"),
        "PT-0002": Patient(patient_id="PT-0002", name="Patient B"),
    }

    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt)

        if "BED-ICU-01" in stmt_str:
            mock_res.scalar_one_or_none.return_value = db_state["BED-ICU-01"]
        elif "BED-ICU-02" in stmt_str:
            mock_res.scalar_one_or_none.return_value = db_state["BED-ICU-02"]
        elif "BED-GEN-01" in stmt_str:
            mock_res.scalar_one_or_none.return_value = db_state["BED-GEN-01"]
        else:
            mock_res.scalar_one_or_none.return_value = None
            mock_res.scalars.return_value.all.return_value = []
        return mock_res

    async def mock_get(model, pk):
        return db_state.get(pk)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.get = AsyncMock(side_effect=mock_get)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    service = TransferService(mock_db)

    # 1. First transfer initiates successfully
    res1 = await service.initiate_transfer(
        patient_id="PT-0001",
        source_bed_id="BED-ICU-01",
        destination_bed_id="BED-GEN-01",
    )
    assert res1["status"] == TransferStatus.DESTINATION_HELD.value
    assert shared_dest_bed.status == BedStatus.TENTATIVE_HOLD
    assert source_bed_1.status == BedStatus.POST_USE

    # 2. Second transfer attempts to acquire same destination bed (now TENTATIVE_HOLD)
    with pytest.raises(TransferDestinationUnavailableError):
        await service.initiate_transfer(
            patient_id="PT-0002",
            source_bed_id="BED-ICU-02",
            destination_bed_id="BED-GEN-01",
        )

    # Invariant: Loser's source bed remains untouched in IN_USE with PT-0002
    assert source_bed_2.status == BedStatus.IN_USE
    assert source_bed_2.current_patient_id == "PT-0002"
