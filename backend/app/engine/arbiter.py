from datetime import datetime, timezone
from decimal import Decimal
import secrets
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.redis import publish_event
from app.models.models import (
    Conflict,
    ConflictTransaction,
    Resource,
    Transaction,
    TransactionStateHistory,
    TxState,
)
from app.services.admin import get_admin_config
from app.services.audit import create_audit_event
from app.services.patient import get_patient_acuity

logger = get_logger(__name__)


def generate_conflict_id() -> str:
    """
    Returns a unique conflict identifier in the format 'CF-XXXX'.
    """
    return f"CF-{secrets.token_hex(4)}"


def compute_wait_contribution(tx: Transaction, coefficient: float) -> float:
    """
    Calculates wait time contribution to the clinical priority score:
    elapsed minutes since tx.created_at * wait_coefficient_per_min.
    """
    now_utc = datetime.now(timezone.utc)
    created_at = (
        tx.created_at
        if tx.created_at.tzinfo is not None
        else tx.created_at.replace(tzinfo=timezone.utc)
    )
    elapsed_seconds = (now_utc - created_at).total_seconds()
    elapsed_minutes = max(0.0, elapsed_seconds / 60.0)
    return round(elapsed_minutes * coefficient, 4)


def compute_effective_score(
    base_acuity: float = 0.0,
    wait_minutes: float = 0.0,
    wait_coefficient: float = 0.12,
    criticality: float = 1.0,
) -> float:
    """
    Calculates the deterministic clinical effective priority score:
    (base_acuity + wait_minutes * wait_coefficient) * criticality
    """
    wait_contribution = wait_minutes * wait_coefficient
    return (base_acuity + wait_contribution) * criticality


