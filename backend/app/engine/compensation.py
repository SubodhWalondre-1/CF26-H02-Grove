from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import publish_event
from app.engine.locking import release_single_resource
from app.models.models import (
    CompensationEvent,
    DependencyEdge,
    HoldState,
    Resource,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
)
from app.services.audit import create_audit_event

logger = get_logger(__name__)


async def build_release_order(
    db: AsyncSession,
    tx_id: str,
) -> List[str]:
    """
    Determines the clinically safe, dependency-aware release order for resources
    held by a transaction using topological sorting on dependency_edges.
    
    Example: ventilator -> anesthesia -> surgeon -> ot.
    """
    # 1. Load resources held or associated with this transaction
    tr_stmt = (
        select(TransactionResource)
        .where(
            TransactionResource.tx_id == tx_id,
            TransactionResource.hold_state.in_([HoldState.held, HoldState.tentative]),
        )
    )
    tr_result = await db.execute(tr_stmt)
    tr_rows = list(tr_result.scalars().all())

    # Fallback to all transaction resources if no held rows found (e.g., pre-inspection)
    if not tr_rows:
        fallback_stmt = select(TransactionResource).where(
            TransactionResource.tx_id == tx_id
        )
        tr_result = await db.execute(fallback_stmt)
        tr_rows = list(tr_result.scalars().all())

    if not tr_rows:
        return []

    resource_ids = [tr.resource_id for tr in tr_rows]

    # 2. Fetch Resource objects to map resource_id -> type
    res_stmt = select(Resource).where(Resource.resource_id.in_(resource_ids))
    res_result = await db.execute(res_stmt)
    resources = list(res_result.scalars().all())

    # Map type -> list of resource_ids
    type_to_res_ids: Dict[str, List[str]] = defaultdict(list)
    res_id_to_type: Dict[str, str] = {}
    present_types: Set[str] = set()

    for r in resources:
        type_str = r.type.value if hasattr(r.type, "value") else str(r.type)
        type_to_res_ids[type_str].append(r.resource_id)
        res_id_to_type[r.resource_id] = type_str
        present_types.add(type_str)

    # 3. Load all dependency_edges
    edges_stmt = select(DependencyEdge)
    edges_result = await db.execute(edges_stmt)
    edges = list(edges_result.scalars().all())

    # 4. Build topological graph for present types
    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {t: 0 for t in present_types}

    for edge in edges:
        from_t = (
            edge.from_resource_type.value
            if hasattr(edge.from_resource_type, "value")
            else str(edge.from_resource_type)
        )
        to_t = (
            edge.to_resource_type.value
            if hasattr(edge.to_resource_type, "value")
            else str(edge.to_resource_type)
        )

        if from_t in present_types and to_t in present_types:
            adj[from_t].append(to_t)
            in_degree[to_t] += 1

    # Topological Sort via Kahn's algorithm
    queue = deque([t for t, deg in in_degree.items() if deg == 0])
    sorted_types: List[str] = []

    while queue:
        curr = queue.popleft()
        sorted_types.append(curr)
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Append any unvisited types (e.g. cycles or detached components)
    for t in present_types:
        if t not in sorted_types:
            sorted_types.append(t)

    # 5. Map sorted types back to resource_ids
    ordered_resource_ids: List[str] = []
    for t in sorted_types:
        for rid in sorted(type_to_res_ids[t]):
            ordered_resource_ids.append(rid)

    logger.info(
        f"Built release order for TX {tx_id}: {ordered_resource_ids}",
        extra={"tx_id": tx_id, "release_order": ordered_resource_ids},
    )

    return ordered_resource_ids


