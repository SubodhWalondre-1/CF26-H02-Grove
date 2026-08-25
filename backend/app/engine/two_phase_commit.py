from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import publish_event
from app.core.scheduler import cancel_ttl_expiry, schedule_ttl_expiry
from app.models.models import (
    HoldState,
    RequestType,
    Resource,
    ResourceStatus,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
)
from app.services.audit import create_audit_event

logger = get_logger(__name__)


async def prepare_bundle(
    db: AsyncSession,
    tx: Transaction,
) -> Tuple[bool, List[str], List[str]]:
    """
    2PC PREPARE phase for care bundles.
    
    Attempts to acquire tentative holds on ALL requested bundle resources sequentially.
    Short-circuits immediately if any single resource fails.
    
    Returns (all_held: bool, held_resource_ids: list[str], failed_resource_ids: list[str]).
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Load target resource_ids
    stmt = (
        select(TransactionResource)
        .where(
            TransactionResource.tx_id == tx.tx_id,
            TransactionResource.hold_state.in_([HoldState.requested, HoldState.tentative]),
        )
        .order_by(TransactionResource.resource_id)
    )
    tr_result = await db.execute(stmt)
    tr_rows = list(tr_result.scalars().all())

    # 2. Transition TX to PREPARING
    hold_ttl = tx.hold_ttl_seconds if tx.hold_ttl_seconds is not None else 30
    tx.state = TxState.PREPARING
    tx.hold_expires_at = now_utc + timedelta(seconds=hold_ttl)
    tx.updated_at = now_utc

    h_preparing = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.PREPARING,
        occurred_at=now_utc,
    )
    db.add(h_preparing)
    await db.flush()

    # Schedule one-shot TTL expiry timer
    schedule_ttl_expiry(tx.tx_id, tx.hold_expires_at)

    held_resource_ids: List[str] = []
    failed_resource_ids: List[str] = []

    # 3. Attempt tentative holds on each resource
    for tr in tr_rows:
        rid = tr.resource_id
        res_stmt = (
            select(Resource)
            .where(
                Resource.resource_id == rid,
                Resource.status == ResourceStatus.available,
            )
            .with_for_update(skip_locked=True)
        )
        res_result = await db.execute(res_stmt)
        res = res_result.scalar_one_or_none()

        if res is not None:
            # Mark resource tentative
            res.status = ResourceStatus.tentative
            res.held_by_tx = tx.tx_id
            res.version = res.version + 1
            res.updated_at = now_utc

            # Update TransactionResource
            tr_update = (
                update(TransactionResource)
                .where(
                    TransactionResource.tx_id == tx.tx_id,
                    TransactionResource.resource_id == rid,
                )
                .values(
                    hold_state=HoldState.tentative,
                    updated_at=now_utc,
                )
            )
            await db.execute(tr_update)
            await db.flush()

            held_resource_ids.append(rid)

            await create_audit_event(
                db=db,
                event_type="TENTATIVE_HOLD",
                tx_id=tx.tx_id,
                resource_id=rid,
            )
            await publish_event(
                "pubsub:dashboard",
                {
                    "event": "BUNDLE_PREPARE_UPDATE",
                    "tx_id": tx.tx_id,
                    "resource_id": rid,
                    "held": True,
                    "timestamp": now_utc.isoformat(),
                },
            )
        else:
            failed_resource_ids.append(rid)
            await publish_event(
                "pubsub:dashboard",
                {
                    "event": "BUNDLE_PREPARE_UPDATE",
                    "tx_id": tx.tx_id,
                    "resource_id": rid,
                    "held": False,
                    "timestamp": now_utc.isoformat(),
                },
            )
            # Break immediately on first failure to guarantee all-or-nothing
            break

    all_held = len(failed_resource_ids) == 0 and len(held_resource_ids) == len(tr_rows)

    logger.info(
        f"2PC Prepare completed for TX {tx.tx_id}. All held: {all_held} (Held: {len(held_resource_ids)}, Failed: {len(failed_resource_ids)})",
        extra={
            "tx_id": tx.tx_id,
            "all_held": all_held,
            "held_resource_ids": held_resource_ids,
            "failed_resource_ids": failed_resource_ids,
        },
    )

    return all_held, held_resource_ids, failed_resource_ids


async def commit_bundle(
    db: AsyncSession,
    tx: Transaction,
    held_resource_ids: List[str],
) -> List[str]:
    """
    2PC COMMIT phase for care bundles.
    
    Atomically upgrades all tentative holds to fully locked resources.
    Re-verifies strict hold counts prior to committing to prevent partial locks.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Re-verify count safeguard
    tentative_stmt = select(func.count(TransactionResource.resource_id)).where(
        TransactionResource.tx_id == tx.tx_id,
        TransactionResource.hold_state == HoldState.tentative,
    )
    tentative_count = (await db.execute(tentative_stmt)).scalar_one() or 0

    total_stmt = select(func.count(TransactionResource.resource_id)).where(
        TransactionResource.tx_id == tx.tx_id
    )
    total_count = (await db.execute(total_stmt)).scalar_one() or 0

    if tentative_count != total_count or total_count == 0:
        logger.error(
            f"Atomic verification failed for TX {tx.tx_id}: tentative={tentative_count}, total={total_count}",
            extra={"tx_id": tx.tx_id, "tentative_count": tentative_count, "total_count": total_count},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="bundle_partial_failure",
        )

    # 2. Transition TX to COMMITTING
    tx.state = TxState.COMMITTING
    tx.updated_at = now_utc
    h_committing = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.COMMITTING,
        occurred_at=now_utc,
    )
    db.add(h_committing)
    await db.flush()

    # 3. Upgrade tentative holds to locked
    for rid in held_resource_ids:
        res_stmt = (
            update(Resource)
            .where(
                Resource.resource_id == rid,
                Resource.held_by_tx == tx.tx_id,
                Resource.status == ResourceStatus.tentative,
            )
            .values(
                status=ResourceStatus.locked,
                version=Resource.version + 1,
                updated_at=now_utc,
            )
        )
        await db.execute(res_stmt)

        tr_stmt = (
            update(TransactionResource)
            .where(
                TransactionResource.tx_id == tx.tx_id,
                TransactionResource.resource_id == rid,
            )
            .values(
                hold_state=HoldState.held,
                updated_at=now_utc,
            )
        )
        await db.execute(tr_stmt)

    # 4. Transition TX to COMMITTED then ACTIVE
    tx.state = TxState.COMMITTED
    tx.updated_at = now_utc
    h_committed = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.COMMITTED,
        occurred_at=now_utc,
    )
    db.add(h_committed)

    tx.state = TxState.ACTIVE
    tx.updated_at = now_utc
    h_active = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.ACTIVE,
        occurred_at=now_utc,
    )
    db.add(h_active)
    await db.flush()

    cancel_ttl_expiry(tx.tx_id)

    # 5. Audit
    await create_audit_event(
        db=db,
        event_type="BUNDLE_COMMITTED",
        tx_id=tx.tx_id,
        decision="COMMIT",
        detail={"resources_locked": held_resource_ids},
    )

    # 6. Publish
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "TRANSACTION_UPDATED",
            "tx_id": tx.tx_id,
            "status": "COMMITTED",
            "timestamp": now_utc.isoformat(),
        },
    )

    logger.info(
        f"2PC Bundle committed successfully for TX {tx.tx_id} ({len(held_resource_ids)} resources locked)",
        extra={"tx_id": tx.tx_id, "resources_locked": held_resource_ids},
    )

    return held_resource_ids


