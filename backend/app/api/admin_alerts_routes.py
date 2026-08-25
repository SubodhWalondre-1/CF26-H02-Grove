"""
Admin Alerts & Thresholds Management Routes — Feature #22: Live Resource & Donation Board
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.redis import get_redis
from app.models.models import User
from app.models.shortage import ShortageThreshold
from app.services.shortage import check_shortage, resolve_alert_manually

router = APIRouter(prefix="/admin", tags=["Admin Shortage & Alert Governance"])


class ThresholdUpdateRequest(BaseModel):
    resource_type: str = Field(..., description="Consumable type (e.g. BLOOD_UNIT, OXYGEN_UNIT, MEDICATION_SLOT)")
    subtype: str = Field(..., description="Subtype/Item code (e.g. O-, O2_CYLINDER_D, ADRENALINE_1MG)")
    critical_threshold: int = Field(..., ge=0, description="Minimum available count before raising shortage alert")
    unit_label: str = Field("units", description="Display unit label (e.g. units, vials, cylinders)")


@router.post("/alerts/{alert_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Manually dismisses an active shortage alert (Admin RBAC only).
    """
    redis_client = await get_redis()
    alert = await resolve_alert_manually(
        alert_id=alert_id,
        resolved_by=current_user.username,
        db=db,
        redis_client=redis_client,
    )
    return {
        "alert_id": alert.alert_id,
        "status": alert.status,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "resolved_by": alert.resolved_by,
    }


@router.get("/shortage-thresholds", status_code=status.HTTP_200_OK)
async def list_shortage_thresholds(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Lists all configured consumable shortage thresholds.
    """
    stmt = select(ShortageThreshold).order_by(ShortageThreshold.resource_type, ShortageThreshold.subtype)
    thresholds = list((await db.execute(stmt)).scalars().all())
    return [
        {
            "id": str(t.id),
            "resource_type": t.resource_type,
            "subtype": t.subtype,
            "critical_threshold": t.critical_threshold,
            "unit_label": t.unit_label,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in thresholds
    ]


@router.put("/shortage-thresholds", status_code=status.HTTP_200_OK)
async def update_shortage_threshold(
    payload: ThresholdUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Creates or updates a consumable shortage threshold configuration and re-evaluates inventory.
    """
    r_type_upper = payload.resource_type.upper()
    sub_upper = payload.subtype.upper()

    stmt = select(ShortageThreshold).where(
        ShortageThreshold.resource_type == r_type_upper,
        ShortageThreshold.subtype == sub_upper,
    )
    threshold = (await db.execute(stmt)).scalar_one_or_none()

    if threshold:
        threshold.critical_threshold = payload.critical_threshold
        threshold.unit_label = payload.unit_label
    else:
        threshold = ShortageThreshold(
            resource_type=r_type_upper,
            subtype=sub_upper,
            critical_threshold=payload.critical_threshold,
            unit_label=payload.unit_label,
        )
        db.add(threshold)

    await db.commit()

    # Re-evaluate shortage immediately
    redis_client = await get_redis()
    await check_shortage(
        resource_type=r_type_upper,
        subtype=sub_upper,
        db=db,
        redis_client=redis_client,
    )
    await db.commit()

    return {
        "resource_type": threshold.resource_type,
        "subtype": threshold.subtype,
        "critical_threshold": threshold.critical_threshold,
        "unit_label": threshold.unit_label,
    }
