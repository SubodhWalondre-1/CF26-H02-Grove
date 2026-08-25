import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.override import evaluate_override
from app.models.models import AdminConfig, Resource, ResourceStatus
from app.models.override import OverrideFlagReason, OverrideTriggerType


@pytest.mark.asyncio
async def test_override_threshold_boundaries():
    """
    Acuity 9.49 must NOT automatically trigger emergency override.
    Acuity 9.50 MUST trigger automatic emergency override.
    """
    mock_db = AsyncMock()

    # Mock admin_config returning threshold = 9.5
    cfg_thresh = AdminConfig(key="acuity_override_threshold", value=Decimal("9.5"), updated_by="admin")
    cfg_freq = AdminConfig(key="override_frequency_flag_limit", value=Decimal("3"), updated_by="admin")

    mock_db_res = MagicMock()
    mock_db_res.scalars.return_value.all.return_value = [cfg_thresh, cfg_freq]
    mock_db.execute.return_value = mock_db_res
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    # Case A: 9.49 -> Not an override
    res_sub = await evaluate_override(
        db=mock_db,
        tx_id="TX-01",
        patient_id="PT-01",
        acuity_score=9.49,
        requested_resources=["RES-VENT1"],
        requested_by="dr.mehta",
    )
    assert res_sub.is_override is False

    # Case B: 9.50 -> Automatic override
    # Mock resource query for RES-VENT1 as available
    res_vent = Resource(
        resource_id="RES-VENT1",
        name="Ventilator 1",
        resource_type="ventilator",
        status=ResourceStatus.available,
    )
    mock_db_res2 = MagicMock()
    mock_db_res2.scalars.return_value.all.return_value = [cfg_thresh, cfg_freq]
    mock_db_res2.scalar_one_or_none.return_value = res_vent
    mock_db.execute.return_value = mock_db_res2

    with patch("app.engine.override.attempt_single_resource_lock", new_callable=AsyncMock) as mock_lock:
        mock_lock.return_value = True
        res_super = await evaluate_override(
            db=mock_db,
            tx_id="TX-02",
            patient_id="PT-02",
            acuity_score=9.50,
            requested_resources=["RES-VENT1"],
            requested_by="dr.mehta",
        )

        assert res_super.is_override is True
        assert res_super.trigger_type == OverrideTriggerType.AUTOMATIC.value
        assert res_super.all_legs_resolved is True
        assert res_super.latency_ms is not None
        assert res_super.latency_ms < 50  # Must be under 50ms


@pytest.mark.asyncio
async def test_manual_declare_and_governance_flags():
    """
    Manual declaration with reason triggers MANUAL_DECLARE.
    If acuity < 7.0, it flags POST_HOC_ACUITY_MISMATCH for review.
    """
    mock_db = AsyncMock()
    cfg_thresh = AdminConfig(key="acuity_override_threshold", value=Decimal("9.5"), updated_by="admin")
    cfg_freq = AdminConfig(key="override_frequency_flag_limit", value=Decimal("3"), updated_by="admin")

    # Mock count of recent overrides = 0
    count_res = MagicMock()
    count_res.scalar_one.return_value = 0

    mock_db_res = MagicMock()
    mock_db_res.scalars.return_value.all.return_value = [cfg_thresh, cfg_freq]
    mock_db_res.scalar_one_or_none.return_value = Resource(
        resource_id="RES-OT1",
        name="OT 1",
        resource_type="ot_room",
        status=ResourceStatus.available,
    )
    mock_db.execute.side_effect = [mock_db_res, mock_db_res, count_res]
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    with patch("app.engine.override.attempt_single_resource_lock", new_callable=AsyncMock) as mock_lock:
        mock_lock.return_value = True
        res = await evaluate_override(
            db=mock_db,
            tx_id="TX-03",
            patient_id="PT-03",
            acuity_score=6.5,  # below 7.0
            requested_resources=["RES-OT1"],
            requested_by="dr.sharma",
            manual_reason="Suspected acute aortic dissection, clinical scoring pending",
        )

        assert res.is_override is True
        assert res.trigger_type == OverrideTriggerType.MANUAL_DECLARE.value
        assert res.flagged_for_review is True
        assert res.flag_reason == OverrideFlagReason.POST_HOC_ACUITY_MISMATCH.value
