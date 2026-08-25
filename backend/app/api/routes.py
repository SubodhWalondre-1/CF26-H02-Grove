from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_active_user,
    get_current_user,
    get_db,
    get_pagination,
    require_admin,
)
from app.core.redis import get_redis
from app.engine import arbiter as arbiter_engine
from app.engine import compensation as compensation_engine
from app.engine import coordinator as coordinator_engine
from app.engine import recovery as recovery_engine
from app.engine import two_phase_commit as tpc_engine
from app.models.models import HoldState, Transaction, TransactionResource, User
from app.schemas.schemas import (
    AdminConfigResponse,
    AuditEventListResponse,
    AuditEventResponse,
    BedCleaningCompleteRequest,
    BedCleaningLogResponse,
    BedCleaningStartRequest,
    BedCreateRequest,
    BedGridFloor,
    BedMaintenanceRequest,
    BedReleaseRequest,
    BedResponse,
    BedShortageSummary,
    BundleCommitResponse,
    BundlePrepareStatusResponse,
    BundleRollbackResponse,
    CancelTransactionRequest,
    CancelTransactionResponse,
    CompensationStatusResponse,
    CompleteTransactionResponse,
    ConflictListResponse,
    ConflictResponse,
    ConflictTxEntry,
    CreateTransactionRequest,
    DependencyGraphResponse,
    ErrorResponse,
    FullTraceEntry,
    FullTraceResponse,
    IncompleteTransactionEntry,
    IncompleteTransactionsResponse,
    LoginRequest,
    MeResponse,
    PaginationParams,
    PatientAcuityResponse,
    PatientResponse,
    PolicyEntry,
    PolicyMatrixResponse,
    RecoveryResolveResponse,
    RecoveryRunEntry,
    RecoveryRunsResponse,
    RefreshRequest,
    ResourceHistoryEvent,
    ResourceHistoryResponse,
    ResourceListResponse,
    ResourceResponse,
    ScoreBreakdownResponse,
    StateHistoryEntry,
    StateHistoryResponse,
    TokenResponse,
    TransactionDetailResponse,
    TransactionListResponse,
    TransactionResponse,
    UpdateAdminConfigRequest,
    UpdatePolicyMatrixRequest,
)
from app.services import admin as admin_service
from app.services import audit as audit_service
from app.services import auth as auth_service
from app.services.bed import BedService, InvalidTransitionError
from app.services import patient as patient_service
from app.services import resource as resource_service
from app.services import transaction as transaction_service

router = APIRouter(prefix="/api/v1")


# =============================================================================
# HEALTH CHECK
# =============================================================================
@router.get(
    "/health",
    tags=["health"],
    status_code=status.HTTP_200_OK,
    summary="Service health check",
)
async def health_check() -> dict:
    """
    Public health check endpoint for container orchestrators and load balancers.
    """
    return {
        "status": "ok",
        "service": "mediora",
        "version": "1.0.0",
    }


