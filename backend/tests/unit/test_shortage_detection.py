import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.pharmacy import PharmacyResource, PharmacyResourceStatus
from app.models.shortage import Alert, ShortageThreshold
from app.services.shortage import check_shortage, CONSUMABLE_TYPES


@pytest.mark.asyncio
async def test_shortage_detection_threshold_breach_creates_alert():
    """
    When available stock drops below threshold, check_shortage creates an ACTIVE Alert.
    """
    mock_db = AsyncMock()

    threshold = ShortageThreshold(
        resource_type="BLOOD_UNIT",
        subtype="O-",
        critical_threshold=4,
        unit_label="units",
    )

    # Exec 1: Fetch threshold -> threshold
    # Exec 2: Sum available qty -> 1 unit
    # Exec 3: Fetch active alert -> None
    mock_exec_thresh = MagicMock()
    mock_exec_thresh.scalar_one_or_none.return_value = threshold

    mock_exec_qty = MagicMock()
    mock_exec_qty.scalar.return_value = 1

    mock_exec_alert = MagicMock()
    mock_exec_alert.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [mock_exec_thresh, mock_exec_qty, mock_exec_alert]

    alert = await check_shortage(
        resource_type="BLOOD_UNIT",
        subtype="O-",
        db=mock_db,
    )

    assert alert is not None
    assert alert.resource_type == "BLOOD_UNIT"
    assert alert.subtype == "O-"
    assert alert.units_needed == 3  # 4 - 1 = 3
    assert alert.status == "ACTIVE"
    assert alert.created_by == "SYSTEM"


@pytest.mark.asyncio
async def test_shortage_detection_restock_auto_resolves_alert():
    """
    When stock rises back at or above threshold, existing ACTIVE Alert is auto-resolved.
    """
    mock_db = AsyncMock()

    threshold = ShortageThreshold(
        resource_type="BLOOD_UNIT",
        subtype="O-",
        critical_threshold=4,
        unit_label="units",
    )

    active_alert = Alert(
        alert_id="ALT-12345",
        resource_type="BLOOD_UNIT",
        subtype="O-",
        units_needed=2,
        status="ACTIVE",
    )

    # Exec 1: Fetch threshold -> threshold
    # Exec 2: Sum available qty -> 6 units (restocked)
    # Exec 3: Fetch active alert -> active_alert
    mock_exec_thresh = MagicMock()
    mock_exec_thresh.scalar_one_or_none.return_value = threshold

    mock_exec_qty = MagicMock()
    mock_exec_qty.scalar.return_value = 6

    mock_exec_alert = MagicMock()
    mock_exec_alert.scalar_one_or_none.return_value = active_alert

    mock_db.execute.side_effect = [mock_exec_thresh, mock_exec_qty, mock_exec_alert]

    alert = await check_shortage(
        resource_type="BLOOD_UNIT",
        subtype="O-",
        db=mock_db,
    )

    assert alert is not None
    assert alert.status == "RESOLVED"
    assert alert.resolved_by == "SYSTEM"
    assert alert.resolved_at is not None


@pytest.mark.asyncio
async def test_non_consumable_ignores_shortage_check():
    """
    Non-consumable resource types (e.g. OT_ROOM, BED_ICU) should never trigger shortage checks.
    """
    mock_db = AsyncMock()

    alert = await check_shortage(
        resource_type="OT_ROOM",
        subtype="OT-1",
        db=mock_db,
    )

    assert alert is None
    assert mock_db.execute.call_count == 0
