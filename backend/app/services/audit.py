from datetime import datetime, timezone
from decimal import Decimal
import secrets
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.models import AuditEvent, Transaction, User

logger = get_logger(__name__)


def generate_audit_id() -> str:
    """
    Generates a unique audit identifier in the format 'AUD-XXXX'.
    """
    return f"AUD-{secrets.token_hex(4)}"


async def create_audit_event(
    db: AsyncSession,
    event_type: str,
    tx_id: Optional[str] = None,
    conflict_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    decision: Optional[str] = None,
    effective_score: Optional[float] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """
    Creates, persists, and logs an AuditEvent record in the database.
    """
    audit_id = generate_audit_id()
    score_decimal = (
        Decimal(str(effective_score)) if effective_score is not None else None
    )

    audit_event = AuditEvent(
        audit_id=audit_id,
        tx_id=tx_id,
        conflict_id=conflict_id,
        resource_id=resource_id,
        event_type=event_type,
        decision=decision,
        effective_score=score_decimal,
        detail=detail,
        occurred_at=datetime.now(timezone.utc),
    )

    db.add(audit_event)
    await db.commit()
    await db.refresh(audit_event)

    logger.info(
        f"Audit event recorded: {event_type} (ID: {audit_id})",
        extra={
            "audit_id": audit_id,
            "event_type": event_type,
            "tx_id": tx_id,
            "conflict_id": conflict_id,
            "resource_id": resource_id,
            "decision": decision,
            "effective_score": effective_score,
            "detail": detail,
        },
    )

    return audit_event


async def list_audit_events(
    db: AsyncSession,
    requesting_user: Optional[User] = None,
    tx_id: Optional[str] = None,
    event_type: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[AuditEvent], int]:
    """
    Queries historical audit log records with optional filtering, role-based scoping, and pagination,
    ordered by most recent first.
    """
    stmt = select(AuditEvent)
    count_stmt = select(func.count(AuditEvent.audit_id))

    if requesting_user:
        user_role_str = (
            requesting_user.role.value
            if hasattr(requesting_user.role, "value")
            else str(requesting_user.role)
        )
        if user_role_str in ("doctor", "nurse"):
            stmt = stmt.join(
                Transaction, AuditEvent.tx_id == Transaction.tx_id
            ).where(Transaction.requested_by == requesting_user.user_id)
            count_stmt = count_stmt.join(
                Transaction, AuditEvent.tx_id == Transaction.tx_id
            ).where(Transaction.requested_by == requesting_user.user_id)

    if tx_id:
        stmt = stmt.where(AuditEvent.tx_id == tx_id)
        count_stmt = count_stmt.where(AuditEvent.tx_id == tx_id)

    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
        count_stmt = count_stmt.where(AuditEvent.event_type == event_type)

    if from_ts:
        stmt = stmt.where(AuditEvent.occurred_at >= from_ts)
        count_stmt = count_stmt.where(AuditEvent.occurred_at >= from_ts)

    if to_ts:
        stmt = stmt.where(AuditEvent.occurred_at <= to_ts)
        count_stmt = count_stmt.where(AuditEvent.occurred_at <= to_ts)

    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar_one()

    stmt = (
        stmt.order_by(AuditEvent.occurred_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total_count



async def get_full_trace(db: AsyncSession, tx_id: str) -> List[AuditEvent]:
    """
    Retrieves the complete chronological audit trail trace for a given transaction.
    """
    tx_stmt = select(Transaction).where(Transaction.tx_id == tx_id)
    tx_res = await db.execute(tx_stmt)
    tx = tx_res.scalar_one_or_none()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{tx_id}' not found",
        )

    stmt = (
        select(AuditEvent)
        .where(AuditEvent.tx_id == tx_id)
        .order_by(AuditEvent.occurred_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

