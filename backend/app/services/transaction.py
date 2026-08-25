from datetime import datetime, timezone
import hashlib
import secrets
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AdminConfig,
    AdminPolicy,
    ConflictTransaction,
    HoldState,
    Patient,
    RequestType,
    Resource,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
    User,
)
from app.schemas.schemas import CreateTransactionRequest
from app.services.audit import create_audit_event


def generate_tx_id() -> str:
    """
    Generates a unique transaction identifier in format TX-XXXX.
    """
    return f"TX-{secrets.token_hex(2)}"


def generate_fingerprint(
    patient_id: str,
    resource_ids: List[str],
    requested_quantity: Optional[int] = None,
    scheduled_start: Optional[str] = None,
    scheduled_end: Optional[str] = None,
) -> str:
    """
    Deterministically computes a request fingerprint FP-XXXX from patient ID and sorted resources.
    For pharmacy resources, includes requested_quantity.
    For diagnostic resources, includes scheduled_start/end time window.
    """
    raw_key = f"{patient_id}:{','.join(sorted(resource_ids))}"
    if requested_quantity is not None:
        raw_key += f":qty={requested_quantity}"
    if scheduled_start and scheduled_end:
        raw_key += f":window={scheduled_start}_{scheduled_end}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:4]
    return f"FP-{digest}"


async def create_transaction(
    db: AsyncSession,
    requesting_user: User,
    payload: CreateTransactionRequest,
) -> Transaction:
    """
    Validates authorization, verifies patient and resource existence, copies hold TTL,
    and inserts a new transaction in QUEUED state.
    """
    # 1. Authorization check via admin_policies
    user_role_str = (
        requesting_user.role.value
        if hasattr(requesting_user.role, "value")
        else str(requesting_user.role)
    )
    policy_stmt = select(AdminPolicy).where(
        AdminPolicy.role == user_role_str,
        AdminPolicy.action == payload.request_type,
    )
    policy_res = await db.execute(policy_stmt)
    policy = policy_res.scalar_one_or_none()

    if not policy or policy.scope == "denied":
        if payload.request_type == "care_bundle":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role is not authorized to request care bundles",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role is not authorized for this transaction type",
        )

    # 2. Validate patient existence
    patient_stmt = select(Patient).where(
        Patient.patient_id == payload.patient_id
    )
    patient_res = await db.execute(patient_stmt)
    patient = patient_res.scalar_one_or_none()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Patient '{payload.patient_id}' not found",
        )

    # 3. Determine and validate resource list
    if payload.request_type == "single_resource":
        resource_ids = [payload.resource_id]  # type: ignore
    else:
        resource_ids = list(payload.resource_ids or [])

    res_stmt = select(Resource.resource_id).where(
        Resource.resource_id.in_(resource_ids)
    )
    res_result = await db.execute(res_stmt)
    found_resources = set(res_result.scalars().all())

    missing_resources = set(resource_ids) - found_resources
    if missing_resources:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown resource(s): {', '.join(sorted(missing_resources))}",
        )

    # 4. Fetch current hold_ttl_seconds from admin_config
    config_stmt = select(AdminConfig.value).where(
        AdminConfig.key == "hold_ttl_seconds"
    )
    config_res = await db.execute(config_stmt)
    config_val = config_res.scalar_one_or_none()
    hold_ttl = int(config_val) if config_val is not None else 120

    # 5. Idempotency Gate Check & Claim
    from app.engine.idempotency import check_and_claim
    from app.core.redis import get_redis

    redis_client = None
    try:
        redis_client = await get_redis()
    except Exception:
        pass

    claim_res = await check_and_claim(
        redis_client=redis_client,
        db=db,
        request_type=payload.request_type,
        fields={"patient_id": payload.patient_id, "resource_ids": resource_ids},
        claimed_by=getattr(requesting_user, "username", None) or requesting_user.user_id,
        default_ttl_seconds=hold_ttl,
    )

    if claim_res.is_duplicate:
        if claim_res.existing_tx_id and claim_res.existing_tx_id != "PENDING":
            existing_tx = await db.get(Transaction, claim_res.existing_tx_id)
            if existing_tx:
                return existing_tx

    # 6. Generate identifiers
    tx_id = generate_tx_id()
    fingerprint = claim_res.fingerprint[:16] if claim_res.fingerprint else generate_fingerprint(payload.patient_id, resource_ids)
    now_utc = datetime.now(timezone.utc)

    # 7. Insert Transaction
    new_tx = Transaction(
        tx_id=tx_id,
        request_type=RequestType(payload.request_type),
        patient_id=payload.patient_id,
        requested_by=requesting_user.user_id,
        state=TxState.QUEUED,
        request_fingerprint=fingerprint,
        hold_ttl_seconds=hold_ttl,
        hold_expires_at=None,
        created_at=now_utc,
        updated_at=now_utc,
    )
    db.add(new_tx)

    # 7. Insert TransactionResource rows
    for r_id in resource_ids:
        tr = TransactionResource(
            tx_id=tx_id,
            resource_id=r_id,
            hold_state=HoldState.requested,
        )
        db.add(tr)

    # 8. Insert TransactionStateHistory (CREATED -> QUEUED)
    h_created = TransactionStateHistory(
        tx_id=tx_id,
        state=TxState.CREATED,
        occurred_at=now_utc,
    )
    h_queued = TransactionStateHistory(
        tx_id=tx_id,
        state=TxState.QUEUED,
        occurred_at=now_utc,
    )
    db.add(h_created)
    db.add(h_queued)

    # 9. Create Audit Event
    await create_audit_event(
        db=db,
        event_type="TRANSACTION_CREATED",
        tx_id=tx_id,
        detail={
            "request_type": payload.request_type,
            "patient_id": payload.patient_id,
            "resources": resource_ids,
        },
    )

    await db.commit()
    await db.refresh(new_tx)
    return new_tx


