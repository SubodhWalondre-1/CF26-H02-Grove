from datetime import datetime, timezone
from decimal import Decimal
import secrets
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import (
    clear_hold_ttl,
    clear_ttl_warned,
    mark_ttl_warned,
    publish_event,
)
from app.engine.two_phase_commit import rollback_bundle
from app.models.models import (
    AuditEvent,
    HoldState,
    Resource,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
)
from app.services.audit import create_audit_event

logger = get_logger(__name__)


def generate_run_id() -> str:
    """
    Returns a unique recovery scan run identifier in the format 'RUN-XXXX'.
    """
    return f"RUN-{secrets.token_hex(2)}"


async def expire_hold(
    db: AsyncSession,
    tx_id: str,
    reason: str = "TTL_EXPIRED",
) -> Optional[str]:
    """
    Core TTL-rollback orchestrator implementing Rule 5.
    
    Guarded strictly by Postgres transaction state verification.
    Rolls back tentatively held bundle resources, logs audit events, and cleans up Redis flags.
    """
    tx = await db.get(Transaction, tx_id)
    if tx is None:
        return None

    state_str = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
    if state_str != "PREPARING":
        await clear_hold_ttl(tx_id)
        return None

    # Retrieve all tentatively held or held resources for this transaction
    tr_stmt = select(TransactionResource).where(
        TransactionResource.tx_id == tx_id,
        TransactionResource.hold_state.in_([HoldState.tentative, HoldState.held, "tentative", "held"]),
    )
    tr_result = await db.execute(tr_stmt)
    tr_rows = list(tr_result.scalars().all())
    held_resource_ids = [r.resource_id for r in tr_rows]

    # Roll back bundle holds atomically
    released_ids = await rollback_bundle(db=db, tx=tx, held_resource_ids=held_resource_ids, reason=reason)

    # Record TTL-specific audit event
    await create_audit_event(
        db=db,
        event_type="ROLLBACK",
        tx_id=tx_id,
        decision="ROLLBACK",
        detail={"reason": reason, "released": released_ids},
    )

    # Redis cleanups
    await clear_hold_ttl(tx_id)
    await clear_ttl_warned(tx_id)

    await db.commit()

    logger.info(
        f"TTL expired for TX {tx_id}. Resources released: {released_ids}",
        extra={"tx_id": tx_id, "released_ids": released_ids, "reason": reason},
    )

    return "ABORTED"


async def check_and_warn_ttl(
    db: AsyncSession,
    tx: Transaction,
) -> None:
    """
    Emits a TTL_WARNING event once remaining hold duration drops below the warning threshold.
    Deduplicated via Redis atomic flags to prevent repeated notifications.
    """
    if not tx.hold_expires_at:
        return

    now_utc = datetime.now(timezone.utc)
    exp = (
        tx.hold_expires_at
        if tx.hold_expires_at.tzinfo is not None
        else tx.hold_expires_at.replace(tzinfo=timezone.utc)
    )
    remaining = (exp - now_utc).total_seconds()

    if remaining > settings.ttl_warning_threshold_seconds:
        return

    newly_warned = await mark_ttl_warned(
        tx_id=tx.tx_id,
        ttl_seconds=max(1, int(remaining) + 1),
    )
    if not newly_warned:
        return

    remaining_val = max(0.0, round(remaining, 1))
    await create_audit_event(
        db=db,
        event_type="TTL_WARNING",
        tx_id=tx.tx_id,
        detail={
            "remaining_seconds": remaining_val,
            "hold_ttl_seconds": tx.hold_ttl_seconds,
        },
    )
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "TTL_WARNING",
            "tx_id": tx.tx_id,
            "remaining_seconds": remaining_val,
            "hold_ttl_seconds": tx.hold_ttl_seconds,
            "timestamp": now_utc.isoformat(),
        },
    )
    await db.commit()


async def run_ttl_sweep(db: AsyncSession) -> Dict[str, Any]:
    """
    Periodic safety-net sweep that expires overdue holds and emits warning events.
    """
    now_utc = datetime.now(timezone.utc)

    stmt = select(Transaction).where(
        Transaction.state == TxState.PREPARING,
        Transaction.hold_expires_at.is_not(None),
    )
    result = await db.execute(stmt)
    transactions = list(result.scalars().all())

    expired: List[str] = []

    for tx in transactions:
        exp = (
            tx.hold_expires_at
            if tx.hold_expires_at.tzinfo is not None
            else tx.hold_expires_at.replace(tzinfo=timezone.utc)
        )
        remaining = (exp - now_utc).total_seconds()

        if remaining <= 0:
            res = await expire_hold(db=db, tx_id=tx.tx_id, reason="TTL_EXPIRED")
            if res:
                expired.append(tx.tx_id)
        else:
            await check_and_warn_ttl(db=db, tx=tx)

    if expired:
        logger.info(
            f"TTL sweep expired {len(expired)} hold(s): {', '.join(expired)}",
            extra={"expired_count": len(expired), "expired_tx_ids": expired},
        )
    else:
        logger.debug(f"TTL sweep checked {len(transactions)} transaction(s); 0 expired.")

    return {
        "checked": len(transactions),
        "expired": expired,
        "swept_at": now_utc.isoformat(),
    }


