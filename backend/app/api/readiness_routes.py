"""
API routes for Feature #19: Resource Readiness Engine
"""

from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_active_user,
    get_db,
    require_admin,
)
from app.core.redis import get_redis
from app.models.models import User
from app.schemas.schemas import (
    BulkReadyResourcesResponse,
    ForceStatusRequest,
    ReadinessResponse,
    ReportFaultRequest,
    VerifyReadyRequest,
)
from app.services.audit import create_audit_event
from app.services.readiness import (
    check_readiness,
    get_bulk_ready_resources,
    subscribe_notify_when_ready,
    transition_resource_state,
    verify_ready,
)

router = APIRouter(tags=["Resource Readiness Engine"])


# ─────────────────────────────────────────────────────────────────────────────
# 1. READINESS STATUS CHECKS
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/resources/{resource_id}/readiness",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
)
async def get_resource_readiness(
    resource_id: str,
    resource_type: Optional[str] = Query(None),
    quantity: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    """
    Evaluates whether a specific resource or bed is currently READY for clinical allocation.
    """
    res = await check_readiness(
        db=db,
        resource_id=resource_id,
        resource_type=resource_type,
        requested_quantity=quantity,
    )
    return ReadinessResponse(
        resource_id=resource_id,
        is_ready=res.is_ready,
        status=res.status,
        reason=res.reason,
        estimated_ready_at=res.estimated_ready_at.isoformat() if res.estimated_ready_at else None,
        details=res.details,
    )


@router.get(
    "/internal/resources/ready",
    response_model=BulkReadyResourcesResponse,
    status_code=status.HTTP_200_OK,
)
async def list_bulk_ready_resources(
    types: Optional[List[str]] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    """
    Bulk query returning all READY discrete resources and beds for the AI Recommendation Engine.
    """
    ready_items = await get_bulk_ready_resources(db=db, resource_types=types)
    return BulkReadyResourcesResponse(resources=ready_items, total=len(ready_items))


# ─────────────────────────────────────────────────────────────────────────────
# 2. HOUSEKEEPING & TURNAROUND TRANSITIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/resources/{resource_id}/transitions/cleaning-complete",
    status_code=status.HTTP_200_OK,
)
async def mark_cleaning_complete(
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Housekeeping: Advances resource from CLEANING to SANITIZED.
    """
    user_id = getattr(current_user, "username", None) or current_user.user_id
    res = await transition_resource_state(
        db=db,
        resource_id=resource_id,
        from_status="CLEANING",
        to_status="SANITIZED",
        triggered_by=user_id,
    )
    await db.commit()
    return {"message": f"Resource {resource_id} marked SANITIZED (pending verification sign-off).", "details": res}


@router.post(
    "/resources/{resource_id}/transitions/verify-ready",
    status_code=status.HTTP_200_OK,
)
async def verify_and_sign_off_ready(
    resource_id: str,
    payload: Optional[VerifyReadyRequest] = None,
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[aioredis.Redis] = Depends(get_redis),
    current_user: User = Depends(get_current_active_user),
):
    """
    Nurse / Housekeeping Lead: Verifies sanitation and transitions SANITIZED to READY.
    Enforces mandatory human staff attribution in verified_by.
    """
    user_id = getattr(current_user, "username", None) or current_user.user_id
    res = await verify_ready(
        db=db,
        resource_id=resource_id,
        verified_by=user_id,
        expected_version=payload.expected_version if payload else None,
        redis_client=redis_client,
    )
    await db.commit()
    return {"message": f"Resource {resource_id} verified and marked READY.", "details": res}


@router.post(
    "/resources/{resource_id}/transitions/report-fault",
    status_code=status.HTTP_200_OK,
)
async def report_resource_fault(
    resource_id: str,
    payload: ReportFaultRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Any clinical staff: Transitions resource from its current state to MAINTENANCE.
    """
    user_id = getattr(current_user, "username", None) or current_user.user_id
    res = await transition_resource_state(
        db=db,
        resource_id=resource_id,
        from_status="READY",  # or current
        to_status="MAINTENANCE",
        triggered_by=user_id,
        maintenance_reason=payload.reason,
    )
    await db.commit()
    return {"message": f"Resource {resource_id} placed in MAINTENANCE.", "details": res}


@router.post(
    "/resources/{resource_id}/transitions/repaired",
    status_code=status.HTTP_200_OK,
)
async def mark_resource_repaired(
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Technician / Maintenance staff: Transitions resource from MAINTENANCE to CLEANING.
    """
    user_id = getattr(current_user, "username", None) or current_user.user_id
    res = await transition_resource_state(
        db=db,
        resource_id=resource_id,
        from_status="MAINTENANCE",
        to_status="CLEANING",
        triggered_by=user_id,
    )
    await db.commit()
    return {"message": f"Resource {resource_id} repair completed. Cleaning initiated.", "details": res}


# ─────────────────────────────────────────────────────────────────────────────
# 3. NOTIFY-WHEN-READY SUBSCRIPTIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/resources/{resource_id}/notify-when-ready",
    status_code=status.HTTP_200_OK,
)
async def subscribe_ready_notification(
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Subscribes current user for a real-time push alert when resource becomes READY.
    """
    user_id = getattr(current_user, "username", None) or current_user.user_id
    res = await subscribe_notify_when_ready(db=db, resource_id=resource_id, subscribed_by=user_id)
    await db.commit()
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 4. ADMIN FORCE-STATUS OVERRIDE (HEAVILY AUDITED)
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/admin/resources/{resource_id}/force-status",
    status_code=status.HTTP_200_OK,
)
async def force_resource_status(
    resource_id: str,
    payload: ForceStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin-only emergency manual override of the state machine. Heavily audited.
    """
    user_id = getattr(current_user, "username", None) or current_user.user_id
    res = await transition_resource_state(
        db=db,
        resource_id=resource_id,
        from_status="FREE",  # bypass validation for admin force
        to_status=payload.status,
        triggered_by=f"ADMIN_FORCE:{user_id}",
    )

    await create_audit_event(
        db=db,
        event_type="ADMIN_FORCE_RESOURCE_STATUS",
        detail={
            "resource_id": resource_id,
            "target_status": payload.status,
            "reason": payload.reason,
            "admin_user": user_id,
        },
    )
    await db.commit()
    return {"message": f"Resource {resource_id} forcibly set to {payload.status}.", "details": res}
