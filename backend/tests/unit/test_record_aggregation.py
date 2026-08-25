import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.models import AuditEvent
from app.services.record import aggregate_operation_record


@pytest.mark.asyncio
async def test_record_aggregation_from_audit_events():
    """
    Given a mocked set of audit events for a transaction, assert OperationRecordData
    correctly extracts patient, medical team, resources, timeline, and audit ID.
    """
    now_utc = datetime.now(timezone.utc)
    mock_db = AsyncMock()

    events = [
        AuditEvent(
            audit_id="AUD-001",
            tx_id="TX-1001",
            event_type="TX_CREATED",
            occurred_at=now_utc,
            detail={
                "patient_id": "PT-99",
                "patient_name": "John Doe",
                "procedure_type": "trauma_surgery",
                "acuity": 9.6,
                "requested_by": "dr.mehta",
            },
        ),
        AuditEvent(
            audit_id="AUD-002",
            tx_id="TX-1001",
            event_type="RESOURCE_LOCKED",
            resource_id="RES-OT-1",
            occurred_at=now_utc,
            detail={
                "resource_id": "RES-OT-1",
                "resource_type": "ot",
                "resource_label": "Operating Theatre 1",
                "who": "nurse.priya",
            },
        ),
        AuditEvent(
            audit_id="AUD-003",
            tx_id="TX-1001",
            event_type="TX_COMMITTED",
            decision="COMMIT",
            occurred_at=now_utc,
            detail={"status": "COMMITTED"},
        ),
    ]

    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = events
    mock_db.execute.return_value = mock_exec

    data = await aggregate_operation_record(tx_id="TX-1001", db=mock_db)

    # 1. Header & ID
    assert data.tx_id == "TX-1001"
    assert data.audit_id == "AUD-TX-1001"
    assert data.status == "COMPLETED"

    # 2. Patient & Criticality
    assert data.patient["patient_id"] == "PT-99"
    assert data.patient["acuity_score"] == 9.6
    assert "CRITICAL" in data.patient["criticality_label"]

    # 3. Medical Team Roles
    staff_ids = [m["employee_id"] for m in data.medical_team]
    assert "dr.mehta" in staff_ids
    assert "nurse.priya" in staff_ids

    # 4. Resources
    assert len(data.resources) == 1
    assert data.resources[0]["resource_id"] == "RES-OT-1"
    assert data.resources[0]["final_status"] == "COMMITTED"

    # 5. Timeline
    assert len(data.timeline) == 3


@pytest.mark.asyncio
async def test_record_aggregation_with_arbiter_conflict_and_rollback():
    """
    Tests aggregation with conflict arbitration scores and rollback status.
    """
    now_utc = datetime.now(timezone.utc)
    mock_db = AsyncMock()

    events = [
        AuditEvent(
            audit_id="AUD-010",
            tx_id="TX-2002",
            event_type="CONFLICT_ARBITRATION",
            conflict_id="CONF-99",
            decision="PREEMPTED",
            effective_score=8.5,
            occurred_at=now_utc,
            detail={
                "patient_id": "PT-02",
                "acuity": 7.0,
                "arbiter_scores": "TX-2002 (8.5) vs TX-3003 (9.8) -> Preempted",
            },
        ),
        AuditEvent(
            audit_id="AUD-011",
            tx_id="TX-2002",
            event_type="TX_ROLLED_BACK",
            occurred_at=now_utc,
            detail={"status": "ROLLED_BACK"},
        ),
    ]

    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = events
    mock_db.execute.return_value = mock_exec

    data = await aggregate_operation_record(tx_id="TX-2002", db=mock_db)

    assert data.status == "ROLLED_BACK"
    assert data.arbiter_notes is not None
    assert "TX-2002" in data.arbiter_notes