async def get_transaction(db: AsyncSession, tx_id: str) -> Transaction:
    """
    Queries a transaction by ID. Raises HTTP 404 if not found.
    """
    stmt = select(Transaction).where(Transaction.tx_id == tx_id)
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{tx_id}' not found",
        )

    return tx


async def get_transaction_detail(
    db: AsyncSession, tx_id: str
) -> Dict[str, Any]:
    """
    Retrieves full transaction detail including resource list, associated conflict ID,
    and computed remaining hold duration.
    """
    tx = await get_transaction(db=db, tx_id=tx_id)

    # Fetch resources
    res_stmt = (
        select(TransactionResource.resource_id)
        .where(TransactionResource.tx_id == tx_id)
        .order_by(TransactionResource.resource_id.asc())
    )
    res_result = await db.execute(res_stmt)
    resources = list(res_result.scalars().all())

    # Fetch unresolved conflict if any
    conflict_stmt = (
        select(ConflictTransaction.conflict_id)
        .where(ConflictTransaction.tx_id == tx_id)
        .order_by(ConflictTransaction.conflict_id.desc())
        .limit(1)
    )
    conflict_result = await db.execute(conflict_stmt)
    conflict_id = conflict_result.scalar_one_or_none()

    # Calculate remaining hold duration
    hold_remaining_seconds = None
    if tx.hold_expires_at:
        now_utc = datetime.now(timezone.utc)
        diff = (tx.hold_expires_at - now_utc).total_seconds()
        hold_remaining_seconds = max(0, int(diff))

    status_str = (
        tx.state.value if hasattr(tx.state, "value") else str(tx.state)
    )
    req_type_str = (
        tx.request_type.value
        if hasattr(tx.request_type, "value")
        else str(tx.request_type)
    )

    return {
        "tx_id": tx.tx_id,
        "status": status_str,
        "request_type": req_type_str,
        "patient_id": tx.patient_id,
        "resources": resources,
        "conflict_id": conflict_id,
        "hold_ttl_seconds": tx.hold_ttl_seconds,
        "hold_remaining_seconds": hold_remaining_seconds,
    }


async def list_transactions(
    db: AsyncSession,
    requesting_user: User,
    status_filter: Optional[str] = None,
    patient_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Transaction], int]:
    """
    Lists transactions with role-based scoping and optional filtering.
    """
    user_role_str = (
        requesting_user.role.value
        if hasattr(requesting_user.role, "value")
        else str(requesting_user.role)
    )

    stmt = select(Transaction)
    count_stmt = select(func.count(Transaction.tx_id))

    # Role scoping per Rule 4
    if user_role_str in ("doctor", "nurse"):
        # Note: Nurses are scoped to their own requests as a Phase-2 simplification of assigned cases
        stmt = stmt.where(Transaction.requested_by == requesting_user.user_id)
        count_stmt = count_stmt.where(
            Transaction.requested_by == requesting_user.user_id
        )

    # Apply filters
    if status_filter:
        stmt = stmt.where(Transaction.state == status_filter)
        count_stmt = count_stmt.where(Transaction.state == status_filter)

    if patient_id:
        stmt = stmt.where(Transaction.patient_id == patient_id)
        count_stmt = count_stmt.where(Transaction.patient_id == patient_id)

    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar_one()

    stmt = (
        stmt.order_by(Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total_count


async def get_state_history(
    db: AsyncSession, tx_id: str
) -> List[TransactionStateHistory]:
    """
    Validates transaction existence and returns all state transitions ordered chronologically.
    """
    await get_transaction(db=db, tx_id=tx_id)

    stmt = (
        select(TransactionStateHistory)
        .where(TransactionStateHistory.tx_id == tx_id)
        .order_by(TransactionStateHistory.occurred_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def cancel_transaction(
    db: AsyncSession,
    tx_id: str,
    requesting_user_id: str,
    reason: str,
) -> dict:
    """
    Cancels an active or in-flight transaction, delegating to the coordinator engine.
    """
    from app.engine.coordinator import cancel_transaction as engine_cancel

    return await engine_cancel(db, tx_id, requesting_user_id, reason)


async def complete_transaction(
    db: AsyncSession,
    tx_id: str,
    requesting_user_id: str,
) -> dict:
    """
    Completes an active transaction, delegating to the coordinator engine.
    """
    from app.engine.coordinator import complete_transaction as engine_complete

    return await engine_complete(db, tx_id, requesting_user_id)