async def rollback_bundle(
    db: AsyncSession,
    tx: Transaction,
    held_resource_ids: List[str],
    reason: str,
) -> List[str]:
    """
    2PC ROLLBACK phase for care bundles.
    
    Atomically releases all tentatively held resources upon any failure or conflict.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Transition TX to ROLLINGBACK
    tx.state = TxState.ROLLINGBACK
    tx.updated_at = now_utc
    h_rollingback = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.ROLLINGBACK,
        occurred_at=now_utc,
    )
    db.add(h_rollingback)
    await db.flush()

    # 2. Release all tentatively held resources
    for rid in held_resource_ids:
        res_stmt = (
            update(Resource)
            .where(
                Resource.resource_id == rid,
                Resource.held_by_tx == tx.tx_id,
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
                TransactionResource.tx_id == tx.tx_id,
                TransactionResource.resource_id == rid,
            )
            .values(
                hold_state=HoldState.released,
                updated_at=now_utc,
            )
        )
        await db.execute(tr_stmt)

    # 3. Mark un-held/failed resources as failed
    tr_failed_stmt = (
        update(TransactionResource)
        .where(
            TransactionResource.tx_id == tx.tx_id,
            TransactionResource.hold_state.in_([HoldState.requested, HoldState.tentative]),
        )
        .values(
            hold_state=HoldState.failed,
            updated_at=now_utc,
        )
    )
    await db.execute(tr_failed_stmt)

    # 4. Transition TX to ABORTED
    tx.state = TxState.ABORTED
    tx.updated_at = now_utc
    h_aborted = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.ABORTED,
        occurred_at=now_utc,
    )
    db.add(h_aborted)
    await db.flush()

    cancel_ttl_expiry(tx.tx_id)

    # 5. Audit
    await create_audit_event(
        db=db,
        event_type="BUNDLE_ROLLBACK",
        tx_id=tx.tx_id,
        decision="ROLLBACK",
        detail={
            "reason": reason,
            "resources_released": held_resource_ids,
        },
    )

    # 6. Publish
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "TRANSACTION_UPDATED",
            "tx_id": tx.tx_id,
            "status": "ABORTED",
            "timestamp": now_utc.isoformat(),
        },
    )

    logger.info(
        f"2PC Bundle rolled back for TX {tx.tx_id}. Reason: {reason}",
        extra={"tx_id": tx.tx_id, "reason": reason, "released": held_resource_ids},
    )

    return held_resource_ids


async def get_prepare_status(db: AsyncSession, tx_id: str) -> Dict[str, Any]:
    """
    Retrieves the current 2PC prepare status and per-resource hold state for a bundle transaction.
    """
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    req_type_str = tx.request_type.value if hasattr(tx.request_type, "value") else str(tx.request_type)
    if req_type_str != "care_bundle":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="not_a_bundle",
        )

    stmt = (
        select(TransactionResource)
        .where(TransactionResource.tx_id == tx_id)
        .order_by(TransactionResource.resource_id)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    phase_str = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
    resource_statuses = [
        {
            "resource_id": r.resource_id,
            "held": r.hold_state in (HoldState.tentative, HoldState.held, "tentative", "held"),
        }
        for r in rows
    ]
    all_held = all(item["held"] for item in resource_statuses) if resource_statuses else False

    return {
        "tx_id": tx_id,
        "phase": phase_str,
        "resources": resource_statuses,
        "all_held": all_held,
    }
