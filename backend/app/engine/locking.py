from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.models import (
    HoldState,
    Resource,
    ResourceStatus,
    TransactionResource,
)

logger = get_logger(__name__)


async def attempt_single_resource_lock(
    db: AsyncSession,
    tx_id: str,
    resource_id: str,
) -> Optional[Resource]:
    """
    Attempts to acquire an immediate non-blocking row-level lock on a single clinical resource
    using SELECT ... FOR UPDATE SKIP LOCKED.
    
    Returns the locked Resource ORM object on success, or None if unavailable/locked.
    """
    stmt = (
        select(Resource)
        .where(
            Resource.resource_id == resource_id,
            Resource.status == ResourceStatus.available,
        )
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    resource = result.scalar_one_or_none()

    if not resource:
        logger.info(
            f"Resource {resource_id} lock acquisition skipped/contested for TX {tx_id}",
            extra={"tx_id": tx_id, "resource_id": resource_id},
        )
        return None

    now_utc = datetime.now(timezone.utc)

    # Transition resource to locked
    resource.status = ResourceStatus.locked
    resource.held_by_tx = tx_id
    resource.version = resource.version + 1
    resource.updated_at = now_utc

    # Update transaction association hold state
    tr_stmt = (
        update(TransactionResource)
        .where(
            TransactionResource.tx_id == tx_id,
            TransactionResource.resource_id == resource_id,
        )
        .values(
            hold_state=HoldState.held,
            updated_at=now_utc,
        )
    )
    await db.execute(tr_stmt)
    await db.flush()

    logger.info(
        f"Resource {resource_id} locked successfully by TX {tx_id} (version: {resource.version})",
        extra={"tx_id": tx_id, "resource_id": resource_id, "version": resource.version},
    )

    return resource


async def release_single_resource(
    db: AsyncSession,
    tx_id: str,
    resource_id: str,
) -> None:
    """
    Releases a lock held by tx_id on resource_id, resetting status to 'available'
    and hold_state to 'released'. Guarded by held_by_tx == tx_id.
    """
    now_utc = datetime.now(timezone.utc)

    res_stmt = (
        update(Resource)
        .where(
            Resource.resource_id == resource_id,
            Resource.held_by_tx == tx_id,
        )
        .values(
            status=ResourceStatus.available,
            held_by_tx=None,
            version=Resource.version + 1,
            updated_at=now_utc,
        )
    )
    await db.execute(res_stmt)

    tr_stmt = (
        update(TransactionResource)
        .where(
            TransactionResource.tx_id == tx_id,
            TransactionResource.resource_id == resource_id,
        )
        .values(
            hold_state=HoldState.released,
            updated_at=now_utc,
        )
    )
    await db.execute(tr_stmt)
    await db.flush()

    logger.info(
        f"Resource {resource_id} released from TX {tx_id}",
        extra={"tx_id": tx_id, "resource_id": resource_id},
    )
