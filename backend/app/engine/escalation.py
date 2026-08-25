"""
Escalation Arbiter Engine — Feature #16

Enables higher-acuity transactions to preempt resources currently held
(LOCKED or TENTATIVE_HOLD) by lower-acuity transactions.

Safety Rules:
  1. IN_USE resources are strictly NON-PREEMPTABLE under any condition.
  2. Escalating acuity must be strictly GREATER than holder acuity (ties favor current holder).
  3. Preempted holder TX is force-rolled-back through existing Cascade Dependency Compensation.
  4. Preempted user receives a real-time notification with a suggested alternative resource.
  5. Audit log records ESCALATION_RESOLVED with both TX IDs and acuity scores.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import publish_event
from app.engine.compensation import initiate_compensation
from app.engine.locking import release_single_resource
from app.models.diagnostics import DiagnosticAppointment, DiagnosticEquipment, EquipmentStatus
from app.models.escalation import (
    EscalationDecision,
    EscalationRequest,
    EscalationSourceFeature,
)
from app.models.models import (
    Bed,
    BedStatus,
    HoldState,
    Patient,
    RequestType,
    Resource,
    ResourceStatus,
    Transaction,
    TransactionResource,
    TransactionStateHistory,
    TxState,
)
from app.services.audit import create_audit_event
from app.services.patient import get_patient_acuity

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CORE ESCALATION ARBITER
# ─────────────────────────────────────────────────────────────────────────────

async def request_escalation(
    db: AsyncSession,
    escalating_tx_id: str,
    target_resource_id: str,
    requested_by: str,
    source_feature: str = "DIRECT",
    redis_client: Optional[aioredis.Redis] = None,
) -> Dict[str, Any]:
    """
    Evaluates and executes an escalation preemption against target_resource_id.
    
    Returns a dict containing:
      escalation_id, escalating_tx_id, target_resource_id, holder_tx_id,
      escalating_acuity, holder_acuity, decision (APPROVED/REJECTED),
      rejection_reason, suggested_alternative (if approved).
    """
    now_utc = datetime.now(timezone.utc)
    escalation_id = uuid.uuid4()

    # ── 1. Load Target Resource and Status ──
    holder_tx_id: Optional[str] = None
    resource_type_str: Optional[str] = None
    is_in_use = False
    is_free = False

    # A. Check standard Resource table
    res_stmt = select(Resource).where(Resource.resource_id == target_resource_id)
    res_result = await db.execute(res_stmt)
    res_obj = res_result.scalar_one_or_none()

    if res_obj:
        resource_type_str = res_obj.type.value if hasattr(res_obj.type, "value") else str(res_obj.type)
        if res_obj.status == ResourceStatus.available:
            is_free = True
        elif res_obj.status == ResourceStatus.locked and not res_obj.held_by_tx:
            # Physically in-use without active hold TX
            is_in_use = True
        else:
            holder_tx_id = res_obj.held_by_tx
    else:
        # B. Check Beds table
        bed_stmt = select(Bed).where(Bed.id == target_resource_id)
        bed_result = await db.execute(bed_stmt)
        bed_obj = bed_result.scalar_one_or_none()

        if bed_obj:
            resource_type_str = "bed"
            if bed_obj.status in [BedStatus.FREE, BedStatus.READY]:
                is_free = True
            elif bed_obj.status == BedStatus.IN_USE:
                is_in_use = True
            elif bed_obj.status in [BedStatus.TENTATIVE_HOLD, BedStatus.LOCKED]:
                holder_tx_id = bed_obj.current_transaction_id
                if not holder_tx_id:
                    # Look up active TransactionResource for bed
                    tr_stmt = (
                        select(TransactionResource)
                        .where(
                            TransactionResource.resource_id == target_resource_id,
                            TransactionResource.hold_state.in_([HoldState.held, HoldState.tentative]),
                        )
                        .order_by(TransactionResource.updated_at.desc())
                    )
                    tr_res = await db.execute(tr_stmt)
                    tr = tr_res.scalar_one_or_none()
                    if tr:
                        holder_tx_id = tr.tx_id
        else:
            # C. Check Diagnostic Equipment
            diag_stmt = select(DiagnosticEquipment).where(DiagnosticEquipment.id == target_resource_id)
            diag_result = await db.execute(diag_stmt)
            diag_obj = diag_result.scalar_one_or_none()

            if diag_obj:
                resource_type_str = diag_obj.type.value if hasattr(diag_obj.type, "value") else str(diag_obj.type)
                if diag_obj.status == EquipmentStatus.AVAILABLE:
                    is_free = True
                elif diag_obj.status == EquipmentStatus.IN_USE:
                    is_in_use = True
                else:
                    # Find active appointment
                    app_stmt = (
                        select(DiagnosticAppointment)
                        .where(
                            DiagnosticAppointment.equipment_id == target_resource_id,
                            DiagnosticAppointment.status.in_(["CONFIRMED", "IN_PROGRESS"]),
                        )
                        .order_by(DiagnosticAppointment.scheduled_start_time.asc())
                    )
                    app_res = await db.execute(app_stmt)
                    app_obj = app_res.scalar_one_or_none()
                    if app_obj:
                        if app_obj.status == "IN_PROGRESS":
                            is_in_use = True
                        else:
                            holder_tx_id = app_obj.tx_id

    # ── 2. Hard Safety Check: IN_USE Is Never Preemptable ──
    if is_in_use:
        req = EscalationRequest(
            id=escalation_id,
            escalating_tx_id=escalating_tx_id,
            escalating_acuity=Decimal("0.0"),
            target_resource_id=target_resource_id,
            holder_tx_id=holder_tx_id,
            holder_acuity=None,
            decision=EscalationDecision.REJECTED.value,
            rejection_reason="RESOURCE_IN_USE",
            requested_by=requested_by,
            requested_at=now_utc,
            resolved_at=now_utc,
            source_feature=source_feature,
        )
        db.add(req)
        await db.flush()

        await create_audit_event(
            db=db,
            event_type="ESCALATION_RESOLVED",
            tx_id=escalating_tx_id,
            decision="REJECTED",
            detail={
                "escalation_id": str(escalation_id),
                "rejection_reason": "RESOURCE_IN_USE",
                "target_resource_id": target_resource_id,
                "source_feature": source_feature,
            },
        )
        return {
            "escalation_id": str(escalation_id),
            "escalating_tx_id": escalating_tx_id,
            "target_resource_id": target_resource_id,
            "decision": EscalationDecision.REJECTED.value,
            "rejection_reason": "RESOURCE_IN_USE",
        }

    # ── 3. Check if Resource Is Already Free ──
    if is_free or not holder_tx_id:
        req = EscalationRequest(
            id=escalation_id,
            escalating_tx_id=escalating_tx_id,
            escalating_acuity=Decimal("0.0"),
            target_resource_id=target_resource_id,
            holder_tx_id=None,
            holder_acuity=None,
            decision=EscalationDecision.REJECTED.value,
            rejection_reason="RESOURCE_ALREADY_FREE",
            requested_by=requested_by,
            requested_at=now_utc,
            resolved_at=now_utc,
            source_feature=source_feature,
        )
        db.add(req)
        await db.flush()

        return {
            "escalation_id": str(escalation_id),
            "escalating_tx_id": escalating_tx_id,
            "target_resource_id": target_resource_id,
            "decision": EscalationDecision.REJECTED.value,
            "rejection_reason": "RESOURCE_ALREADY_FREE",
        }

    # ── 4. Load Both Acuity Scores ──
    escalating_tx = await db.get(Transaction, escalating_tx_id)
    holder_tx = await db.get(Transaction, holder_tx_id)

    if not escalating_tx:
        raise ValueError(f"Escalating transaction {escalating_tx_id} not found")

    escalating_patient = await get_patient_acuity(db, escalating_tx.patient_id)
    escalating_acuity = float(escalating_patient.base_acuity)

    holder_acuity = 0.0
    if holder_tx:
        holder_patient = await get_patient_acuity(db, holder_tx.patient_id)
        holder_acuity = float(holder_patient.base_acuity)

    # ── 5. Acuity Comparison (Strictly Greater Required) ──
    if escalating_acuity <= holder_acuity:
        req = EscalationRequest(
            id=escalation_id,
            escalating_tx_id=escalating_tx_id,
            escalating_acuity=Decimal(str(escalating_acuity)),
            target_resource_id=target_resource_id,
            holder_tx_id=holder_tx_id,
            holder_acuity=Decimal(str(holder_acuity)),
            decision=EscalationDecision.REJECTED.value,
            rejection_reason="HOLDER_HIGHER_ACUITY",
            requested_by=requested_by,
            requested_at=now_utc,
            resolved_at=now_utc,
            source_feature=source_feature,
        )
        db.add(req)
        await db.flush()

        await create_audit_event(
            db=db,
            event_type="ESCALATION_RESOLVED",
            tx_id=escalating_tx_id,
            decision="REJECTED",
            detail={
                "escalation_id": str(escalation_id),
                "rejection_reason": "HOLDER_HIGHER_ACUITY",
                "escalating_acuity": escalating_acuity,
                "holder_tx_id": holder_tx_id,
                "holder_acuity": holder_acuity,
                "source_feature": source_feature,
            },
        )

        return {
            "escalation_id": str(escalation_id),
            "escalating_tx_id": escalating_tx_id,
            "target_resource_id": target_resource_id,
            "holder_tx_id": holder_tx_id,
            "escalating_acuity": escalating_acuity,
            "holder_acuity": holder_acuity,
            "decision": EscalationDecision.REJECTED.value,
            "rejection_reason": "HOLDER_HIGHER_ACUITY",
        }

    # ── 6. Escalation APPROVED: Preempt Holder & Allocate to Escalator ──
    suggested_alt = await find_alternative_resource(db, target_resource_id, resource_type_str)

    if holder_tx:
        await preempt_holder(
            db=db,
            holder_tx=holder_tx,
            target_resource_id=target_resource_id,
            escalating_tx=escalating_tx,
            suggested_alternative=suggested_alt,
            redis_client=redis_client,
        )

    # Allocate target resource directly to escalating TX
    if res_obj:
        res_obj.status = ResourceStatus.locked
        res_obj.held_by_tx = escalating_tx_id
        res_obj.version = res_obj.version + 1
        res_obj.updated_at = now_utc

    # Record escalation decision
    req = EscalationRequest(
        id=escalation_id,
        escalating_tx_id=escalating_tx_id,
        escalating_acuity=Decimal(str(escalating_acuity)),
        target_resource_id=target_resource_id,
        holder_tx_id=holder_tx_id,
        holder_acuity=Decimal(str(holder_acuity)),
        decision=EscalationDecision.APPROVED.value,
        rejection_reason=None,
        requested_by=requested_by,
        requested_at=now_utc,
        resolved_at=now_utc,
        source_feature=source_feature,
    )
    db.add(req)
    await db.flush()

    # Log Audit Event with BOTH TX IDs
    await create_audit_event(
        db=db,
        event_type="ESCALATION_RESOLVED",
        tx_id=escalating_tx_id,
        decision="APPROVED",
        detail={
            "escalation_id": str(escalation_id),
            "decision": "APPROVED",
            "escalating_tx_id": escalating_tx_id,
            "escalating_acuity": escalating_acuity,
            "holder_tx_id": holder_tx_id,
            "holder_acuity": holder_acuity,
            "target_resource_id": target_resource_id,
            "suggested_alternative": suggested_alt,
            "source_feature": source_feature,
        },
    )

    # Broadcast to dashboard
    if redis_client:
        try:
            await publish_event(
                "pubsub:dashboard",
                {
                    "event": "ESCALATION_RESOLVED",
                    "escalation_id": str(escalation_id),
                    "decision": "APPROVED",
                    "escalating_tx_id": escalating_tx_id,
                    "holder_tx_id": holder_tx_id,
                    "target_resource_id": target_resource_id,
                    "escalating_acuity": escalating_acuity,
                    "holder_acuity": holder_acuity,
                    "source_feature": source_feature,
                    "suggested_alternative": suggested_alt,
                    "timestamp": now_utc.isoformat(),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish ESCALATION_RESOLVED: {e}")

    return {
        "escalation_id": str(escalation_id),
        "escalating_tx_id": escalating_tx_id,
        "target_resource_id": target_resource_id,
        "holder_tx_id": holder_tx_id,
        "escalating_acuity": escalating_acuity,
        "holder_acuity": holder_acuity,
        "decision": EscalationDecision.APPROVED.value,
        "suggested_alternative": suggested_alt,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. PREEMPT HOLDER VIA CASCADE COMPENSATION
# ─────────────────────────────────────────────────────────────────────────────

async def preempt_holder(
    db: AsyncSession,
    holder_tx: Transaction,
    target_resource_id: str,
    escalating_tx: Transaction,
    suggested_alternative: Optional[Dict[str, Any]],
    redis_client: Optional[aioredis.Redis] = None,
) -> None:
    """
    Forces the holder transaction into rollback/compensation using the existing
    Cascade Dependency Compensation engine, then notifies the holder's user via WebSocket.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Rollback / Compensate holder transaction
    is_bundle = (
        holder_tx.request_type == RequestType.care_bundle
        if hasattr(holder_tx.request_type, "value")
        else str(holder_tx.request_type) == "care_bundle"
    )

    if is_bundle:
        # Use existing cascade dependency compensation
        await initiate_compensation(db=db, tx=holder_tx)
    else:
        # Single resource release
        await release_single_resource(db=db, tx_id=holder_tx.tx_id, resource_id=target_resource_id)
        holder_tx.state = TxState.ABORTED
        holder_tx.updated_at = now_utc
        h_abort = TransactionStateHistory(
            tx_id=holder_tx.tx_id,
            state=TxState.ABORTED,
            occurred_at=now_utc,
        )
        db.add(h_abort)

    await db.flush()

    # 2. Push WebSocket Toast Notification to Preempted User
    if redis_client:
        notif_payload = {
            "event": "PREEMPTION_NOTIFICATION",
            "preempted_tx_id": holder_tx.tx_id,
            "requested_by": holder_tx.requested_by,
            "preempted_resource_id": target_resource_id,
            "escalating_tx_id": escalating_tx.tx_id,
            "message": f"Resource {target_resource_id} was reassigned to a critical patient.",
            "suggested_alternative": suggested_alternative,
            "timestamp": now_utc.isoformat(),
        }
        try:
            msg = json.dumps(notif_payload, default=str)
            await redis_client.publish("pubsub:dashboard", msg)
        except Exception as e:
            logger.warning(f"Failed to publish PREEMPTION_NOTIFICATION: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. ALTERNATIVE RESOURCE FINDER
# ─────────────────────────────────────────────────────────────────────────────

async def find_alternative_resource(
    db: AsyncSession,
    target_resource_id: str,
    resource_type_str: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Queries for the next available/READY resource of the same type.
    """
    if not resource_type_str:
        return None

    # Check Bed
    if resource_type_str == "bed":
        bed_stmt = (
            select(Bed)
            .where(
                Bed.status == BedStatus.READY,
                Bed.id != target_resource_id,
            )
            .limit(1)
        )
        bed_res = await db.execute(bed_stmt)
        alt_bed = bed_res.scalar_one_or_none()
        if alt_bed:
            return {
                "resource_id": alt_bed.id,
                "label": alt_bed.bed_number,
                "type": "bed",
                "ward": alt_bed.ward,
                "floor": alt_bed.floor,
            }
        return None

    # Check Resource table (OT, Surgeon, Anesthesia, Ventilator)
    res_stmt = (
        select(Resource)
        .where(
            Resource.status == ResourceStatus.available,
            Resource.resource_id != target_resource_id,
        )
        .limit(1)
    )
    res_result = await db.execute(res_stmt)
    alt_res = res_result.scalar_one_or_none()
    if alt_res:
        return {
            "resource_id": alt_res.resource_id,
            "label": alt_res.label,
            "type": alt_res.type.value if hasattr(alt_res.type, "value") else str(alt_res.type),
        }

    return None
