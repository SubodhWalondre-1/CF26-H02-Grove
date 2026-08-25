"""
Escalation API routes — Feature #16.

Enforces server-side RBAC:
  • Doctor and Admin: Allowed
  • Nurse: 403 Forbidden
"""

import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.redis import get_redis
from app.engine.escalation import request_escalation
from app.models.escalation import EscalationRequest
from app.models.models import (
    HoldState,
    Patient,
    RequestType,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
    User,
    UserRole,
)
from app.schemas.schemas import (
    EscalationCreateRequest,
    EscalationListResponse,
    EscalationResponse,
)
from app.services.transaction import generate_fingerprint

router = APIRouter(tags=["escalations"])


# =============================================================================
# 1. SUBMIT ESCALATION REQUEST (Doctor & Admin Only)
# =============================================================================
@router.post(
    "/api/v1/escalations",
    response_model=EscalationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an escalation / preemption request for a held resource",
)
async def create_escalation(
    payload: EscalationCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    user: User = Depends(get_current_active_user),
):
    # RBAC: Nurse explicitly denied
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val == "nurse":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nurse role is not permitted to submit escalation / preemption requests. Doctor or Admin required.",
        )

    # Validate patient
    patient = await db.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient {payload.patient_id} not found",
        )

    now_utc = datetime.now(timezone.utc)
    tx_id = f"TX-ESC-{secrets.token_hex(2)}"

    # Generate Idempotency Fingerprint
    fingerprint = generate_fingerprint(
        patient_id=payload.patient_id,
        resource_ids=[payload.target_resource_id, "ESCALATION"],
    )

    # Create Escalating Transaction
    tx = Transaction(
        tx_id=tx_id,
        request_type=RequestType.escalation,
        patient_id=payload.patient_id,
        requested_by=user.username,
        state=TxState.PREPARING,
        request_fingerprint=fingerprint,
        hold_ttl_seconds=300,
        created_at=now_utc,
        updated_at=now_utc,
    )
    db.add(tx)

    h = TransactionStateHistory(
        tx_id=tx_id,
        state=TxState.PREPARING,
        occurred_at=now_utc,
    )
    db.add(h)

    tr = TransactionResource(
        tx_id=tx_id,
        resource_id=payload.target_resource_id,
        hold_state=HoldState.tentative,
        updated_at=now_utc,
    )
    db.add(tr)
    await db.flush()

    # Invoke Escalation Arbiter Engine
    result = await request_escalation(
        db=db,
        escalating_tx_id=tx_id,
        target_resource_id=payload.target_resource_id,
        requested_by=user.username,
        source_feature="DIRECT",
        redis_client=redis,
    )

    if result.get("decision") == "APPROVED":
        tx.state = TxState.ACTIVE
        tr.hold_state = HoldState.held
    else:
        tx.state = TxState.ABORTED

    await db.commit()

    # Return full Escalation response
    return {
        "escalation_id": result["escalation_id"],
        "escalating_tx_id": tx_id,
        "target_resource_id": payload.target_resource_id,
        "holder_tx_id": result.get("holder_tx_id"),
        "escalating_acuity": result.get("escalating_acuity"),
        "holder_acuity": result.get("holder_acuity"),
        "decision": result["decision"],
        "rejection_reason": result.get("rejection_reason"),
        "requested_by": user.username,
        "requested_at": now_utc.isoformat(),
        "resolved_at": now_utc.isoformat(),
        "source_feature": "DIRECT",
        "suggested_alternative": result.get("suggested_alternative"),
    }


# =============================================================================
# 2. GET ESCALATION BY ID
# =============================================================================
@router.get(
    "/api/v1/escalations/{id}",
    response_model=EscalationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get status and outcome of an escalation request",
)
async def get_escalation(
    id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    try:
        esc_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format",
        )

    esc = await db.get(EscalationRequest, esc_uuid)
    if not esc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation request not found",
        )

    return {
        "escalation_id": str(esc.id),
        "escalating_tx_id": esc.escalating_tx_id,
        "target_resource_id": esc.target_resource_id,
        "holder_tx_id": esc.holder_tx_id,
        "escalating_acuity": float(esc.escalating_acuity) if esc.escalating_acuity is not None else None,
        "holder_acuity": float(esc.holder_acuity) if esc.holder_acuity is not None else None,
        "decision": esc.decision,
        "rejection_reason": esc.rejection_reason,
        "requested_by": esc.requested_by,
        "requested_at": esc.requested_at.isoformat() if esc.requested_at else None,
        "resolved_at": esc.resolved_at.isoformat() if esc.resolved_at else None,
        "source_feature": esc.source_feature,
    }


# =============================================================================
# 3. LIST ESCALATION ATTEMPTS (Audit Review)
# =============================================================================
@router.get(
    "/api/v1/escalations",
    response_model=EscalationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List historical escalation attempts against resources",
)
async def list_escalations(
    resource_id: Optional[str] = Query(None, description="Filter by target resource"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    query = select(EscalationRequest)
    if resource_id:
        query = query.where(EscalationRequest.target_resource_id == resource_id)

    query = query.order_by(EscalationRequest.requested_at.desc())
    res = await db.execute(query)
    items = list(res.scalars().all())

    response_items = []
    for esc in items:
        response_items.append({
            "escalation_id": str(esc.id),
            "escalating_tx_id": esc.escalating_tx_id,
            "target_resource_id": esc.target_resource_id,
            "holder_tx_id": esc.holder_tx_id,
            "escalating_acuity": float(esc.escalating_acuity) if esc.escalating_acuity is not None else None,
            "holder_acuity": float(esc.holder_acuity) if esc.holder_acuity is not None else None,
            "decision": esc.decision,
            "rejection_reason": esc.rejection_reason,
            "requested_by": esc.requested_by,
            "requested_at": esc.requested_at.isoformat() if esc.requested_at else None,
            "resolved_at": esc.resolved_at.isoformat() if esc.resolved_at else None,
            "source_feature": esc.source_feature,
        })

    return {"items": response_items, "total": len(response_items)}