async def initiate_compensation(
    db: AsyncSession,
    tx: Transaction,
) -> List[str]:
    """
    Executes dependency-aware cascade compensation for an ACTIVE cancelled transaction.
    
    Releases each resource sequentially according to clinical dependencies, committing
    each release step individually to ensure durability against mid-flight crashes.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Transition TX to COMPENSATING
    tx.state = TxState.COMPENSATING
    tx.updated_at = now_utc
    h_comp = TransactionStateHistory(
        tx_id=tx.tx_id,
        state=TxState.COMPENSATING,
        occurred_at=now_utc,
    )
    db.add(h_comp)

    # 2. Build release order
    release_order = await build_release_order(db, tx.tx_id)

    # 3. Insert compensation_events rows
    for idx, rid in enumerate(release_order, start=1):
        ce = CompensationEvent(
            tx_id=tx.tx_id,
            resource_id=rid,
            release_order=idx,
            released_at=None,
            verified=False,
        )
        db.add(ce)

    # 4. Audit initiation
    await create_audit_event(
        db=db,
        event_type="COMPENSATION_INITIATED",
        tx_id=tx.tx_id,
        detail={"release_order": release_order},
    )

    # 5. Publish initial progress
    await publish_event(
        "pubsub:dashboard",
        {
            "event": "COMPENSATION_PROGRESS",
            "tx_id": tx.tx_id,
            "released": [],
            "pending": release_order,
            "timestamp": now_utc.isoformat(),
        },
    )

    # 6. Commit initial state setup
    await db.commit()

    # 7. Execute releases sequentially with per-resource commits
    for idx, rid in enumerate(release_order, start=1):
        rel_time = datetime.now(timezone.utc)

        # a. Release single resource
        await release_single_resource(db=db, tx_id=tx.tx_id, resource_id=rid)

        # b. Update compensation event
        ce_update = (
            update(CompensationEvent)
            .where(
                CompensationEvent.tx_id == tx.tx_id,
                CompensationEvent.resource_id == rid,
            )
            .values(
                released_at=rel_time,
                verified=True,
            )
        )
        await db.execute(ce_update)

        # c. Audit
        await create_audit_event(
            db=db,
            event_type="COMPENSATION_RESOURCE_RELEASED",
            tx_id=tx.tx_id,
            resource_id=rid,
            detail={"release_order_position": idx},
        )

        # d. Publish progress
        await publish_event(
            "pubsub:dashboard",
            {
                "event": "COMPENSATION_PROGRESS",
                "tx_id": tx.tx_id,
                "resource_released": rid,
                "timestamp": rel_time.isoformat(),
            },
        )

        # e. Commit after each release for crash resilience
        await db.commit()

    # 8. Check completion
    pending_stmt = select(func.count(CompensationEvent.id)).where(
        CompensationEvent.tx_id == tx.tx_id,
        CompensationEvent.released_at.is_(None),
    )
    pending_count = (await db.execute(pending_stmt)).scalar_one() or 0

    if pending_count == 0:
        close_time = datetime.now(timezone.utc)
        tx_ref = await db.get(Transaction, tx.tx_id)
        if tx_ref:
            tx_ref.state = TxState.CLOSED
            tx_ref.closed_at = close_time
            tx_ref.updated_at = close_time
            h_closed = TransactionStateHistory(
                tx_id=tx.tx_id,
                state=TxState.CLOSED,
                occurred_at=close_time,
            )
            db.add(h_closed)

        await create_audit_event(
            db=db,
            event_type="COMPENSATION_COMPLETE",
            tx_id=tx.tx_id,
        )
        await publish_event(
            "pubsub:dashboard",
            {
                "event": "TRANSACTION_UPDATED",
                "tx_id": tx.tx_id,
                "status": "CLOSED",
                "timestamp": close_time.isoformat(),
            },
        )
        await db.commit()

        try:
            from app.workers.tasks import generate_operation_record_pdf
            generate_operation_record_pdf.delay(tx.tx_id)
        except Exception as e:
            logger.warning(f"Could not dispatch generate_operation_record_pdf for tx={tx.tx_id}: {e}")

    logger.info(
        f"Cascade compensation complete for TX {tx.tx_id} ({len(release_order)} resources released)",
        extra={"tx_id": tx.tx_id, "release_order": release_order},
    )

    return release_order


async def get_dependency_graph(
    db: AsyncSession,
    tx_id: str,
) -> List[str]:
    """
    Returns the ordered topological release plan for a transaction's resources.
    Read-only inspection helper. Raises 404 if transaction is missing.
    """
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    return await build_release_order(db=db, tx_id=tx_id)


async def get_compensation_status(
    db: AsyncSession,
    tx_id: str,
) -> Dict[str, Any]:
    """
    Returns the live progress of cascade compensation for a transaction.
    """
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    stmt = (
        select(CompensationEvent)
        .where(CompensationEvent.tx_id == tx_id)
        .order_by(CompensationEvent.release_order.asc())
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    released = [e.resource_id for e in events if e.released_at is not None]
    pending = [e.resource_id for e in events if e.released_at is None]

    return {
        "tx_id": tx_id,
        "released": released,
        "pending": pending,
        "complete": len(pending) == 0 and len(events) > 0,
    }