async def scan_incomplete_transactions(db: AsyncSession) -> List[Dict[str, Any]]:
    """
    Scans for transactions in non-terminal, in-flight states (PREPARING, COMMITTING, ROLLINGBACK, ARBITRATING).
    """
    now_utc = datetime.now(timezone.utc)

    stmt = select(Transaction).where(
        Transaction.state.in_([
            TxState.PREPARING,
            TxState.COMMITTING,
            TxState.ROLLINGBACK,
            TxState.ARBITRATING,
            "PREPARING",
            "COMMITTING",
            "ROLLINGBACK",
            "ARBITRATING",
        ])
    )
    result = await db.execute(stmt)
    transactions = list(result.scalars().all())

    items = []
    for r in transactions:
        state_str = r.state.value if hasattr(r.state, "value") else str(r.state)
        exp = (
            r.hold_expires_at.replace(tzinfo=timezone.utc)
            if r.hold_expires_at and r.hold_expires_at.tzinfo is None
            else r.hold_expires_at
        )
        ttl_expired = (
            state_str == "PREPARING"
            and exp is not None
            and exp < now_utc
        )
        items.append({
            "tx_id": r.tx_id,
            "state": state_str,
            "ttl_expired": ttl_expired,
        })

    return items


async def resolve_transaction(
    db: AsyncSession,
    tx_id: str,
    triggered_by: str = "manual",
) -> Dict[str, Any]:
    """
    Reconciles an in-flight transaction against PostgreSQL ground truth.
    Handles PREPARING, ARBITRATING, COMMITTING, and ROLLINGBACK states.
    """
    now_utc = datetime.now(timezone.utc)

    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    state_str = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
    recoverable_states = {"PREPARING", "COMMITTING", "ROLLINGBACK", "ARBITRATING"}

    if state_str not in recoverable_states:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transaction {tx_id} is in terminal/active state {state_str} and does not need recovery.",
        )

    action_taken = ""
    reason = ""
    verified_state = ""

    if state_str == "PREPARING":
        exp = (
            tx.hold_expires_at.replace(tzinfo=timezone.utc)
            if tx.hold_expires_at and tx.hold_expires_at.tzinfo is None
            else tx.hold_expires_at
        )
        ttl_expired = exp is not None and exp < now_utc
        if ttl_expired:
            await expire_hold(db=db, tx_id=tx_id, reason="TTL_EXPIRED")
            action_taken, reason, verified_state = "ROLLBACK", "TTL_EXPIRED", "ABORTED"
        else:
            action_taken, reason, verified_state = "RECOVER", "TTL_NOT_EXPIRED", "PREPARING"

    elif state_str == "ARBITRATING":
        tx.state = TxState.QUEUED
        tx.updated_at = now_utc
        h_requeue = TransactionStateHistory(
            tx_id=tx_id,
            state=TxState.QUEUED,
            occurred_at=now_utc,
        )
        db.add(h_requeue)
        action_taken, reason, verified_state = "REQUEUE", "CRASH_DURING_ARBITRATION", "QUEUED"

    elif state_str == "COMMITTING":
        total_stmt = select(func.count(TransactionResource.resource_id)).where(
            TransactionResource.tx_id == tx_id
        )
        total = (await db.execute(total_stmt)).scalar_one() or 0

        held_stmt = select(func.count(TransactionResource.resource_id)).where(
            TransactionResource.tx_id == tx_id,
            TransactionResource.hold_state.in_([HoldState.held, "held"]),
        )
        held = (await db.execute(held_stmt)).scalar_one() or 0

        if held == total and total > 0:
            tx.state = TxState.ACTIVE
            tx.updated_at = now_utc
            h_active = TransactionStateHistory(
                tx_id=tx_id,
                state=TxState.ACTIVE,
                occurred_at=now_utc,
            )
            db.add(h_active)
            action_taken, reason, verified_state = "KEEP", "COMMIT_ALREADY_PERSISTED", "ACTIVE"
        else:
            tr_stmt = select(TransactionResource).where(
                TransactionResource.tx_id == tx_id,
                TransactionResource.hold_state.in_([HoldState.tentative, HoldState.held, "tentative", "held"]),
            )
            tr_res = await db.execute(tr_stmt)
            held_ids = [r.resource_id for r in tr_res.scalars().all()]
            await rollback_bundle(db=db, tx=tx, held_resource_ids=held_ids, reason="CRASH_DURING_COMMIT")
            action_taken, reason, verified_state = "ROLLBACK", "CRASH_DURING_COMMIT", "ABORTED"

    elif state_str == "ROLLINGBACK":
        tr_stmt = select(TransactionResource).where(
            TransactionResource.tx_id == tx_id,
            TransactionResource.hold_state.in_([HoldState.tentative, HoldState.held, "tentative", "held"]),
        )
        tr_res = await db.execute(tr_stmt)
        held_ids = [r.resource_id for r in tr_res.scalars().all()]

        if held_ids:
            await rollback_bundle(db=db, tx=tx, held_resource_ids=held_ids, reason="CRASH_DURING_ROLLBACK")
            action_taken, reason, verified_state = "ROLLBACK", "CRASH_DURING_ROLLBACK", "ABORTED"
        else:
            tx.state = TxState.ABORTED
            tx.updated_at = now_utc
            h_aborted = TransactionStateHistory(
                tx_id=tx_id,
                state=TxState.ABORTED,
                occurred_at=now_utc,
            )
            db.add(h_aborted)
            action_taken, reason, verified_state = "KEEP", "ROLLBACK_ALREADY_COMPLETE", "ABORTED"

    # Write Recovery Audit Event
    await create_audit_event(
        db=db,
        event_type="RECOVERY_ACTION",
        tx_id=tx_id,
        decision=action_taken,
        detail={
            "reason": reason,
            "triggered_by": triggered_by,
            "verified_state": verified_state,
        },
    )

    # Publish Recovery Action
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "RECOVERY_ACTION",
            "tx_id": tx_id,
            "action_taken": action_taken,
            "reason": reason,
            "verified_state": verified_state,
            "timestamp": now_utc.isoformat(),
        },
    )

    await db.commit()

    logger.info(
        f"Recovered transaction {tx_id}: action={action_taken}, reason={reason}, final_state={verified_state}",
        extra={"tx_id": tx_id, "action": action_taken, "reason": reason, "verified_state": verified_state},
    )

    return {
        "tx_id": tx_id,
        "action_taken": action_taken,
        "reason": reason,
        "verified_state": verified_state,
    }


