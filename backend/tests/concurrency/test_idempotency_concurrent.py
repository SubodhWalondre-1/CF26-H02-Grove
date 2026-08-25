import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.engine.idempotency import check_and_claim


@pytest.mark.asyncio
async def test_concurrent_burst_claims_produce_exactly_one_winner():
    """
    Simulates 50 simultaneous identical requests hitting the Idempotency Gate.
    The Redis SET NX atomic claim guarantees that exactly 1 request succeeds
    (is_duplicate=False) and all 49 other concurrent calls are flagged as duplicates.
    """
    # Simulated Redis in-memory storage with atomic SET NX behavior
    redis_store = {}
    lock = asyncio.Lock()

    async def mock_set(key, value, nx=False, ex=None, keepttl=False, xx=False):
        async with lock:
            if nx:
                if key in redis_store:
                    return None
                redis_store[key] = value
                return True
            if xx:
                if key not in redis_store:
                    return None
                redis_store[key] = value
                return True
            redis_store[key] = value
            return True

    async def mock_get(key):
        async with lock:
            return redis_store.get(key)

    mock_redis = AsyncMock()
    mock_redis.set.side_effect = mock_set
    mock_redis.get.side_effect = mock_get

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    fields = {
        "patient_id": "PT-CONCURRENT",
        "resource_ids": ["RES-OT2", "RES-SURG-A"],
    }

    # Fire 50 concurrent requests simultaneously
    results = await asyncio.gather(
        *[
            check_and_claim(
                redis_client=mock_redis,
                db=mock_db,
                request_type="care_bundle",
                fields=fields,
                claimed_by=f"dr.user_{i}",
            )
            for i in range(50)
        ]
    )

    winners = [r for r in results if not r.is_duplicate]
    duplicates = [r for r in results if r.is_duplicate]

    assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"
    assert len(duplicates) == 49, f"Expected 49 duplicates, got {len(duplicates)}"
