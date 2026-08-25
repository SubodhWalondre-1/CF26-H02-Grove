import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.escalation import request_escalation
from app.models.escalation import EscalationDecision
from app.models.models import (
    Patient,
    RequestType,
    Resource,
    ResourceStatus,
    ResourceType,
    Transaction,
    TxState,
)


@pytest.mark.asyncio
async def test_concurrent_escalations_against_same_held_resource():
    """
    Simulates multiple doctors attempting rapid-fire escalations against
    the same held resource with varying acuities:
      - Holder: Acuity 4.0
      - Doctor 1: Acuity 8.0 -> Preempts holder, becomes new holder
      - Doctor 2: Acuity 6.0 -> Evaluates against new state -> Rejected (HOLDER_HIGHER_ACUITY)
    """
    held_resource = Resource(
        resource_id="RES-VENT3",
        type=ResourceType.ventilator,
        label="VENT-3",
        status=ResourceStatus.locked,
        held_by_tx="TX-HOLDER-4",
    )

    transactions = {
        "TX-HOLDER-4": Transaction(tx_id="TX-HOLDER-4", patient_id="PT-4", state=TxState.ACTIVE),
        "TX-ESC-8": Transaction(tx_id="TX-ESC-8", patient_id="PT-8", state=TxState.PREPARING),
        "TX-ESC-6": Transaction(tx_id="TX-ESC-6", patient_id="PT-6", state=TxState.PREPARING),
    }

    patients = {
        "PT-4": Patient(patient_id="PT-4", name="Pt 4", base_acuity=Decimal("4.00")),
        "PT-8": Patient(patient_id="PT-8", name="Pt 8", base_acuity=Decimal("8.00")),
        "PT-6": Patient(patient_id="PT-6", name="Pt 6", base_acuity=Decimal("6.00")),
    }

    mock_db = AsyncMock()

    def mock_get(model, pk):
        return transactions.get(pk)

    mock_db.get.side_effect = mock_get
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt)
        if "resources" in stmt_str:
            mock_res.scalar_one_or_none.return_value = held_resource
        else:
            mock_res.scalar_one_or_none.return_value = None
            mock_res.scalars.return_value.all.return_value = []
        return mock_res

    mock_db.execute.side_effect = mock_execute

    with patch("app.engine.escalation.get_patient_acuity") as mock_acuity:
        async def get_acuity(db, pt_id):
            return patients.get(pt_id)

        mock_acuity.side_effect = get_acuity

        # 1. Doctor 1 (Acuity 8.0) escalates against Holder (Acuity 4.0)
        res1 = await request_escalation(
            db=mock_db,
            escalating_tx_id="TX-ESC-8",
            target_resource_id="RES-VENT3",
            requested_by="dr.mehta",
        )
        assert res1["decision"] == EscalationDecision.APPROVED.value
        assert held_resource.held_by_tx == "TX-ESC-8"

        # 2. Doctor 2 (Acuity 6.0) now escalates against the new Holder (TX-ESC-8, Acuity 8.0)
        res2 = await request_escalation(
            db=mock_db,
            escalating_tx_id="TX-ESC-6",
            target_resource_id="RES-VENT3",
            requested_by="dr.kapoor",
        )
        assert res2["decision"] == EscalationDecision.REJECTED.value
        assert res2["rejection_reason"] == "HOLDER_HIGHER_ACUITY"
        # Resource remains with Doctor 1 (Acuity 8.0)
        assert held_resource.held_by_tx == "TX-ESC-8"