async def run_crash_recovery_scan(
    db: AsyncSession,
    triggered_by: str = "startup",
) -> Dict[str, Any]:
    """
    Executes a complete recovery scan over all in-flight incomplete transactions.
    """
    run_id = generate_run_id()
    started_at = datetime.now(timezone.utc)

    incomplete = await scan_incomplete_transactions(db)
    resolved = []

    for entry in incomplete:
        res = await resolve_transaction(db=db, tx_id=entry["tx_id"], triggered_by=triggered_by)
        resolved.append(res)

    completed_at = datetime.now(timezone.utc)

    # Log summary audit event
    await create_audit_event(
        db=db,
        event_type="RECOVERY_RUN",
        tx_id=None,
        detail={
            "run_id": run_id,
            "triggered_by": triggered_by,
            "scanned_count": len(incomplete),
            "resolved_count": len(resolved),
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        },
    )
    await db.commit()

    logger.info(
        f"Recovery run {run_id} ({triggered_by}) completed: scanned {len(incomplete)}, resolved {len(resolved)}",
        extra={"run_id": run_id, "scanned_count": len(incomplete), "resolved_count": len(resolved)},
    )

    return {
        "run_id": run_id,
        "triggered_by": triggered_by,
        "started_at": started_at,
        "completed_at": completed_at,
        "scanned_count": len(incomplete),
        "resolved_count": len(resolved),
        "resolved": resolved,
    }


async def list_recovery_runs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Lists historical crash-recovery audit runs from the audit_events table.
    """
    count_stmt = select(func.count(AuditEvent.audit_id)).where(
        AuditEvent.event_type == "RECOVERY_RUN"
    )
    total = (await db.execute(count_stmt)).scalar_one() or 0

    offset = (page - 1) * page_size
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.event_type == "RECOVERY_RUN")
        .order_by(AuditEvent.occurred_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    items = []
    for r in events:
        detail = r.detail or {}
        items.append({
            "run_id": detail.get("run_id", f"RUN-{r.audit_id}"),
            "triggered_by": detail.get("triggered_by", "manual"),
            "started_at": detail.get("started_at", r.occurred_at.isoformat()),
            "completed_at": detail.get("completed_at", r.occurred_at.isoformat()),
            "scanned_count": detail.get("scanned_count", 0),
            "resolved_count": detail.get("resolved_count", 0),
        })

    return items, total
