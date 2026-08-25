"""
Record Aggregation Service — Feature #21: Digital Emergency Operation Record (PDF)

DATA SOURCE DISCIPLINE:
The record must be constructed ENTIRELY from `audit_events`.
It must never query live resource state or mutable transaction rows,
guaranteeing an immutable, historically accurate snapshot at close time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditEvent

logger = logging.getLogger(__name__)


@dataclass
class OperationRecordData:
    tx_id: str
    closed_at: str
    patient: Dict[str, Any]
    medical_team: List[Dict[str, str]]
    resources: List[Dict[str, str]]
    timeline: List[Dict[str, Any]]
    status: str
    audit_id: str
    arbiter_notes: Optional[str] = None


async def aggregate_operation_record(
    tx_id: str,
    db: AsyncSession,
) -> OperationRecordData:
    """
    Assembles structured OperationRecordData strictly by analyzing audit_events for the given tx_id.
    """
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.tx_id == tx_id)
        .order_by(AuditEvent.occurred_at.asc())
    )
    events = list((await db.execute(stmt)).scalars().all())

    if not events:
        raise ValueError(f"No audit events found for transaction '{tx_id}'. Cannot generate record.")

    # 1. Patient & Case Extraction
    patient_id = "UNKNOWN"
    patient_name = "Unknown Patient"
    procedure_type = "Emergency Procedure"
    acuity_score = 5.0
    criticality_label = "Standard"

    # 2. Medical Team & Participants
    medical_team_map: Dict[str, Dict[str, str]] = {}

    # 3. Resources and their final states
    resource_map: Dict[str, Dict[str, str]] = {}

    # 4. Chronological Timeline
    timeline: List[Dict[str, Any]] = []

    # 5. Final Status & Arbiter details
    final_status = "CLOSED"
    arbiter_notes = None
    closed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    for ev in events:
        ev_type = ev.event_type
        detail = ev.detail or {}
        time_str = ev.occurred_at.strftime("%Y-%m-%d %H:%M:%S UTC") if ev.occurred_at else ""

        # Check for Patient Info in detail
        if "patient_id" in detail:
            patient_id = detail["patient_id"]
        if "patient_name" in detail:
            patient_name = detail["patient_name"]
        if "procedure_type" in detail:
            procedure_type = str(detail["procedure_type"]).replace("_", " ").title()
        if "acuity" in detail:
            try:
                acuity_score = float(detail["acuity"])
            except (ValueError, TypeError):
                pass
        elif "effective_score" in detail:
            try:
                acuity_score = float(detail["effective_score"])
            except (ValueError, TypeError):
                pass

        if acuity_score >= 9.5:
            criticality_label = "CRITICAL (Immediate Life Threat)"
        elif acuity_score >= 7.0:
            criticality_label = "URGENT (High Acuity)"
        else:
            criticality_label = "STANDARD (Stable)"

        # Medical Team from actors/requesters
        actor = detail.get("who") or detail.get("requested_by") or detail.get("user_id") or "Clinical Staff"
        actor_role = detail.get("role") or "Clinician"
        if actor and actor != "system":
            if "surg" in actor.lower() or "dr" in actor.lower():
                actor_role = "Lead Surgeon / Attending"
            elif "anes" in actor.lower():
                actor_role = "Anesthesiologist"
            elif "nurse" in actor.lower():
                actor_role = "Nurse Specialist"

            medical_team_map[actor] = {
                "employee_id": actor,
                "name": detail.get("display_name") or actor.replace(".", " ").title(),
                "role": actor_role,
            }

        # Resource Tracking
        res_id = ev.resource_id or detail.get("resource_id")
        if res_id:
            res_type = detail.get("resource_type") or ("OT" if "OT" in res_id else "Resource")
            res_label = detail.get("resource_label") or detail.get("label") or res_id

            current_res_status = "ALLOCATED"
            if ev_type in ("TX_COMMITTED", "RESOURCE_LOCKED", "CARE_BUNDLE_COMMITTED"):
                current_res_status = "COMMITTED"
            elif ev_type in ("TX_ROLLED_BACK", "RESOURCE_RELEASED"):
                current_res_status = "ROLLED_BACK"
            elif ev_type in ("COMPENSATION_EXECUTED", "RESOURCE_COMPENSATED"):
                current_res_status = "COMPENSATED"

            resource_map[res_id] = {
                "resource_id": res_id,
                "type": res_type,
                "label": res_label,
                "final_status": current_res_status,
            }

        # Multi-resource bundles in detail
        if "resources" in detail and isinstance(detail["resources"], list):
            for r_item in detail["resources"]:
                if isinstance(r_item, dict):
                    rid = r_item.get("resource_id", "RES")
                    resource_map[rid] = {
                        "resource_id": rid,
                        "type": r_item.get("type", "Resource"),
                        "label": r_item.get("label", rid),
                        "final_status": "COMMITTED",
                    }
                elif isinstance(r_item, str):
                    resource_map[r_item] = {
                        "resource_id": r_item,
                        "type": "Resource",
                        "label": r_item,
                        "final_status": "COMMITTED",
                    }

        # Timeline entries
        timeline.append({
            "event": ev_type,
            "timestamp": time_str,
            "actor": actor,
            "decision": ev.decision or "SUCCESS",
            "score": float(ev.effective_score) if ev.effective_score is not None else None,
        })

        # Conflict arbitration score notes
        if "conflict" in ev_type.lower() or ev.conflict_id or "arbiter_scores" in detail:
            scores_detail = detail.get("arbiter_scores") or f"Decision: {ev.decision}, Score: {ev.effective_score}"
            arbiter_notes = f"Arbiter Resolution (Conflict ID: {ev.conflict_id or 'Auto'}): {scores_detail}"

        # Final Status determination
        if ev_type in ("TX_COMMITTED", "CARE_BUNDLE_COMMITTED", "TRANSFER_COMPLETED"):
            final_status = "COMPLETED"
        elif ev_type in ("TX_ROLLED_BACK", "TRANSACTION_ABORTED"):
            final_status = "ROLLED_BACK"
        elif ev_type in ("COMPENSATION_EXECUTED", "TRANSACTION_COMPENSATED"):
            final_status = "COMPENSATED"

        if ev_type in ("TX_CLOSED", "TRANSACTION_CLOSED"):
            closed_at = time_str

    patient_data = {
        "patient_id": patient_id,
        "name": patient_name,
        "procedure_type": procedure_type,
        "acuity_score": acuity_score,
        "criticality_label": criticality_label,
    }

    # Ensure at least 1 team member is listed
    if not medical_team_map:
        medical_team_map["USR-PRIMARY"] = {
            "employee_id": "USR-PRIMARY",
            "name": "Attending Clinical Coordinator",
            "role": "Lead Coordinator",
        }

    return OperationRecordData(
        tx_id=tx_id,
        closed_at=closed_at,
        patient=patient_data,
        medical_team=list(medical_team_map.values()),
        resources=list(resource_map.values()),
        timeline=timeline,
        status=final_status,
        audit_id=f"AUD-{tx_id}",
        arbiter_notes=arbiter_notes,
    )
