import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.shortage import Alert, ShortageThreshold
from app.services.shortage import check_shortage


@pytest.mark.asyncio
async def test_alert_idempotency_updates_existing_active_alert():
    """
    Subsequent check_shortage calls for the same resource update units_needed
    on the existing active alert and do not create duplicate active alert records.
    """
    mock_db = AsyncMock()

    threshold = ShortageThreshold(
        resource_type="MEDICATION_SLOT",
        subtype="ADRENALINE_1MG",
        critical_threshold=20,
        unit_label="vials",
    )

    existing_alert = Alert(
        alert_id="ALT-ADR001",
        resource_type="MEDICATION_SLOT",
        subtype="ADRENALINE_1MG",
        units_needed=5,
        status="ACTIVE",
    )

    # Exec 1: Fetch threshold
    mock_exec_thresh = MagicMock()
    mock_exec_thresh.scalar_one_or_none.return_value = threshold

    # Exec 2: Available count is now 10 (needs 10 instead of 5)
    mock_exec_qty = MagicMock()
    mock_exec_qty.scalar.return_value = 10

    # Exec 3: Fetch active alert -> returns existing_alert
    mock_exec_alert = MagicMock()
    mock_exec_alert.scalar_one_or_none.return_value = existing_alert

    mock_db.execute.side_effect = [mock_exec_thresh, mock_exec_qty, mock_exec_alert]

    result_alert = await check_shortage(
        resource_type="MEDICATION_SLOT",
        subtype="ADRENALINE_1MG",
        db=mock_db,
    )

    # Assert existing alert was updated in-place
    assert result_alert.alert_id == "ALT-ADR001"
    assert result_alert.units_needed == 10
    assert result_alert.status == "ACTIVE"
    # db.add should not be called since we updated existing
    assert mock_db.add.call_count == 0
