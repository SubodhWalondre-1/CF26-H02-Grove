"""
API routes for Feature #18: Emergency Override Gate & Governance
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_active_user,
    get_db,
    require_admin,
    require_doctor_or_admin,
)
from app.core.redis import get_redis
from app.engine.override import evaluate_override
from app.models.models import (
    AdminConfig,
    Patient,
    Transaction,
    TransactionResource,
    User,
)
from app.models.override import (
    EmergencyOverrideEvent,
    OverrideTriggerType,
)
from app.schemas.schemas import (
    DeclareEmergencyRequest,
    EmergencyOverrideEventResponse,
    EmergencyOverrideListResponse,
    UpdateOverrideThresholdRequest,
)
from app.services.audit import create_audit_event

router = APIRouter(tags=["Emergency Override"])


# ─────────────────────────────────────────────────────────────────────────────
# 1. MANUAL EMERGENCY DECLARE
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/transactions/{tx_id}/declare-emergency",
    response_model=EmergencyOverrideEventResponse,
    status_code=status.HTTP_200_OK,
)
async def declare_emergency(
    tx_id: str,
    payload: DeclareEmergencyRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[aioredis.Redis] = Depends(get_redis),
    current_user: User = Depends(require_doctor_or_admin),
):
    """
    Manually declares an Emergency Override for a transaction.
    Restricted to Doctor and Admin roles with mandatory clinical reason string.
    """
    # 1. Verify Transaction exists
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{tx_id}' not found.",
        )

    # 2. Verify Patient Acuity
    patient = await db.get(Patient, tx.patient_id)
    acuity_score = float(patient.base_acuity) if patient else 5.0

    # 3. Collect requested resources
    stmt = select(TransactionResource.resource_id).where(
        TransactionResource.tx_id == tx_id
    )
    res = await db.execute(stmt)
    resources = list(res.scalars().all())

    # 4. Execute Emergency Override Gate
    user_identifier = getattr(current_user, "username", None) or current_user.user_id
    override_res = await evaluate_override(
        db=db,
        tx_id=tx_id,
        patient_id=tx.patient_id,
        acuity_score=acuity_score,
        requested_resources=resources,
        requested_by=user_identifier,
        manual_reason=payload.reason,
        redis_client=redis_client,
    )

    if not override_res.is_override or not override_res.event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to evaluate emergency override.",
        )

    tx.emergency_override = True
    await db.commit()

    # 5. Load and return created event
    evt = await db.get(EmergencyOverrideEvent, override_res.event_id)
    return EmergencyOverrideEventResponse(
        id=str(evt.id),
        tx_id=evt.tx_id,
        patient_id=evt.patient_id,
        trigger_type=evt.trigger_type,
        acuity_score_at_trigger=float(evt.acuity_score_at_trigger),
        manual_reason=evt.manual_reason,
        requested_by=evt.requested_by,
        resources_requested=evt.resources_requested,
        escalation_ids=[str(u) for u in evt.escalation_ids] if evt.escalation_ids else [],
        latency_ms=evt.latency_ms,
        flagged_for_review=evt.flagged_for_review,
        flag_reason=evt.flag_reason,
        created_at=evt.created_at.isoformat(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. ADMIN LIST OVERRIDES (GOVERNANCE & AUDIT)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/admin/overrides",
    response_model=EmergencyOverrideListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_emergency_overrides(
    flagged_for_review: Optional[bool] = Query(None, description="Filter by review flag"),
    requested_by: Optional[str] = Query(None, description="Filter by staff ID/username"),
    patient_id: Optional[str] = Query(None, description="Filter by patient ID"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Lists emergency override events for retrospective governance auditing.
    """
    stmt = select(EmergencyOverrideEvent).order_by(desc(EmergencyOverrideEvent.created_at))

    if flagged_for_review is not None:
        stmt = stmt.where(EmergencyOverrideEvent.flagged_for_review == flagged_for_review)
    if requested_by:
        stmt = stmt.where(EmergencyOverrideEvent.requested_by == requested_by)
    if patient_id:
        stmt = stmt.where(EmergencyOverrideEvent.patient_id == patient_id)

    res = await db.execute(stmt)
    records = list(res.scalars().all())

    items = [
        EmergencyOverrideEventResponse(
            id=str(evt.id),
            tx_id=evt.tx_id,
            patient_id=evt.patient_id,
            trigger_type=evt.trigger_type,
            acuity_score_at_trigger=float(evt.acuity_score_at_trigger),
            manual_reason=evt.manual_reason,
            requested_by=evt.requested_by,
            resources_requested=evt.resources_requested,
            escalation_ids=[str(u) for u in evt.escalation_ids] if evt.escalation_ids else [],
            latency_ms=evt.latency_ms,
            flagged_for_review=evt.flagged_for_review,
            flag_reason=evt.flag_reason,
            created_at=evt.created_at.isoformat(),
        )
        for evt in records
    ]

    return EmergencyOverrideListResponse(items=items, total=len(items))


# ─────────────────────────────────────────────────────────────────────────────
# 3. ADMIN TUNE OVERRIDE THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/admin/config/override-threshold",
    status_code=status.HTTP_200_OK,
)
async def update_override_threshold(
    payload: UpdateOverrideThresholdRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint to tune acuity_override_threshold and override_frequency_flag_limit.
    """
    now_utc = datetime.now(timezone.utc)
    changes = {}

    if payload.acuity_override_threshold is not None:
        stmt = select(AdminConfig).where(AdminConfig.key == "acuity_override_threshold")
        cfg = (await db.execute(stmt)).scalar_one_or_none()
        if not cfg:
            cfg = AdminConfig(key="acuity_override_threshold", value=Decimal(str(payload.acuity_override_threshold)), updated_by=current_user.user_id)
            db.add(cfg)
        else:
            cfg.value = Decimal(str(payload.acuity_override_threshold))
            cfg.updated_by = current_user.user_id
            cfg.updated_at = now_utc
        changes["acuity_override_threshold"] = payload.acuity_override_threshold

    if payload.override_frequency_flag_limit is not None:
        stmt = select(AdminConfig).where(AdminConfig.key == "override_frequency_flag_limit")
        cfg = (await db.execute(stmt)).scalar_one_or_none()
        if not cfg:
            cfg = AdminConfig(key="override_frequency_flag_limit", value=Decimal(str(payload.override_frequency_flag_limit)), updated_by=current_user.user_id)
            db.add(cfg)
        else:
            cfg.value = Decimal(str(payload.override_frequency_flag_limit))
            cfg.updated_by = current_user.user_id
            cfg.updated_at = now_utc
        changes["override_frequency_flag_limit"] = payload.override_frequency_flag_limit

    if changes:
        await create_audit_event(
            db=db,
            event_type="OVERRIDE_CONFIG_UPDATED",
            detail={"updated_by": current_user.user_id, "changes": changes},
        )
        await db.commit()

    return {"message": "Override threshold configuration updated successfully", "changes": changes}
