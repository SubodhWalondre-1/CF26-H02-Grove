import asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.services.bed import BedService, InvalidTransitionError
from app.models.models import Bed, BedStatus, BedType


@pytest.mark.concurrency
async def test_concurrent_allocation_prevents_double_booking(test_db, redis_client, db_session):
    """
    Concurrent requests for 1 READY bed.
    Only 1 should succeed, rest should get InvalidTransitionError.
    """
    bed_id = "BED-TEST-CONCURRENT"

    # Ensure test bed exists in READY state
    existing = await db_session.get(Bed, bed_id)
    if not existing:
        test_bed = Bed(
            id=bed_id,
            bed_number="TEST-99",
            ward="Emergency Ward",
            bed_type=BedType.ICU,
            status=BedStatus.READY,
            floor=1,
            room_number="R-99",
        )
        db_session.add(test_bed)
        await db_session.commit()
    else:
        existing.status = BedStatus.READY
        existing.current_transaction_id = None
        await db_session.commit()

    session_factory = async_sessionmaker(
        bind=test_db,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def attempt_hold(tx_index: int):
        async with session_factory() as session:
            bed_service = BedService(session, redis_client)
            return await bed_service.tentative_hold(bed_id, f"TX-{tx_index}")

    results = await asyncio.gather(
        *[attempt_hold(i) for i in range(50)],
        return_exceptions=True
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 49, f"Expected 49 failures, got {len(failures)}"
    for f in failures:
        assert isinstance(f, InvalidTransitionError)