def select_winner(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Selects the winning candidate based on highest effective_score.
    Tie-breaks deterministically by earlier created_at timestamp.
    Raises ValueError if candidates list is empty.
    """
    if not candidates:
        raise ValueError("Candidates list cannot be empty")

    def sort_key(c: Dict[str, Any]):
        score = float(c.get("effective_score", 0.0))
        created = c.get("created_at")

        if isinstance(created, str):
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                created_dt = datetime.max.replace(tzinfo=timezone.utc)
        elif isinstance(created, datetime):
            created_dt = (
                created
                if created.tzinfo is not None
                else created.replace(tzinfo=timezone.utc)
            )
        else:
            created_dt = datetime.max.replace(tzinfo=timezone.utc)

        return (-score, created_dt)

    return min(candidates, key=sort_key)


async def compute_tx_effective_score(
    db: AsyncSession,
    tx: Transaction,
    resource: Resource,
) -> Tuple[float, float, float, float]:
    """
    Computes (base_acuity, wait_contribution, resource_criticality, effective_score)
    using live patient base_acuity and live admin coordinator configuration.
    """
    patient = await get_patient_acuity(db=db, patient_id=tx.patient_id)
    base_acuity = float(patient.base_acuity)

    admin_cfg = await get_admin_config(db=db)
    coefficient = float(admin_cfg.get("wait_coefficient_per_min", 0.12))

    now_utc = datetime.now(timezone.utc)
    created_at = (
        tx.created_at
        if tx.created_at.tzinfo is not None
        else tx.created_at.replace(tzinfo=timezone.utc)
    )
    elapsed_minutes = max(0.0, (now_utc - created_at).total_seconds() / 60.0)
    wait_contribution = compute_wait_contribution(tx, coefficient)
    resource_criticality = float(resource.criticality)

    effective_score = round(
        compute_effective_score(
            base_acuity=base_acuity,
            wait_minutes=elapsed_minutes,
            wait_coefficient=coefficient,
            criticality=resource_criticality,
        ),
        2,
    )

    return base_acuity, wait_contribution, resource_criticality, effective_score


async def detect_and_arbitrate(
    db: AsyncSession,
    incoming_tx: Transaction,
    contested_resource_id: str,
) -> Tuple[Transaction, Optional[str]]:
    """
    Core clinical arbitration function (Rules 2, 3, and 6).
    
    Evaluates competing transactions via deterministic composite scoring:
    effective_score = (base_acuity + (elapsed_mins * wait_coefficient)) * resource_criticality
    
    Returns (winner_tx, conflict_id). If no conflict exists (resource freed), returns (incoming_tx, None).
    """
    now_utc = datetime.now(timezone.utc)

    # 1. FIND THE HOLDING TRANSACTION
    res_stmt = select(Resource).where(Resource.resource_id == contested_resource_id)
    res_result = await db.execute(res_stmt)
    resource = res_result.scalar_one_or_none()

    if not resource or resource.held_by_tx is None:
        logger.info(
            f"No holding transaction found on resource {contested_resource_id} (race resolved)",
            extra={"tx_id": incoming_tx.tx_id, "resource_id": contested_resource_id},
        )
        return incoming_tx, None

    held_tx_id = resource.held_by_tx

    # 2. LOAD BOTH TRANSACTIONS
    held_tx = await db.get(Transaction, held_tx_id)
    if not held_tx:
        logger.warning(
            f"Held transaction {held_tx_id} not found in database",
            extra={"held_tx_id": held_tx_id, "resource_id": contested_resource_id},
        )
        return incoming_tx, None

    # 3. TRANSITION INCOMING TX TO ARBITRATING
    incoming_tx.state = TxState.ARBITRATING
    incoming_tx.updated_at = now_utc

    h2 = TransactionStateHistory(
        tx_id=incoming_tx.tx_id, state=TxState.ARBITRATING, occurred_at=now_utc
    )
    db.add(h2)

    # 4. COMPUTE EFFECTIVE SCORES
    held_base, held_wait, held_crit, held_score = await compute_tx_effective_score(
        db, held_tx, resource
    )
    inc_base, inc_wait, inc_crit, inc_score = await compute_tx_effective_score(
        db, incoming_tx, resource
    )

    # 5. CREATE CONFLICT RECORD
    conflict_id = generate_conflict_id()
    conflict = Conflict(
        conflict_id=conflict_id,
        resource_contested=contested_resource_id,
        winner_tx_id=None,
        resolution_level="transaction",
        created_at=now_utc,
    )
    db.add(conflict)

    # 6. INSERT CONFLICT_TRANSACTIONS ROWS
    ct_held = ConflictTransaction(
        conflict_id=conflict_id,
        tx_id=held_tx.tx_id,
        base_acuity=Decimal(str(held_base)),
        wait_contribution=Decimal(str(held_wait)),
        resource_criticality=Decimal(str(held_crit)),
        effective_score=Decimal(str(held_score)),
        outcome="pending",
    )
    ct_inc = ConflictTransaction(
        conflict_id=conflict_id,
        tx_id=incoming_tx.tx_id,
        base_acuity=Decimal(str(inc_base)),
        wait_contribution=Decimal(str(inc_wait)),
        resource_criticality=Decimal(str(inc_crit)),
        effective_score=Decimal(str(inc_score)),
        outcome="pending",
    )
    db.add(ct_held)
    db.add(ct_inc)

    # 7. SELECT WINNER (with deterministic tie-breaker on created_at)
    candidates = [
        {
            "tx": held_tx,
            "tx_id": held_tx.tx_id,
            "effective_score": held_score,
            "created_at": held_tx.created_at,
        },
        {
            "tx": incoming_tx,
            "tx_id": incoming_tx.tx_id,
            "effective_score": inc_score,
            "created_at": incoming_tx.created_at,
        },
    ]
    winner_cand = select_winner(candidates)
    winner_tx = winner_cand["tx"]
    loser_tx = held_tx if winner_tx == incoming_tx else incoming_tx

    winner_score = inc_score if winner_tx == incoming_tx else held_score
    loser_score = held_score if winner_tx == incoming_tx else inc_score

    # 8. UPDATE RECORDS WITH WINNER/LOSER
    conflict.winner_tx_id = winner_tx.tx_id
    conflict.resolved_at = now_utc

    if winner_tx == incoming_tx:
        ct_inc.outcome = "winner"
        ct_held.outcome = "loser"
        # held_tx lost: transition held_tx to QUEUED and release its hold
        held_tx.state = TxState.QUEUED
        held_tx.updated_at = now_utc
        h_held_queued = TransactionStateHistory(
            tx_id=held_tx.tx_id, state=TxState.QUEUED, occurred_at=now_utc
        )
        db.add(h_held_queued)
        from app.engine.locking import release_single_resource
        await release_single_resource(db, held_tx.tx_id, contested_resource_id)
    else:
        ct_held.outcome = "winner"
        ct_inc.outcome = "loser"
        # incoming_tx lost: transition incoming_tx to QUEUED
        incoming_tx.state = TxState.QUEUED
        incoming_tx.updated_at = now_utc
        h_inc_queued = TransactionStateHistory(
            tx_id=incoming_tx.tx_id, state=TxState.QUEUED, occurred_at=now_utc
        )
        db.add(h_inc_queued)

    # 10. WRITE AUDIT EVENTS (two: one per transaction)
    await create_audit_event(
        db=db,
        event_type="ARBITRATION_RESULT",
        tx_id=winner_tx.tx_id,
        conflict_id=conflict_id,
        resource_id=contested_resource_id,
        decision="WINNER",
        effective_score=winner_score,
        detail={
            "loser_tx_id": loser_tx.tx_id,
            "resource_contested": contested_resource_id,
            "winner_score": winner_score,
            "loser_score": loser_score,
        },
    )
    await create_audit_event(
        db=db,
        event_type="ARBITRATION_RESULT",
        tx_id=loser_tx.tx_id,
        conflict_id=conflict_id,
        resource_id=contested_resource_id,
        decision="LOSER",
        effective_score=loser_score,
        detail={
            "winner_tx_id": winner_tx.tx_id,
            "resource_contested": contested_resource_id,
            "winner_score": winner_score,
            "loser_score": loser_score,
        },
    )

    # 11. PUBLISH TO REDIS
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "CONFLICT_DETECTED",
            "conflict_id": conflict_id,
            "resource_contested": contested_resource_id,
            "timestamp": now_utc.isoformat(),
        },
    )
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "ARBITRATION_RESULT",
            "conflict_id": conflict_id,
            "winner_tx_id": winner_tx.tx_id,
            "loser_tx_id": loser_tx.tx_id,
            "timestamp": now_utc.isoformat(),
        },
    )

    # 12. COMMIT DB CHANGES
    await db.commit()

    logger.info(
        f"Conflict {conflict_id} resolved. Winner: {winner_tx.tx_id} (score {winner_score}), Loser: {loser_tx.tx_id} (score {loser_score})",
        extra={
            "conflict_id": conflict_id,
            "winner_tx_id": winner_tx.tx_id,
            "loser_tx_id": loser_tx.tx_id,
            "contested_resource_id": contested_resource_id,
        },
    )

    # 13. RETURN WINNER AND CONFLICT_ID
    return winner_tx, conflict_id


async def get_conflict(db: AsyncSession, conflict_id: str) -> Conflict:
    """
    Retrieves a Conflict entity by identifier with eager-loaded conflict_transactions.
    Raises 404 if not found.
    """
    stmt = (
        select(Conflict)
        .options(selectinload(Conflict.conflict_transactions))
        .where(Conflict.conflict_id == conflict_id)
    )
    result = await db.execute(stmt)
    conflict = result.scalar_one_or_none()

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found",
        )

    return conflict


async def list_conflicts(
    db: AsyncSession,
    status_filter: Optional[str] = None,
    resource_id: Optional[str] = None,
    tx_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Conflict], int]:
    """
    Lists conflicts with optional status, resource, and transaction filters.
    Returns (conflicts_list, total_count).
    """
    base_query = select(Conflict).options(
        selectinload(Conflict.conflict_transactions)
    )
    count_query = select(func.count(Conflict.conflict_id))

    filters = []

    if status_filter == "open":
        filters.append(Conflict.resolved_at.is_(None))
    elif status_filter == "resolved":
        filters.append(Conflict.resolved_at.is_not(None))

    if resource_id:
        filters.append(Conflict.resource_contested == resource_id)

    if tx_id:
        filters.append(
            Conflict.conflict_transactions.any(
                ConflictTransaction.tx_id == tx_id
            )
        )

    if filters:
        base_query = base_query.where(*filters)
        count_query = count_query.where(*filters)

    # Total count
    total_result = await db.execute(count_query)
    total = total_result.scalar_one() or 0

    # Paginated results
    offset = (page - 1) * page_size
    paginated_query = (
        base_query.order_by(Conflict.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(paginated_query)
    items = list(result.scalars().all())

    return items, total


async def get_score_breakdown(
    db: AsyncSession,
    conflict_id: str,
    tx_id: str,
) -> Dict[str, Any]:
    """
    Fetches the historical clinical score breakdown snapshot for a transaction in a conflict.
    Raises 404 if the conflict transaction record is missing.
    """
    stmt = select(ConflictTransaction).where(
        ConflictTransaction.conflict_id == conflict_id,
        ConflictTransaction.tx_id == tx_id,
    )
    result = await db.execute(stmt)
    ct = result.scalar_one_or_none()

    if not ct:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Score breakdown not found for this transaction and conflict",
        )

    admin_cfg = await get_admin_config(db=db)
    wait_coeff = float(admin_cfg.get("wait_coefficient_per_min", 0.12))

    return {
        "tx_id": ct.tx_id,
        "base_acuity": float(ct.base_acuity),
        "wait_contribution": float(ct.wait_contribution),
        "wait_coefficient_per_min": wait_coeff,
        "resource_criticality": float(ct.resource_criticality),
        "effective_score": float(ct.effective_score),
        "formula": "(base_acuity + wait_contribution) * resource_criticality",
    }
