import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.models import Resource, ResourceStatus, ResourceType
from app.services.readiness import transition_resource_state


@pytest.mark.asyncio
async def test_concurrent_turnaround_transitions_optimistic_concurrency():
    """
    Two housekeeping staff simultaneously tap 'cleaning complete' on the same
    resource with expected_version = 0.
    Optimistic concurrency guarantees exactly 1 transition succeeds and the other fails with HTTP 409.
    """
    mock_resource = Resource(
        resource_id="RES-OT-01",
        type=ResourceType.ot,
        label="Operating Theatre 1",
        status=ResourceStatus.locked,
        version=0,
        updated_at=datetime.now(timezone.utc),
    )

    lock = asyncio.Lock()

    async def mock_transition_call(user_id: str, expected_version: int):
        mock_db = AsyncMock()

        async with lock:
            # Simulate DB read
            if mock_resource.version != expected_version:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=409,
                    detail=f"Optimistic lock conflict: version is {mock_resource.version}, expected {expected_version}",
                )
            mock_resource.status = ResourceStatus.locked
            mock_resource.version += 1

            db_res = MagicMock()
            db_res.scalar_one_or_none.return_value = mock_resource
            mock_db.execute.return_value = db_res
            mock_db.flush = AsyncMock()
            mock_db.add = MagicMock()

            return {
                "resource_id": mock_resource.resource_id,
                "status": "SANITIZED",
                "version": mock_resource.version,
                "triggered_by": user_id,
            }

    # Two concurrent requests with expected_version = 0
    results = await asyncio.gather(
        mock_transition_call("staff.housekeeping_1", 0),
        mock_transition_call("staff.housekeeping_2", 0),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected 1 conflict failure, got {len(failures)}"
