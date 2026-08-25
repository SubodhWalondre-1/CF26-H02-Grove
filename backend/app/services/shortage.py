"""
Shortage Detection Engine — Feature #22: Live Resource & Donation Board

Responsibilities:
  • Monitors consumable resources (Blood Units, Oxygen, Medications).
  • Evaluates available stock against configurable shortage_thresholds.
  • Creates/updates idempotent ACTIVE alerts when inventory drops below threshold.
  • Automatically resolves active alerts when inventory is restocked.
  • Broadcasts real-time alert/clearance events to the unauthenticated public_alerts channel.
  • STRICT ZERO-PHI GUARANTEE: Never exposes patient, clinician, or procedural data.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import publish_event
from app.models.pharmacy import PharmacyResource, PharmacyResourceStatus
from app.models.shortage import Alert, ShortageThreshold

logger = logging.getLogger(__name__)

CONSUMABLE_TYPES = {
    "BLOOD_UNIT",
    "OXYGEN_UNIT",
    "MEDICATION_SLOT",
    "blood_unit",
    "oxygen_unit",
    "medication_slot",
}

# Public Helpline Configuration
PUBLIC_HELPLINE_PHONE = "+1 (800) 555-CARE (2273)"
PUBLIC_HELPLINE_URL = "https://mediora.hospital/donate"


async def check_shortage(
    resource_type: str,
    subtype: str,
    db: AsyncSession,
    redis_client: Optional[aioredis.Redis] = None,
) -> Optional[Alert]:
    """
    Evaluates a specific consumable inventory item against its threshold.
    Creates or updates an active alert on shortage, or auto-resolves if restocked.
    """
    r_type_upper = resource_type.upper()
    sub_upper = subtype.upper()

    if r_type_upper not in CONSUMABLE_TYPES:
        return None

    now_utc = datetime.now(timezone.utc)

    # 1. Fetch threshold configuration
    thresh_stmt = select(ShortageThreshold).where(
        ShortageThreshold.resource_type == r_type_upper,
        func.upper(ShortageThreshold.subtype) == sub_upper,
    )
    threshold = (await db.execute(thresh_stmt)).scalar_one_or_none()

    if not threshold:
        return None

    # 2. Calculate current available stock
    qty_stmt = (
        select(func.coalesce(func.sum(PharmacyResource.available_quantity), 0))
        .where(
            func.upper(PharmacyResource.resource_type) == r_type_upper,
            func.upper(PharmacyResource.sub_type) == sub_upper,
            PharmacyResource.status.in_([
                PharmacyResourceStatus.STOCKED,
                PharmacyResourceStatus.LOW_STOCK,
            ]),
        )
    )
    available_qty = int((await db.execute(qty_stmt)).scalar() or 0)

    # 3. Check for existing active alert (row-level lock for idempotency)
    alert_stmt = (
        select(Alert)
        .where(
            Alert.resource_type == r_type_upper,
            Alert.subtype == sub_upper,
            Alert.status == "ACTIVE",
        )
        .with_for_update()
    )
    active_alert = (await db.execute(alert_stmt)).scalar_one_or_none()

    # Case A: Stock is BELOW critical threshold -> Raise / Update Alert
    if available_qty < threshold.critical_threshold:
        units_needed = threshold.critical_threshold - available_qty

        if active_alert:
            active_alert.units_needed = units_needed
            alert_obj = active_alert
        else:
            alert_id = f"ALT-{uuid.uuid4().hex[:6].upper()}"
            alert_obj = Alert(
                alert_id=alert_id,
                resource_type=r_type_upper,
                subtype=sub_upper,
                units_needed=units_needed,
                status="ACTIVE",
                created_at=now_utc,
                created_by="SYSTEM",
            )
            db.add(alert_obj)

        await db.flush()

        # Broadcast to public_alerts WebSocket channel (unauthenticated)
        payload = {
            "event": "SHORTAGE_ALERT_RAISED",
            "alert_id": alert_obj.alert_id,
            "resource_type": r_type_upper,
            "subtype": sub_upper,
            "units_needed": units_needed,
            "unit_label": threshold.unit_label,
            "helpline": PUBLIC_HELPLINE_PHONE,
            "timestamp": now_utc.isoformat(),
        }
        await publish_event("pubsub:public_alerts", payload)
        await publish_event("pubsub:dashboard", payload)
        return alert_obj

    # Case B: Stock is RESTOCKED >= critical threshold -> Auto-resolve Alert
    elif active_alert:
        active_alert.status = "RESOLVED"
        active_alert.resolved_at = now_utc
        active_alert.resolved_by = "SYSTEM"
        await db.flush()

        payload = {
            "event": "SHORTAGE_ALERT_RESOLVED",
            "alert_id": active_alert.alert_id,
            "resource_type": r_type_upper,
            "subtype": sub_upper,
            "timestamp": now_utc.isoformat(),
        }
        await publish_event("pubsub:public_alerts", payload)
        await publish_event("pubsub:dashboard", payload)
        return active_alert

    return None


async def check_all_shortage_thresholds(
    db: AsyncSession,
    redis_client: Optional[aioredis.Redis] = None,
) -> int:
    """
    Scheduled sweep running every 60s via APScheduler across all configured thresholds.
    """
    stmt = select(ShortageThreshold)
    thresholds = list((await db.execute(stmt)).scalars().all())

    checked_count = 0
    for th in thresholds:
        await check_shortage(
            resource_type=th.resource_type,
            subtype=th.subtype,
            db=db,
            redis_client=redis_client,
        )
        checked_count += 1

    await db.commit()
    return checked_count


async def get_active_alerts(db: AsyncSession) -> List[Dict[str, Any]]:
    """
    Returns list of all active shortages formatted for the Public Donation Board.
    Guaranteed zero PHI.
    """
    stmt = (
        select(Alert, ShortageThreshold.unit_label)
        .join(
            ShortageThreshold,
            (Alert.resource_type == ShortageThreshold.resource_type)
            & (Alert.subtype == ShortageThreshold.subtype),
            isouter=True,
        )
        .where(Alert.status == "ACTIVE")
        .order_by(Alert.created_at.desc())
    )
    rows = list((await db.execute(stmt)).all())

    results = []
    for alert, unit_label in rows:
        results.append({
            "alert_id": alert.alert_id,
            "resource_type": alert.resource_type,
            "subtype": alert.subtype,
            "units_needed": alert.units_needed,
            "unit_label": unit_label or "units",
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "helpline_phone": PUBLIC_HELPLINE_PHONE,
            "helpline_url": PUBLIC_HELPLINE_URL,
        })
    return results


async def resolve_alert_manually(
    alert_id: str,
    resolved_by: str,
    db: AsyncSession,
    redis_client: Optional[aioredis.Redis] = None,
) -> Alert:
    """
    Admin-only action to manually dismiss/override an active shortage alert.
    """
    now_utc = datetime.now(timezone.utc)
    stmt = select(Alert).where(Alert.alert_id == alert_id).with_for_update()
    alert = (await db.execute(stmt)).scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found.",
        )

    if alert.status != "ACTIVE":
        return alert

    alert.status = "RESOLVED"
    alert.resolved_at = now_utc
    alert.resolved_by = f"ADMIN:{resolved_by}"
    await db.flush()

    payload = {
        "event": "SHORTAGE_ALERT_RESOLVED",
        "alert_id": alert.alert_id,
        "resource_type": alert.resource_type,
        "subtype": alert.subtype,
        "resolved_by": alert.resolved_by,
        "timestamp": now_utc.isoformat(),
    }
    await publish_event("pubsub:public_alerts", payload)
    await publish_event("pubsub:dashboard", payload)
    await db.commit()
    return alert
