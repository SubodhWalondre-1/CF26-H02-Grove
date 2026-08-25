import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from app.engine.idempotency import (
    build_fingerprint,
    check_and_claim,
    finalize_idempotency,
)


def test_fingerprint_deterministic_and_order_independent():
    """
    Fingerprint generation must be deterministic regardless of dictionary
    key order or resource array order.
    """
    fields_1 = {
        "patient_id": "PT-0001",
        "resource_ids": ["RES-OT2", "RES-SURG-A", "RES-VENT3"],
    }
    fields_2 = {
        "resource_ids": ["RES-VENT3", "RES-OT2", "RES-SURG-A"],  # reversed order
        "patient_id": "PT-0001",
    }

    fp1 = build_fingerprint("care_bundle", fields_1, bucket_seconds=10)
    fp2 = build_fingerprint("care_bundle", fields_2, bucket_seconds=10)

    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex digest length


def test_fingerprint_changes_across_time_buckets():
    """
    Requests in different 10-second time windows must produce distinct fingerprints.
    """
    fields = {"patient_id": "PT-0001", "resource_id": "RES-OT2"}

    # Current bucket
    fp1 = build_fingerprint("single_resource", fields, bucket_seconds=10)

    # Simulated past bucket (20 seconds ago)
    past_time = time.time() - 20
    import hashlib
    raw_past = f"type=single_resource|patient=PT-0001|resources=RES-OT2|bucket={int(past_time // 10) * 10}"
    fp_past = hashlib.sha256(raw_past.encode("utf-8")).hexdigest()

    assert fp1 != fp_past


@pytest.mark.asyncio
async def test_atomic_claim_and_duplicate_suppression():
    """
    1st call: SET NX succeeds -> is_duplicate = False.
    2nd call: SET NX returns None -> is_duplicate = True, suppressed audit event logged.
    """
    mock_redis = AsyncMock()
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    fields = {"patient_id": "PT-0001", "resource_id": "RES-OT2"}

    # 1. First claim: Redis SET NX returns True
    mock_redis.set.return_value = True

    res1 = await check_and_claim(
        redis_client=mock_redis,
        db=mock_db,
        request_type="single_resource",
        fields=fields,
        claimed_by="dr.mehta",
    )

    assert res1.is_duplicate is False
    assert res1.fingerprint is not None

    # 2. Duplicate claim: Redis SET NX returns None/False
    mock_redis.set.return_value = None
    mock_redis.get.return_value = '{"tx_id": "TX-01", "status": "PENDING", "claimed_by": "dr.mehta"}'

    res2 = await check_and_claim(
        redis_client=mock_redis,
        db=mock_db,
        request_type="single_resource",
        fields=fields,
        claimed_by="nurse.priya",
    )

    assert res2.is_duplicate is True
    assert res2.existing_tx_id == "TX-01"
    assert res2.claimed_by == "dr.mehta"


@pytest.mark.asyncio
async def test_outcome_based_dynamic_ttl_policy():
    """
    Outcome TTL Policy verification:
      - COMMITTED: keepttl / full TTL retained
      - REJECTED: shortened to 2-second grace window
      - ROLLED_BACK: deleted immediately
    """
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = [b"idem:single_resource:testfp12345"]
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.flush = AsyncMock()

    fp = "testfp12345"

    # Case A: COMMITTED -> keeps full TTL
    await finalize_idempotency(mock_redis, mock_db, fp, "TX-01", "COMMITTED")
    mock_redis.set.assert_called()
    assert mock_redis.set.call_args[1].get("keepttl") is True

    # Case B: REJECTED -> shortened to 2s
    mock_redis.reset_mock()
    await finalize_idempotency(mock_redis, mock_db, fp, "TX-01", "REJECTED", rejection_grace_seconds=2)
    mock_redis.set.assert_called()
    assert mock_redis.set.call_args[1].get("ex") == 2

    # Case C: ROLLED_BACK -> deleted immediately
    mock_redis.reset_mock()
    await finalize_idempotency(mock_redis, mock_db, fp, "TX-01", "ROLLED_BACK")
    mock_redis.delete.assert_called_with("idem:single_resource:testfp12345")