# =============================================================================
# AUTH ROUTES
# =============================================================================
@router.post(
    "/auth/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["auth"],
    status_code=status.HTTP_200_OK,
    summary="User login",
)
async def login_user(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticates user credentials and returns JWT access tokens.
    """
    return await auth_service.login(
        db=db,
        username=request.username,
        password=request.password,
    )


@router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["auth"],
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Issues a new access token using a valid refresh token.
    """
    return await auth_service.refresh_access_token(
        refresh_token=request.refresh_token,
        db=db,
    )


@router.get(
    "/auth/me",
    response_model=MeResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    tags=["auth"],
    status_code=status.HTTP_200_OK,
    summary="Get current user profile and permissions",
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """
    Returns the authenticated user's profile and dynamic policy-driven permissions.
    """
    return await auth_service.get_me(db=db, user=current_user)


# =============================================================================
# PATIENTS ROUTES
# =============================================================================
@router.get(
    "/patients/{patient_id}",
    response_model=PatientResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["patients"],
    status_code=status.HTTP_200_OK,
    summary="Get patient details",
)
async def get_patient_by_id(
    patient_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PatientResponse:
    """
    Retrieves a registered patient record by identifier.
    """
    patient = await patient_service.get_patient(db=db, patient_id=patient_id)
    return PatientResponse(
        patient_id=patient.patient_id,
        name=patient.name,
        clinical_context=patient.clinical_context,
        base_acuity=float(patient.base_acuity),
    )


@router.get(
    "/patients/{patient_id}/acuity",
    response_model=PatientAcuityResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["patients"],
    status_code=status.HTTP_200_OK,
    summary="Get live patient acuity",
)
async def get_patient_acuity_by_id(
    patient_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PatientAcuityResponse:
    """
    Retrieves the live, non-cached clinical acuity score for a patient.
    """
    patient = await patient_service.get_patient_acuity(
        db=db, patient_id=patient_id
    )
    return PatientAcuityResponse(
        patient_id=patient.patient_id,
        base_acuity=float(patient.base_acuity),
        last_updated=patient.updated_at,
    )


# =============================================================================
# RESOURCES ROUTES
# =============================================================================
@router.get(
    "/resources",
    response_model=ResourceListResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["resources"],
    status_code=status.HTTP_200_OK,
    summary="List resources",
)
async def list_clinical_resources(
    type: Optional[str] = Query(
        None, description="Filter by resource type (e.g., ot, surgeon, anesthesia, ventilator)"
    ),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by resource status"
    ),
    pagination: PaginationParams = Depends(get_pagination),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ResourceListResponse:
    """
    Lists resources with optional type/status filters and hold status.
    """
    items, total = await resource_service.list_resources(
        db=db,
        resource_type=type,
        status_filter=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return ResourceListResponse(
        items=[ResourceResponse(**item) for item in items],
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


@router.get(
    "/resources/{resource_id}",
    response_model=ResourceResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["resources"],
    status_code=status.HTTP_200_OK,
    summary="Get resource details with hold expiration",
)
async def get_resource_by_id(
    resource_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ResourceResponse:
    """
    Retrieves detailed resource state and active hold expiration timestamps.
    """
    data = await resource_service.get_resource_with_hold_expiry(
        db=db, resource_id=resource_id
    )
    return ResourceResponse(**data)


@router.get(
    "/resources/{resource_id}/history",
    response_model=ResourceHistoryResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["resources"],
    status_code=status.HTTP_200_OK,
    summary="Get resource history audit trail",
)
async def get_resource_audit_history(
    resource_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ResourceHistoryResponse:
    """
    Retrieves chronological audit trail records for a given resource.
    """
    events = await resource_service.get_resource_history(
        db=db, resource_id=resource_id
    )
    return ResourceHistoryResponse(
        resource_id=resource_id,
        events=[
            ResourceHistoryEvent(
                audit_id=e.audit_id,
                event=e.event_type,
                tx_id=e.tx_id,
                timestamp=e.occurred_at,
            )
            for e in events
        ],
    )


# =============================================================================
# TRANSACTIONS ROUTES
# =============================================================================
@router.post(
    "/transactions",
    response_model=TransactionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    tags=["transactions"],
    status_code=status.HTTP_201_CREATED,
    summary="Create transaction request",
)
async def create_new_transaction(
    payload: CreateTransactionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """
    Submits a new single resource or care bundle request and processes it through the coordinator.
    """
    tx = await transaction_service.create_transaction(
        db=db,
        requesting_user=current_user,
        payload=payload,
    )

    # Process through coordinator state machine synchronously
    await coordinator_engine.process_transaction(db=db, tx_id=tx.tx_id)
    updated_tx = await transaction_service.get_transaction(db=db, tx_id=tx.tx_id)

    status_str = (
        updated_tx.state.value
        if hasattr(updated_tx.state, "value")
        else str(updated_tx.state)
    )
    req_type_str = (
        updated_tx.request_type.value
        if hasattr(updated_tx.request_type, "value")
        else str(updated_tx.request_type)
    )
    return TransactionResponse(
        tx_id=updated_tx.tx_id,
        status=status_str,
        request_type=req_type_str,
        request_fingerprint=updated_tx.request_fingerprint,
        created_at=updated_tx.created_at,
    )


@router.get(
    "/transactions/{tx_id}",
    response_model=TransactionDetailResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["transactions"],
    status_code=status.HTTP_200_OK,
    summary="Get transaction details",
)
async def get_transaction_by_id(
    tx_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionDetailResponse:
    """
    Retrieves full transaction status, resources, hold times, and conflict links.
    """
    tx_obj = await transaction_service.get_transaction(db=db, tx_id=tx_id)
    user_role_str = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )

    if user_role_str in ("doctor", "nurse"):
        if tx_obj.requested_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this transaction.",
            )

    data = await transaction_service.get_transaction_detail(
        db=db, tx_id=tx_id
    )
    return TransactionDetailResponse(**data)


@router.get(
    "/transactions",
    response_model=TransactionListResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["transactions"],
    status_code=status.HTTP_200_OK,
    summary="List transactions",
)
async def list_all_transactions(
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by transaction state"
    ),
    patient_id: Optional[str] = Query(
        None, description="Filter by patient ID"
    ),
    pagination: PaginationParams = Depends(get_pagination),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionListResponse:
    """
    Lists transactions scoped by user role with optional state/patient filtering.
    """
    items, total = await transaction_service.list_transactions(
        db=db,
        requesting_user=current_user,
        status_filter=status_filter,
        patient_id=patient_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return TransactionListResponse(
        items=[
            TransactionResponse(
                tx_id=t.tx_id,
                status=t.state.value
                if hasattr(t.state, "value")
                else str(t.state),
                request_type=t.request_type.value
                if hasattr(t.request_type, "value")
                else str(t.request_type),
                request_fingerprint=t.request_fingerprint,
                created_at=t.created_at,
            )
            for t in items
        ],
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


@router.get(
    "/transactions/{tx_id}/state-history",
    response_model=StateHistoryResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["transactions"],
    status_code=status.HTTP_200_OK,
    summary="Get transaction state history",
)
async def get_transaction_state_history(
    tx_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> StateHistoryResponse:
    """
    Retrieves chronological lifecycle state transitions for a transaction.
    """
    tx_obj = await transaction_service.get_transaction(db=db, tx_id=tx_id)
    user_role_str = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )

    if user_role_str in ("doctor", "nurse"):
        if tx_obj.requested_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access state history for this transaction.",
            )

    history = await transaction_service.get_state_history(db=db, tx_id=tx_id)
    return StateHistoryResponse(
        tx_id=tx_id,
        history=[
            StateHistoryEntry(
                state=h.state.value
                if hasattr(h.state, "value")
                else str(h.state),
                at=h.occurred_at,
            )
            for h in history
        ],
    )


@router.post(
    "/transactions/{tx_id}/cancel",
    response_model=CancelTransactionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["transactions"],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cancel transaction",
)
async def cancel_transaction_endpoint(
    tx_id: str,
    payload: CancelTransactionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CancelTransactionResponse:
    """
    Cancels an active or in-flight transaction, triggering cascade compensation if ACTIVE.
    """
    result = await transaction_service.cancel_transaction(
        db=db,
        tx_id=tx_id,
        requesting_user_id=current_user.user_id,
        reason=payload.reason,
    )
    return CancelTransactionResponse(**result)


@router.post(
    "/transactions/{tx_id}/complete",
    response_model=CompleteTransactionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["transactions"],
    status_code=status.HTTP_200_OK,
    summary="Complete transaction",
)
async def complete_transaction_endpoint(
    tx_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CompleteTransactionResponse:
    """
    Marks clinical care complete and releases all held resources.
    """
    result = await transaction_service.complete_transaction(
        db=db,
        tx_id=tx_id,
        requesting_user_id=current_user.user_id,
    )
    return CompleteTransactionResponse(**result)


# =============================================================================
# CONFLICTS ROUTES
# =============================================================================
@router.get(
    "/conflicts/{conflict_id}",
    response_model=ConflictResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["conflicts"],
    status_code=status.HTTP_200_OK,
    summary="Get conflict details",
)
async def get_conflict_by_id(
    conflict_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ConflictResponse:
    """
    Retrieves clinical conflict resolution details, participants, and winner.
    """
    conflict = await arbiter_engine.get_conflict(db=db, conflict_id=conflict_id)
    status_str = "resolved" if conflict.resolved_at is not None else "open"
    return ConflictResponse(
        conflict_id=conflict.conflict_id,
        resource_contested=conflict.resource_contested,
        transactions=[
            ConflictTxEntry(
                tx_id=ct.tx_id,
                effective_score=float(ct.effective_score),
            )
            for ct in conflict.conflict_transactions
        ],
        winner_tx_id=conflict.winner_tx_id,
        resolution="transaction_level",
        status=status_str,
        resolved_at=conflict.resolved_at,
        created_at=conflict.created_at,
    )


@router.get(
    "/conflicts/{conflict_id}/score-breakdown",
    response_model=ScoreBreakdownResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["conflicts"],
    status_code=status.HTTP_200_OK,
    summary="Get conflict transaction score breakdown",
)
async def get_conflict_score_breakdown(
    conflict_id: str,
    tx_id: Optional[str] = Query(None, description="Transaction ID to inspect"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreBreakdownResponse:
    """
    Retrieves the clinical score calculation components for a specific transaction in a conflict.
    """
    if not tx_id:
        conflict = await arbiter_engine.get_conflict(db=db, conflict_id=conflict_id)
        if conflict.conflict_transactions:
            tx_id = conflict.winner_tx_id or conflict.conflict_transactions[0].tx_id
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No transactions associated with this conflict",
            )

    data = await arbiter_engine.get_score_breakdown(
        db=db, conflict_id=conflict_id, tx_id=tx_id
    )
    return ScoreBreakdownResponse(**data)


@router.get(
    "/conflicts",
    response_model=ConflictListResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["conflicts"],
    status_code=status.HTTP_200_OK,
    summary="List conflicts",
)
async def list_clinical_conflicts(
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status ('open' or 'resolved')"
    ),
    resource_id: Optional[str] = Query(
        None, description="Filter by contested resource ID"
    ),
    tx_id: Optional[str] = Query(
        None, description="Filter by participating transaction ID"
    ),
    pagination: PaginationParams = Depends(get_pagination),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ConflictListResponse:
    """
    Lists clinical conflicts with optional status and participant filters.
    """
    items, total = await arbiter_engine.list_conflicts(
        db=db,
        status_filter=status_filter,
        resource_id=resource_id,
        tx_id=tx_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return ConflictListResponse(
        items=[
            ConflictResponse(
                conflict_id=c.conflict_id,
                resource_contested=c.resource_contested,
                transactions=[
                    ConflictTxEntry(
                        tx_id=ct.tx_id,
                        effective_score=float(ct.effective_score),
                    )
                    for ct in c.conflict_transactions
                ],
                winner_tx_id=c.winner_tx_id,
                resolution="transaction_level",
                status="resolved" if c.resolved_at is not None else "open",
                resolved_at=c.resolved_at,
                created_at=c.created_at,
            )
            for c in items
        ],
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


# =============================================================================
# BUNDLES ROUTES
# =============================================================================
@router.get(
    "/bundles/{tx_id}/prepare-status",
    response_model=BundlePrepareStatusResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["bundles"],
    status_code=status.HTTP_200_OK,
    summary="Get 2PC prepare status",
)
async def get_bundle_prepare_status_endpoint(
    tx_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BundlePrepareStatusResponse:
    """
    Returns the real-time Two-Phase Commit prepare status and resource holds for a care bundle.
    """
    data = await tpc_engine.get_prepare_status(db=db, tx_id=tx_id)
    return BundlePrepareStatusResponse(**data)


@router.post(
    "/bundles/{tx_id}/commit",
    response_model=BundleCommitResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["bundles"],
    status_code=status.HTTP_200_OK,
    summary="Admin override: Commit 2PC bundle",
)
async def admin_commit_bundle_endpoint(
    tx_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BundleCommitResponse:
    """
    Admin debug endpoint to force-commit an in-flight 2PC bundle.
    """
    stmt = select(Transaction).where(Transaction.tx_id == tx_id).with_for_update()
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()
    req_type = tx.request_type.value if tx and hasattr(tx.request_type, "value") else str(tx.request_type if tx else "")
    state_str = tx.state.value if tx and hasattr(tx.state, "value") else str(tx.state if tx else "")

    if not tx or req_type != "care_bundle" or state_str != "PREPARING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="invalid_state",
        )

    tr_stmt = select(TransactionResource).where(TransactionResource.tx_id == tx_id)
    tr_result = await db.execute(tr_stmt)
    tr_rows = list(tr_result.scalars().all())

    held_ids = [
        r.resource_id
        for r in tr_rows
        if r.hold_state in (HoldState.tentative, "tentative")
    ]
    if len(held_ids) != len(tr_rows) or len(tr_rows) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot commit: not all resources are tentatively held.",
        )

    locked_ids = await tpc_engine.commit_bundle(
        db=db, tx=tx, held_resource_ids=held_ids
    )
    await db.commit()

    return BundleCommitResponse(
        tx_id=tx_id,
        status="COMMITTED",
        resources_locked=locked_ids,
    )


@router.post(
    "/bundles/{tx_id}/rollback",
    response_model=BundleRollbackResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["bundles"],
    status_code=status.HTTP_200_OK,
    summary="Admin override: Rollback 2PC bundle",
)
async def admin_rollback_bundle_endpoint(
    tx_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BundleRollbackResponse:
    """
    Admin debug endpoint to force-rollback an in-flight 2PC bundle.
    """
    stmt = select(Transaction).where(Transaction.tx_id == tx_id).with_for_update()
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()
    req_type = tx.request_type.value if tx and hasattr(tx.request_type, "value") else str(tx.request_type if tx else "")
    state_str = tx.state.value if tx and hasattr(tx.state, "value") else str(tx.state if tx else "")

    if not tx or req_type != "care_bundle" or state_str != "PREPARING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="invalid_state",
        )

    tr_stmt = select(TransactionResource).where(TransactionResource.tx_id == tx_id)
    tr_result = await db.execute(tr_stmt)
    tr_rows = list(tr_result.scalars().all())

    held_ids = [
        r.resource_id
        for r in tr_rows
        if r.hold_state in (HoldState.tentative, "tentative")
    ]
    released_ids = await tpc_engine.rollback_bundle(
        db=db, tx=tx, held_resource_ids=held_ids, reason="ADMIN_ROLLBACK"
    )
    await db.commit()

    return BundleRollbackResponse(
        tx_id=tx_id,
        status="ABORTED",
        resources_released=released_ids,
        reason="ADMIN_ROLLBACK",
    )


# =============================================================================
# COMPENSATION ROUTES
# =============================================================================
@router.get(
    "/compensation/{tx_id}/dependency-graph",
    response_model=DependencyGraphResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["compensation"],
    status_code=status.HTTP_200_OK,
    summary="Get cascade release order",
)
async def get_compensation_dependency_graph(
    tx_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DependencyGraphResponse:
    """
    Retrieves the topological release sequence for clinical resources associated with a transaction.
    """
    order = await compensation_engine.get_dependency_graph(db=db, tx_id=tx_id)
    return DependencyGraphResponse(tx_id=tx_id, release_order=order)


@router.get(
    "/compensation/{tx_id}/status",
    response_model=CompensationStatusResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["compensation"],
    status_code=status.HTTP_200_OK,
    summary="Get compensation progress",
)
async def get_compensation_progress_status(
    tx_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CompensationStatusResponse:
    """
    Retrieves live status of released vs pending resources during cascade compensation.
    """
    data = await compensation_engine.get_compensation_status(
        db=db, tx_id=tx_id
    )
    return CompensationStatusResponse(**data)


# =============================================================================
# ADMIN ROUTES
# =============================================================================
@router.get(
    "/admin/policies",
    response_model=PolicyMatrixResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["admin"],
    status_code=status.HTTP_200_OK,
    summary="Get role policy matrix",
)
async def get_role_policy_matrix(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PolicyMatrixResponse:
    """
    Retrieves the entire role-based authorization policy matrix.
    """
    policies = await admin_service.get_policy_matrix(db=db)
    return PolicyMatrixResponse(
        policies=[
            PolicyEntry(
                role=p.role.value
                if hasattr(p.role, "value")
                else str(p.role),
                action=p.action,
                scope=p.scope,
            )
            for p in policies
        ]
    )


@router.put(
    "/admin/policies",
    response_model=PolicyMatrixResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    tags=["admin"],
    status_code=status.HTTP_200_OK,
    summary="Update role policy matrix",
)
async def update_role_policy_matrix(
    payload: UpdatePolicyMatrixRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PolicyMatrixResponse:
    """
    Updates or inserts policy definitions across roles. Admin only.
    """
    policies = await admin_service.update_policy_matrix(
        db=db,
        updates=payload.policies,
        updated_by=current_user,
    )
    return PolicyMatrixResponse(
        policies=[
            PolicyEntry(
                role=p.role.value
                if hasattr(p.role, "value")
                else str(p.role),
                action=p.action,
                scope=p.scope,
            )
            for p in policies
        ]
    )


@router.get(
    "/admin/config",
    response_model=AdminConfigResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["admin"],
    status_code=status.HTTP_200_OK,
    summary="Get coordinator configuration",
)
async def get_coordinator_admin_config(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AdminConfigResponse:
    """
    Retrieves tunable coordinator parameters (Hold TTL and fairness wait coefficient).
    """
    cfg = await admin_service.get_admin_config(db=db)
    return AdminConfigResponse(**cfg)


@router.put(
    "/admin/config",
    response_model=AdminConfigResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    tags=["admin"],
    status_code=status.HTTP_200_OK,
    summary="Update coordinator configuration",
)
async def update_coordinator_admin_config(
    payload: UpdateAdminConfigRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminConfigResponse:
    """
    Updates coordinator parameters in real time. Admin only.
    """
    cfg = await admin_service.update_admin_config(
        db=db,
        updates=payload,
        updated_by=current_user,
    )
    return AdminConfigResponse(**cfg)


# =============================================================================
# RECOVERY ROUTES
# =============================================================================
@router.get(
    "/recovery/incomplete-transactions",
    response_model=IncompleteTransactionsResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    tags=["recovery"],
    status_code=status.HTTP_200_OK,
    summary="List incomplete transactions",
)
async def list_incomplete_transactions(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> IncompleteTransactionsResponse:
    """
    Scans for in-flight transactions requiring recovery or TTL verification. Admin only.
    """
    items = await recovery_engine.scan_incomplete_transactions(db=db)
    return IncompleteTransactionsResponse(
        items=[IncompleteTransactionEntry(**item) for item in items]
    )


@router.post(
    "/recovery/{tx_id}/resolve",
    response_model=RecoveryResolveResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["recovery"],
    status_code=status.HTTP_200_OK,
    summary="Manually resolve incomplete transaction",
)
async def manually_resolve_transaction(
    tx_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RecoveryResolveResponse:
    """
    Executes manual recovery on a specific in-flight transaction. Admin only.
    """
    result = await recovery_engine.resolve_transaction(
        db=db, tx_id=tx_id, triggered_by="manual"
    )
    return RecoveryResolveResponse(**result)


@router.get(
    "/recovery/runs",
    response_model=RecoveryRunsResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    tags=["recovery"],
    status_code=status.HTTP_200_OK,
    summary="List recovery scan runs",
)
async def list_recovery_runs_endpoint(
    pagination: PaginationParams = Depends(get_pagination),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RecoveryRunsResponse:
    """
    Retrieves paginated historical crash-recovery audit runs. Admin only.
    """
    items, total = await recovery_engine.list_recovery_runs(
        db=db,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return RecoveryRunsResponse(
        items=[RecoveryRunEntry(**item) for item in items],
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


# =============================================================================
# AUDIT ROUTES
# =============================================================================
@router.get(
    "/audit/events",
    response_model=AuditEventListResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["audit"],
    status_code=status.HTTP_200_OK,
    summary="Query audit events",
)
async def query_system_audit_events(
    tx_id: Optional[str] = Query(
        None, description="Filter audit events by transaction ID"
    ),
    event_type: Optional[str] = Query(
        None, description="Filter by event type identifier"
    ),
    from_ts: Optional[datetime] = Query(
        None, alias="from", description="Earliest timestamp (ISO-8601)"
    ),
    to_ts: Optional[datetime] = Query(
        None, alias="to", description="Latest timestamp (ISO-8601)"
    ),
    pagination: PaginationParams = Depends(get_pagination),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AuditEventListResponse:
    """
    Queries immutable audit log records with role-scoping and multi-field filters.
    """
    items, total = await audit_service.list_audit_events(
        db=db,
        requesting_user=current_user,
        tx_id=tx_id,
        event_type=event_type,
        from_ts=from_ts,
        to_ts=to_ts,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return AuditEventListResponse(
        items=[
            AuditEventResponse(
                audit_id=e.audit_id,
                tx_id=e.tx_id,
                conflict_id=e.conflict_id,
                effective_score=float(e.effective_score)
                if e.effective_score is not None
                else None,
                decision=e.decision,
                timestamp=e.occurred_at,
            )
            for e in items
        ],
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


@router.get(
    "/audit/{tx_id}/full-trace",
    response_model=FullTraceResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["audit"],
    status_code=status.HTTP_200_OK,
    summary="Get complete transaction audit trace",
)
async def get_transaction_full_trace(
    tx_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FullTraceResponse:
    """
    Retrieves the complete chronological lifecycle event trail for a transaction.
    """
    tx_obj = await transaction_service.get_transaction(db=db, tx_id=tx_id)
    user_role_str = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )

    if user_role_str in ("doctor", "nurse"):
        if tx_obj.requested_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view audit trace for this transaction.",
            )

    events = await audit_service.get_full_trace(db=db, tx_id=tx_id)
    return FullTraceResponse(
        tx_id=tx_id,
        trace=[
            FullTraceEntry(
                audit_id=e.audit_id,
                event_type=e.event_type,
                decision=e.decision,
                effective_score=float(e.effective_score)
                if e.effective_score is not None
                else None,
                detail=e.detail,
                timestamp=e.occurred_at,
            )
            for e in events
        ],
    )


# =============================================================================
# BED MANAGEMENT ROUTES
# =============================================================================

@router.get("/beds", response_model=List[BedResponse], tags=["Bed Management"])
async def list_beds(
    bed_type: Optional[str] = None,
    floor: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """All beds with optional filters."""
    service = BedService(db, redis)
    return await service.get_all_beds(bed_type, floor, status)


@router.get(
    "/beds/available",
    response_model=List[BedResponse],
    tags=["Bed Management"],
)
async def get_available_beds(
    bed_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """
    Returns ONLY READY beds.
    Used by: AI Recommendation Engine, Transaction Request Builder.
    """
    service = BedService(db, redis)
    return await service.get_ready_beds(bed_type)


@router.get(
    "/beds/grid",
    response_model=List[BedGridFloor],
    tags=["Bed Management"],
)
async def get_bed_grid(
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """Floor-wise grouped beds for dashboard visual grid."""
    service = BedService(db, redis)
    return await service.get_bed_grid()


@router.get(
    "/beds/shortage",
    response_model=List[dict],
    tags=["Bed Management"],
)
async def get_shortage_summary(
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """Ready-count vs threshold per bed type. Used by donation board."""
    service = BedService(db, redis)
    return await service.get_shortage_summary()


@router.get(
    "/beds/{bed_id}",
    response_model=BedResponse,
    tags=["Bed Management"],
)
async def get_bed(
    bed_id: str,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    service = BedService(db, redis)
    bed = await service.get_bed_by_id(bed_id)
    if not bed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bed {bed_id} not found",
        )
    return bed


@router.post("/beds/{bed_id}/release", tags=["Bed Management"])
async def release_bed(
    bed_id: str,
    body: BedReleaseRequest,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """
    Release bed after patient discharge/transfer.
    Automatically triggers cleaning workflow.
    """
    service = BedService(db, redis)
    emp_id = getattr(user, "employee_id", user.user_id)
    try:
        bed = await service.release_bed(bed_id, body.release_reason, emp_id)
        return {
            "message": f"Bed {bed.bed_number} released. Cleaning initiated.",
            "bed_id": bed.id,
            "new_status": bed.status.value
            if hasattr(bed.status, "value")
            else str(bed.status),
            "estimated_ready_at": bed.estimated_ready_at.isoformat()
            if bed.estimated_ready_at
            else None,
        }
    except InvalidTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/beds/{bed_id}/cleaning/start", tags=["Bed Management"])
async def start_cleaning(
    bed_id: str,
    body: BedCleaningStartRequest,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """Housekeeping marks cleaning started."""
    service = BedService(db, redis)
    emp_id = getattr(user, "employee_id", user.user_id)
    log = await service.start_cleaning(bed_id, emp_id, body.estimated_minutes)
    return {
        "message": "Cleaning started",
        "cleaning_log_id": log.id,
        "started_at": log.started_at.isoformat(),
    }


@router.post("/beds/cleaning/complete", tags=["Bed Management"])
async def complete_cleaning(
    body: BedCleaningCompleteRequest,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """Housekeeping verifies cleaning — bed becomes READY."""
    service = BedService(db, redis)
    emp_id = getattr(user, "employee_id", user.user_id)
    bed = await service.complete_cleaning(
        body.cleaning_log_id, emp_id, body.notes
    )
    return {
        "message": f"Bed {bed.bed_number} is now READY",
        "bed_id": bed.id,
        "new_status": bed.status.value
            if hasattr(bed.status, "value")
            else str(bed.status),
    }


@router.post("/beds/{bed_id}/maintenance", tags=["Bed Management"])
async def set_maintenance(
    bed_id: str,
    body: BedMaintenanceRequest,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(require_admin),  # admin only
):
    """Put bed in maintenance. Only admins."""
    service = BedService(db, redis)
    emp_id = getattr(user, "employee_id", user.user_id)
    try:
        bed = await service.set_maintenance(bed_id, body.reason, emp_id)
        return {
            "message": f"Bed {bed.bed_number} placed in maintenance",
            "bed_id": bed.id,
        }
    except InvalidTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/beds/{bed_id}/maintenance/resolve", tags=["Bed Management"])
async def resolve_maintenance(
    bed_id: str,
    db: AsyncSession = Depends(get_db),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
    user: User = Depends(require_admin),
):
    """Mark maintenance done — triggers cleaning → READY."""
    service = BedService(db, redis)
    emp_id = getattr(user, "employee_id", user.user_id)
    bed = await service.resolve_maintenance(bed_id, emp_id)
    return {
        "message": f"Bed {bed.bed_number} maintenance resolved. Cleaning initiated."
    }


@router.get("/metrics/idempotency", tags=["System Metrics"])
async def get_idempotency_metrics(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    """Returns aggregated count of suppressed duplicates."""
    from app.models.idempotency import IdempotencyKey
    stmt = select(func.coalesce(func.sum(IdempotencyKey.duplicate_hits), 0))
    res = await db.execute(stmt)
    total_blocked = res.scalar_one() or 0
    return {"duplicates_blocked": int(total_blocked)}


@router.get("/metrics/overrides", tags=["System Metrics"])
async def get_override_metrics(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    """Returns count of emergency override events triggered today."""
    from datetime import datetime, timezone, timedelta
    from app.models.override import EmergencyOverrideEvent
    now_utc = datetime.now(timezone.utc)
    today_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    stmt = select(func.count(EmergencyOverrideEvent.id)).where(EmergencyOverrideEvent.created_at >= today_start)
    res = await db.execute(stmt)
    overrides_today = res.scalar_one() or 0
    return {"overrides_today": int(overrides_today)}

