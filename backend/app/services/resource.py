from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditEvent, Resource, Transaction


async def get_resource(db: AsyncSession, resource_id: str) -> Resource:
    """
    Queries a resource by its identifier.
    Raises HTTP 404 if the resource does not exist.
    """
    stmt = select(Resource).where(Resource.resource_id == resource_id)
    result = await db.execute(stmt)
    resource = result.scalar_one_or_none()

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found",
        )

    return resource


async def list_resources(
    db: AsyncSession,
    resource_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Lists resources with optional filtering by type and status,
    including pagination and hold expiration calculation.
    """
    # Base query joining Transaction to resolve hold expiration
    stmt = select(Resource, Transaction.hold_expires_at).outerjoin(
        Transaction, Resource.held_by_tx == Transaction.tx_id
    )
    count_stmt = select(func.count(Resource.resource_id))

    # Apply filters
    if resource_type:
        stmt = stmt.where(Resource.type == resource_type)
        count_stmt = count_stmt.where(Resource.type == resource_type)

    if status_filter:
        stmt = stmt.where(Resource.status == status_filter)
        count_stmt = count_stmt.where(Resource.status == status_filter)

    # Compute total matching count
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar_one()

    # Apply pagination and sorting
    stmt = (
        stmt.order_by(Resource.resource_id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for res, hold_expires_at in rows:
        type_str = res.type.value if hasattr(res.type, "value") else str(res.type)
        status_str = (
            res.status.value if hasattr(res.status, "value") else str(res.status)
        )
        items.append(
            {
                "resource_id": res.resource_id,
                "type": type_str,
                "label": res.label,
                "status": status_str,
                "criticality": float(res.criticality),
                "held_by_tx": res.held_by_tx,
                "hold_expires_at": hold_expires_at if res.held_by_tx else None,
            }
        )

    return items, total_count


async def get_resource_with_hold_expiry(
    db: AsyncSession, resource_id: str
) -> Dict[str, Any]:
    """
    Retrieves a single resource and resolves its current hold_expires_at timestamp.
    """
    resource = await get_resource(db=db, resource_id=resource_id)

    hold_expires_at = None
    if resource.held_by_tx:
        tx_stmt = select(Transaction.hold_expires_at).where(
            Transaction.tx_id == resource.held_by_tx
        )
        tx_result = await db.execute(tx_stmt)
        hold_expires_at = tx_result.scalar_one_or_none()

    type_str = (
        resource.type.value
        if hasattr(resource.type, "value")
        else str(resource.type)
    )
    status_str = (
        resource.status.value
        if hasattr(resource.status, "value")
        else str(resource.status)
    )

    return {
        "resource_id": resource.resource_id,
        "type": type_str,
        "label": resource.label,
        "status": status_str,
        "criticality": float(resource.criticality),
        "held_by_tx": resource.held_by_tx,
        "hold_expires_at": hold_expires_at,
    }


async def get_resource_history(
    db: AsyncSession, resource_id: str
) -> List[AuditEvent]:
    """
    Validates resource existence and retrieves all historical audit trail events in chronological order.
    """
    await get_resource(db=db, resource_id=resource_id)

    stmt = (
        select(AuditEvent)
        .where(AuditEvent.resource_id == resource_id)
        .order_by(AuditEvent.occurred_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
