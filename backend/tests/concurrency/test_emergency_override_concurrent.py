import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.override import evaluate_override
from app.models.models import AdminConfig, Resource, ResourceStatus


@pytest.mark.asyncio
async def test_concurrent_emergency_override_burst_under_50ms():
    """
    Simulates a burst of 20 concurrent emergency override requests.
    Asserts that all requests evaluate correctly and report sub-50ms latency.
    """
    mock_db = AsyncMock()
    cfg_thresh = AdminConfig(key="acuity_override_threshold", value=Decimal("9.5"), updated_by="admin")
    cfg_freq = AdminConfig(key="override_frequency_flag_limit", value=Decimal("100"), updated_by="admin")

    def make_db_res():
        res = MagicMock()
        res.scalars.return_value.all.return_value = [cfg_thresh, cfg_freq]
        res.scalar_one_or_none.return_value = Resource(
            resource_id="RES-VENT1",
            name="Ventilator 1",
            resource_type="ventilator",
            status=ResourceStatus.available,
        )
        return res

    mock_db.execute.side_effect = lambda stmt: make_db_res()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    with patch("app.engine.override.attempt_single_resource_lock", new_callable=AsyncMock) as mock_lock:
        mock_lock.return_value = True

        tasks = [
            evaluate_override(
                db=mock_db,
                tx_id=f"TX-EMERG-{i}",
                patient_id=f"PT-{i}",
                acuity_score=9.8,
                requested_resources=["RES-VENT1"],
                requested_by=f"dr.user_{i}",
            )
            for i in range(20)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 20
        for r in results:
            assert r.is_override is True
            assert r.all_legs_resolved is True
            assert r.latency_ms < 50, f"Expected <50ms latency, got {r.latency_ms}ms"
