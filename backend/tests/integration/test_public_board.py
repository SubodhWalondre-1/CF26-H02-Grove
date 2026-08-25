import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.api.public_board_routes import get_public_shortage_alerts
from app.api.admin_alerts_routes import resolve_alert
from app.models.models import User, UserRole
from app.models.shortage import Alert


@pytest.mark.asyncio
async def test_public_board_unauthenticated_and_zero_phi():
    """
    Public board endpoint must return 200 without authentication
    and guarantee STRICT ZERO PHI in the payload.
    """
    mock_db = AsyncMock()

    mock_alert = Alert(
        alert_id="ALT-B001",
        resource_type="BLOOD_UNIT",
        subtype="O-",
        units_needed=4,
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
    )

    mock_exec = MagicMock()
    mock_exec.all.return_value = [(mock_alert, "units")]
    mock_db.execute.return_value = mock_exec

    # Call endpoint without any current_user dependency
    alerts = await get_public_shortage_alerts(db=mock_db)

    assert len(alerts) == 1
    item = alerts[0]

    # Verify expected public fields
    assert item["alert_id"] == "ALT-B001"
    assert item["resource_type"] == "BLOOD_UNIT"
    assert item["subtype"] == "O-"
    assert item["units_needed"] == 4
    assert item["unit_label"] == "units"
    assert "helpline_phone" in item

    # STRICT ZERO-PHI AUDIT
    phi_forbidden_keys = {
        "patient_id",
        "patient_name",
        "patient",
        "procedure",
        "procedure_type",
        "diagnosis",
        "doctor",
        "nurse",
        "clinician",
        "user_id",
        "tx_id",
        "medical_record_number",
    }
    for forbidden in phi_forbidden_keys:
        assert forbidden not in item, f"PHI leakage detected: key '{forbidden}' present in public payload!"


@pytest.mark.asyncio
async def test_admin_alert_resolve_rbac():
    """
    Asserts only Admin role can resolve shortage alerts manually.
    """
    mock_db = AsyncMock()

    mock_alert = Alert(
        alert_id="ALT-O2-01",
        resource_type="OXYGEN_UNIT",
        subtype="O2_CYLINDER_D",
        units_needed=8,
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
    )

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = mock_alert
    mock_db.execute.return_value = mock_exec

    # 1. Admin resolution -> Allowed
    admin_user = User(user_id="USR-ADMIN", username="admin.ops", role=UserRole.admin)
    res = await resolve_alert(
        alert_id="ALT-O2-01",
        db=mock_db,
        current_user=admin_user,
    )

    assert res["alert_id"] == "ALT-O2-01"
    assert res["status"] == "RESOLVED"
    assert "admin.ops" in res["resolved_by"]
