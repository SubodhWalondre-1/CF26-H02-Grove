import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.escalation import request_escalation
from app.models.escalation import EscalationDecision
from app.models.models import (
    Bed,
    BedStatus,
    BedType,
    Patient,
    RequestType,
    Resource,
    ResourceStatus,
    ResourceType,
    Transaction,
    TxState,
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
    redis.publish = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_in_use_resource_is_never_preemptable(mock_db, mock_redis):
    """
    HARD SAFETY RULE:
    If a resource is IN_USE (bed occupied mid-procedure, surgery underway),
    preemption MUST be rejected (RESOURCE_IN_USE), regardless of acuity gap.
    """
    target_bed = Bed(
        id="BED-ICU-01",
        bed_number="ICU-01",
        ward="ICU",
        bed_type=BedType.ICU,
        status=BedStatus.IN_USE,  # Actively in use!
        current_patient_id="PT-ROUTINE",
        floor=1,
        room_number="101",
    )

    # 1st execute: check Resource (none)
    mock_res1 = MagicMock()
    mock_res1.scalar_one_or_none.return_value = None

    # 2nd execute: check Bed (found, IN_USE)
    mock_res2 = MagicMock()
    mock_res2.scalar_one_or_none.return_value = target_bed

    mock_db.execute.side_effect = [mock_res1, mock_res2]

    res = await request_escalation(
        db=mock_db,
        escalating_tx_id="TX-EMERGENCY-10",
        target_resource_id="BED-ICU-01",
        requested_by="dr.mehta",
        source_feature="DIRECT",
        redis_client=mock_redis,
    )

    assert res["decision"] == EscalationDecision.REJECTED.value
    assert res["rejection_reason"] == "RESOURCE_IN_USE"


@pytest.mark.asyncio
async def test_acuity_tie_favors_current_holder(mock_db, mock_redis):
    """
    If escalating_acuity == holder_acuity (e.g. both 7.0),
    escalation MUST be rejected (HOLDER_HIGHER_ACUITY) — first-come is the tiebreaker.
    """
    held_resource = Resource(
        resource_id="RES-OT2",
        type=ResourceType.ot,
        label="OT-2",
        status=ResourceStatus.locked,
        held_by_tx="TX-HOLDER-7",
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = held_resource
    mock_db.execute.return_value = mock_res

    holder_tx = Transaction(tx_id="TX-HOLDER-7", patient_id="PT-0001", state=TxState.ACTIVE)
    escalating_tx = Transaction(tx_id="TX-ESCALATE-7", patient_id="PT-0002", state=TxState.PREPARING)

    def mock_get(model, pk):
        if pk == "TX-HOLDER-7":
            return holder_tx
        if pk == "TX-ESCALATE-7":
            return escalating_tx
        return None

    mock_db.get.side_effect = mock_get

    # Both patients have acuity 7.0
    with patch("app.engine.escalation.get_patient_acuity") as mock_acuity:
        mock_acuity.side_effect = [
            Patient(patient_id="PT-0002", name="Patient B", base_acuity=Decimal("7.00")),  # escalating
            Patient(patient_id="PT-0001", name="Patient A", base_acuity=Decimal("7.00")),  # holder
        ]

        res = await request_escalation(
            db=mock_db,
            escalating_tx_id="TX-ESCALATE-7",
            target_resource_id="RES-OT2",
            requested_by="dr.mehta",
            source_feature="DIRECT",
            redis_client=mock_redis,
        )

        assert res["decision"] == EscalationDecision.REJECTED.value
        assert res["rejection_reason"] == "HOLDER_HIGHER_ACUITY"


@pytest.mark.asyncio
async def test_higher_acuity_escalation_approves_and_preempts_holder(mock_db, mock_redis):
    """
    Higher acuity (9.8 vs 5.0) -> APPROVED.
    Holder is preempted, alternative resource suggested, and target assigned to escalator.
    """
    held_resource = Resource(
        resource_id="RES-OT2",
        type=ResourceType.ot,
        label="OT-2",
        status=ResourceStatus.locked,
        held_by_tx="TX-ROUTINE-5",
    )

    alt_resource = Resource(
        resource_id="RES-OT3",
        type=ResourceType.ot,
        label="OT-3",
        status=ResourceStatus.available,
    )

    mock_res1 = MagicMock()
    mock_res1.scalar_one_or_none.return_value = held_resource

    mock_res2 = MagicMock()
    mock_res2.scalar_one_or_none.return_value = alt_resource

    mock_db.execute.side_effect = [
        mock_res1,  # Target resource lookup
        mock_res2,  # Alternative resource lookup
        MagicMock(), # Single resource release query
        MagicMock(), # TransactionResource update
    ]

    holder_tx = Transaction(
        tx_id="TX-ROUTINE-5",
        patient_id="PT-0001",
        requested_by="dr.kapoor",
        request_type=RequestType.single_resource,
        state=TxState.ACTIVE,
    )
    escalating_tx = Transaction(
        tx_id="TX-CRITICAL-9",
        patient_id="PT-0002",
        requested_by="dr.mehta",
        request_type=RequestType.escalation,
        state=TxState.PREPARING,
    )

    def mock_get(model, pk):
        if pk == "TX-ROUTINE-5":
            return holder_tx
        if pk == "TX-CRITICAL-9":
            return escalating_tx
        return None

    mock_db.get.side_effect = mock_get

    with patch("app.engine.escalation.get_patient_acuity") as mock_acuity:
        mock_acuity.side_effect = [
            Patient(patient_id="PT-0002", name="Patient Critical", base_acuity=Decimal("9.80")),  # escalating
            Patient(patient_id="PT-0001", name="Patient Routine", base_acuity=Decimal("5.00")),   # holder
        ]

        res = await request_escalation(
            db=mock_db,
            escalating_tx_id="TX-CRITICAL-9",
            target_resource_id="RES-OT2",
            requested_by="dr.mehta",
            source_feature="DIRECT",
            redis_client=mock_redis,
        )

        assert res["decision"] == EscalationDecision.APPROVED.value
        assert res["escalating_acuity"] == 9.8
        assert res["holder_acuity"] == 5.0
        assert res["suggested_alternative"] is not None
        assert res["suggested_alternative"]["resource_id"] == "RES-OT3"

        # Resource allocated to escalating TX
        assert held_resource.held_by_tx == "TX-CRITICAL-9"
        # Holder marked aborted
        assert holder_tx.state == TxState.ABORTED
        # WebSocket alert dispatched to preempted holder
        assert mock_redis.publish.called
