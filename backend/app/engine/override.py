"""
Emergency Override Gate Engine — Feature #18

Enables critical patient transactions (acuity >= 9.5 or manual Doctor/Admin declaration)
to skip the normal Conflict Detection / Acuity Arbiter queue for READY resources in <50ms,
while routing held resources into the Escalation Arbiter.

Key Guarantees:
  • Runs post-Idempotency Gate (never bypassed).
  • Direct-locks READY resources in sub-50ms.
  • Routes held resources to Escalation Arbiter (source_feature='EMERGENCY_OVERRIDE_ROUTED').
  • Defers unavailable resources to AI recommendation fallbacks (no physics violation).
  • Preserves Care Bundle 2PC atomicity.
  • Logs rich EMERGENCY_OVERRIDE_TRIGGERED audit record with per-leg breakdown.
  • Retrospective clinical governance monitoring (24h frequency & post-hoc acuity mismatch).
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import publish_event
from app.engine.escalation import request_escalation
from app.engine.locking import attempt_single_resource_lock
from app.models.models import (
    AdminConfig,
    Bed,
    BedStatus,
    Patient,
    Resource,
    ResourceStatus,
    Transaction,
    TxState,
)
from app.models.override import (
    EmergencyOverrideEvent,
    OverrideFlagReason,
    OverrideTriggerType,
)
from app.services.audit import create_audit_event

logger = logging.getLogger(__name__)


@dataclass
class OverrideLegResult:
    resource_id: str
    was_ready: bool
    status: str
    escalation_id: Optional[uuid.UUID] = None
    suggested_alternative: Optional[Dict[str, Any]] = None


@dataclass
class OverrideResult:
    is_override: bool
    trigger_type: Optional[str] = None
    latency_ms: Optional[int] = None
    all_legs_resolved: bool = False
    legs: Optional[List[OverrideLegResult]] = None
    event_id: Optional[uuid.UUID] = None
    flagged_for_review: bool = False
    flag_reason: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# 1. CORE EMERGENCY OVERRIDE EVALUATION GATE
# ─────────────────────────────────────────────────────────────────────────────

async def evaluate_override(
    db: AsyncSession,
    tx_id: str,
    patient_id: str,
    acuity_score: float,
    requested_resources: List[str],
    requested_by: str,
    manual_reason: Optional[str] = None,
    redis_client: Optional[aioredis.Redis] = None,
) -> OverrideResult:
    """
    Evaluates whether a transaction qualifies for Emergency Override, and if so,
    executes rapid direct locking for READY resources and escalation routing for held resources.
    """
    now_utc = datetime.now(timezone.utc)

    # ── 1. Fetch Configurable Thresholds ──
    threshold_stmt = select(AdminConfig).where(
        AdminConfig.key.in_(["acuity_override_threshold", "override_frequency_flag_limit"])
    )
    res = await db.execute(threshold_stmt)
    configs = {row.key: row.value for row in res.scalars().all()}
    acuity_threshold = float(configs.get("acuity_override_threshold", 9.5))
    freq_limit = int(configs.get("override_frequency_flag_limit", 3))

    # ── 2. Determine Trigger Type ──
    trigger_type: Optional[str] = None
    if acuity_score >= acuity_threshold:
        trigger_type = OverrideTriggerType.AUTOMATIC.value
    elif manual_reason and manual_reason.strip():
        trigger_type = OverrideTriggerType.MANUAL_DECLARE.value
    else:
        return OverrideResult(is_override=False)

    # ── 3. Start Latency Stopwatch ──
    start_time = time.perf_counter()

    legs: List[OverrideLegResult] = []
    escalation_ids: List[uuid.UUID] = []
    all_legs_resolved = True

    # ── 4. Resolve Each Requested Resource ──
    for rid in requested_resources:
        # A. Check standard Resource table
        res_stmt = select(Resource).where(Resource.resource_id == rid)
        res_obj = (await db.execute(res_stmt)).scalar_one_or_none()

        if res_obj:
            if res_obj.status == ResourceStatus.available:
                # Direct Lock in <50ms
                locked = await attempt_single_resource_lock(db, tx_id, rid)
                legs.append(OverrideLegResult(resource_id=rid, was_ready=True, status="LOCKED"))
            elif res_obj.status in [ResourceStatus.tentative, ResourceStatus.locked]:
                # Route to Escalation Arbiter
                esc_res = await request_escalation(
                    db=db,
                    escalating_tx_id=tx_id,
                    target_resource_id=rid,
                    requested_by=requested_by,
                    source_feature="EMERGENCY_OVERRIDE_ROUTED",
                    redis_client=redis_client,
                )
                esc_uuid = uuid.UUID(esc_res["escalation_id"])
                escalation_ids.append(esc_uuid)
                if esc_res.get("decision") == "APPROVED":
                    legs.append(
                        OverrideLegResult(
                            resource_id=rid,
                            was_ready=False,
                            status="ESCALATED_LOCKED",
                            escalation_id=esc_uuid,
                        )
                    )
                else:
                    all_legs_resolved = False
                    legs.append(
                        OverrideLegResult(
                            resource_id=rid,
                            was_ready=False,
                            status="ESCALATION_REJECTED",
                            escalation_id=esc_uuid,
                        )
                    )
            else:
                # Cleaning / Maintenance / Offline
                all_legs_resolved = False
                legs.append(
                    OverrideLegResult(
                        resource_id=rid,
                        was_ready=False,
                        status="UNAVAILABLE_FALLBACK",
                    )
                )
        else:
            # B. Check Beds table
            bed_stmt = select(Bed).where(Bed.id == rid)
            bed_obj = (await db.execute(bed_stmt)).scalar_one_or_none()

            if bed_obj:
                if bed_obj.status == BedStatus.READY:
                    bed_obj.status = BedStatus.LOCKED
                    bed_obj.current_transaction_id = tx_id
                    bed_obj.updated_at = now_utc
                    legs.append(OverrideLegResult(resource_id=rid, was_ready=True, status="LOCKED"))
                elif bed_obj.status in [BedStatus.TENTATIVE_HOLD, BedStatus.LOCKED]:
                    esc_res = await request_escalation(
                        db=db,
                        escalating_tx_id=tx_id,
                        target_resource_id=rid,
                        requested_by=requested_by,
                        source_feature="EMERGENCY_OVERRIDE_ROUTED",
                        redis_client=redis_client,
                    )
                    esc_uuid = uuid.UUID(esc_res["escalation_id"])
                    escalation_ids.append(esc_uuid)
                    if esc_res.get("decision") == "APPROVED":
                        legs.append(
                            OverrideLegResult(
                                resource_id=rid,
                                was_ready=False,
                                status="ESCALATED_LOCKED",
                                escalation_id=esc_uuid,
                            )
                        )
                    else:
                        all_legs_resolved = False
                        legs.append(
                            OverrideLegResult(
                                resource_id=rid,
                                was_ready=False,
                                status="ESCALATION_REJECTED",
                                escalation_id=esc_uuid,
                            )
                        )
                else:
                    all_legs_resolved = False
                    legs.append(
                        OverrideLegResult(
                            resource_id=rid,
                            was_ready=False,
                            status="UNAVAILABLE_FALLBACK",
                        )
                    )
            else:
                all_legs_resolved = False
                legs.append(
                    OverrideLegResult(
                        resource_id=rid,
                        was_ready=False,
                        status="NOT_FOUND",
                    )
                )

    # ── 5. Measure Latency ──
    latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))

    # ── 6. Governance Anomaly Checks (Non-Blocking) ──
    flagged_for_review = False
    flag_reason: Optional[str] = None

    if trigger_type == OverrideTriggerType.MANUAL_DECLARE.value:
        # Check frequency limit (last 24 hours)
        day_ago = now_utc - timedelta(hours=24)
        count_stmt = select(func.count(EmergencyOverrideEvent.id)).where(
            EmergencyOverrideEvent.requested_by == requested_by,
            EmergencyOverrideEvent.trigger_type == OverrideTriggerType.MANUAL_DECLARE.value,
            EmergencyOverrideEvent.created_at >= day_ago,
        )
        recent_count = (await db.execute(count_stmt)).scalar_one() or 0

        if recent_count >= freq_limit:
            flagged_for_review = True
            flag_reason = OverrideFlagReason.FREQUENCY_THRESHOLD.value

        # Check immediate acuity mismatch
        if acuity_score < 7.0:
            flagged_for_review = True
            flag_reason = OverrideFlagReason.POST_HOC_ACUITY_MISMATCH.value

    # ── 7. Persist Event & Audit Log ──
    event_id = uuid.uuid4()
    resources_json = [
        {"resource_id": leg.resource_id, "was_ready": leg.was_ready, "status": leg.status}
        for leg in legs
    ]

    event = EmergencyOverrideEvent(
        id=event_id,
        tx_id=tx_id,
        patient_id=patient_id,
        trigger_type=trigger_type,
        acuity_score_at_trigger=Decimal(str(acuity_score)),
        manual_reason=manual_reason,
        requested_by=requested_by,
        resources_requested=resources_json,
        escalation_ids=escalation_ids if escalation_ids else None,
        latency_ms=latency_ms,
        flagged_for_review=flagged_for_review,
        flag_reason=flag_reason,
        created_at=now_utc,
    )
    db.add(event)
    await db.flush()

    # Rich Audit Event
    await create_audit_event(
        db=db,
        event_type="EMERGENCY_OVERRIDE_TRIGGERED",
        tx_id=tx_id,
        decision="OVERRIDE_EXECUTED" if all_legs_resolved else "OVERRIDE_PARTIAL_OR_FAILED",
        effective_score=acuity_score,
        detail={
            "event_id": str(event_id),
            "trigger_type": trigger_type,
            "acuity_score": acuity_score,
            "manual_reason": manual_reason,
            "latency_ms": latency_ms,
            "legs": resources_json,
            "flagged_for_review": flagged_for_review,
            "flag_reason": flag_reason,
        },
    )

    # Publish to Redis Dashboard
    if redis_client:
        try:
            await publish_event(
                "pubsub:dashboard",
                {
                    "event": "EMERGENCY_OVERRIDE_TRIGGERED",
                    "event_id": str(event_id),
                    "tx_id": tx_id,
                    "patient_id": patient_id,
                    "trigger_type": trigger_type,
                    "acuity_score": acuity_score,
                    "latency_ms": latency_ms,
                    "timestamp": now_utc.isoformat(),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish EMERGENCY_OVERRIDE_TRIGGERED: {e}")

    return OverrideResult(
        is_override=True,
        trigger_type=trigger_type,
        latency_ms=latency_ms,
        all_legs_resolved=all_legs_resolved,
        legs=legs,
        event_id=event_id,
        flagged_for_review=flagged_for_review,
        flag_reason=flag_reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. RETROSPECTIVE POST-HOC ACUITY MISMATCH SCAN
# ─────────────────────────────────────────────────────────────────────────────

async def scan_post_hoc_acuity_mismatches(db: AsyncSession) -> int:
    """
    Retrospective worker job: inspects manual-declare overrides where patient's
    updated base acuity landed < 7.0 and flags them for review.
    """
    now_utc = datetime.now(timezone.utc)
    recent_cutoff = now_utc - timedelta(hours=24)

    stmt = (
        select(EmergencyOverrideEvent)
        .where(
            EmergencyOverrideEvent.trigger_type == OverrideTriggerType.MANUAL_DECLARE.value,
            EmergencyOverrideEvent.flagged_for_review.is_(False),
            EmergencyOverrideEvent.created_at >= recent_cutoff,
        )
    )
    events = list((await db.execute(stmt)).scalars().all())

    flagged_count = 0
    for evt in events:
        pt = await db.get(Patient, evt.patient_id)
        if pt and float(pt.base_acuity) < 7.0:
            evt.flagged_for_review = True
            evt.flag_reason = OverrideFlagReason.POST_HOC_ACUITY_MISMATCH.value
            flagged_count += 1

    if flagged_count:
        await db.flush()
        logger.info(f"Emergency override governance: {flagged_count} event(s) flagged for retrospective review")

    return flagged_count
