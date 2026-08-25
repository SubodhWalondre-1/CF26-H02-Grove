"""
AI Emergency Resource Recommendation Engine — Feature #20

READ-ONLY GUARANTEE:
This service MUST NEVER write to, lock, or mutate the `resources`, `beds`, or
`transactions` tables. It acts solely as an in-memory ranking and advisory layer.

Key Guarantees:
  • Fetches live resource pool and active conflict map in <= 2 queries.
  • In-memory scoring algorithm based on readiness, proximity, wait time, and conflict risk.
  • Acuity-weighted ranking producing top-3 explainable bundle options.
  • Multi-patient (mass casualty) greedy provisional deduplication without double-booking.
  • Graceful fallback handling with nearest turnaround ETA.
"""

import itertools
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.procedure_requirements import get_required_resource_categories
from app.models.models import Bed, BedStatus, Resource, ResourceStatus
from app.schemas.recommendation import (
    BundleOption,
    BundleResourceItem,
    PatientIntakeItem,
    PatientRecommendation,
    RecommendationResponse,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PURE SCORING FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def calculate_resource_score(
    resource: Dict[str, Any],
    conflict_held_ids: Set[str],
) -> Tuple[float, str]:
    """
    Computes individual resource fitness score:
      score = (+40 if READY) + (proximity_bonus <= 10) - (est_wait * 2) - (conflict_penalty 15)
    Returns (score, reasoning_bullet).
    """
    res_id = resource["resource_id"]
    status = resource.get("status", "").upper()
    is_ready = status in ("READY", "AVAILABLE")
    est_wait = resource.get("est_wait_minutes", 0)

    # 1. Ready bonus
    ready_bonus = 40.0 if is_ready else 0.0

    # 2. Proximity bonus
    floor = resource.get("floor")
    proximity_bonus = 10.0 if floor == 2 or "OT" in resource.get("label", "") else 5.0

    # 3. Wait time penalty
    wait_penalty = est_wait * 2.0

    # 4. Conflict penalty
    has_conflict = res_id in conflict_held_ids or status == "TENTATIVE"
    conflict_penalty = 15.0 if has_conflict else 0.0

    score = ready_bonus + proximity_bonus - wait_penalty - conflict_penalty

    # Generate clinical reasoning bullet
    label = resource.get("label", res_id)
    if is_ready and not has_conflict:
        reasoning = f"{label} is READY (optimal match, no wait)"
    elif is_ready and has_conflict:
        reasoning = f"{label} is READY but has an active tentative hold (-15 penalty)"
    elif est_wait > 0:
        reasoning = f"{label} turnaround in progress (est. {est_wait}m wait)"
    else:
        reasoning = f"{label} in {status} state"

    return score, reasoning


def calculate_bundle_score(
    bundle_resources: List[BundleResourceItem],
    acuity_score: float,
    conflict_risk: int = 0,
) -> float:
    """
    Computes aggregate bundle score:
      bundle_score = sum(resource_scores) + (acuity_score * 5) - (conflict_risk * 10)
    """
    base_sum = sum(r.score for r in bundle_resources)
    acuity_boost = float(acuity_score) * 5.0
    conflict_deduction = float(conflict_risk) * 10.0
    return round(base_sum + acuity_boost - conflict_deduction, 2)


# ─────────────────────────────────────────────────────────────────────────────
# 2. IN-MEMORY BUNDLE COMBINATION GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def match_resource_category(res_type: str, category: str) -> bool:
    """Matches a resource's type string to the requested procedure category."""
    rt = res_type.lower()
    cat = category.lower()

    if cat == "ot" and ("ot" in rt or "operating" in rt):
        return True
    if cat == "surgeon" and "surgeon" in rt:
        return True
    if cat == "anesthesia" and "anesthesia" in rt:
        return True
    if cat == "ventilator" and "ventilator" in rt:
        return True
    if cat == "bed_icu" and ("icu" in rt or rt == "bed_icu"):
        return True
    if cat == "bed_general" and ("general" in rt or rt == "bed_general" or rt == "bed"):
        return True
    if cat == "bed_stepdown" and ("stepdown" in rt or "general" in rt):
        return True
    if cat == "transport_unit" and ("transport" in rt or "ambulance" in rt or "other" in rt):
        return True
    if cat.startswith("diagnostic") and ("diagnostic" in rt or cat in rt):
        return True
    if cat == "lab_slot" and ("lab" in rt or "slot" in rt):
        return True

    return rt == cat


def generate_candidate_bundles(
    required_categories: List[str],
    available_resources: List[Dict[str, Any]],
    conflict_held_ids: Set[str],
    excluded_resource_ids: Set[str],
    acuity_score: float,
) -> List[BundleOption]:
    """
    Forms and ranks all valid resource combination bundles satisfying required categories.
    """
    # 1. Filter out excluded resources and score candidates
    scored_by_category: Dict[str, List[BundleResourceItem]] = {}

    for cat in required_categories:
        candidates = []
        for res in available_resources:
            res_id = res["resource_id"]
            if res_id in excluded_resource_ids:
                continue

            if match_resource_category(res["type"], cat):
                score, reason = calculate_resource_score(res, conflict_held_ids)
                item = BundleResourceItem(
                    resource_id=res_id,
                    type=res["type"],
                    label=res["label"],
                    status=res.get("status", "AVAILABLE"),
                    score=score,
                    details={"reasoning": reason, "floor": res.get("floor")},
                )
                candidates.append(item)

        # Sort candidate resources per category descending by score
        candidates.sort(key=lambda x: x.score, reverse=True)
        scored_by_category[cat] = candidates

    # If any category has 0 candidates, cannot form a full bundle
    for cat in required_categories:
        if not scored_by_category.get(cat):
            return []

    # 2. Form cartesian combinations (take top 3 per category to prevent explosion)
    category_choices = [scored_by_category[cat][:3] for cat in required_categories]
    all_combos = list(itertools.product(*category_choices))

    bundle_options: List[BundleOption] = []
    seen_combos = set()

    for idx, combo in enumerate(all_combos):
        res_ids = tuple(sorted(r.resource_id for r in combo))
        # Ensure no duplicate resource used for multiple categories in same bundle
        if len(set(res_ids)) < len(combo) or res_ids in seen_combos:
            continue
        seen_combos.add(res_ids)

        bundle_res_list = list(combo)
        conflict_risk = sum(1 for r in bundle_res_list if r.resource_id in conflict_held_ids)
        b_score = calculate_bundle_score(bundle_res_list, acuity_score, conflict_risk)

        # Aggregate reasoning
        reasons = [r.details.get("reasoning", f"{r.label} available") for r in bundle_res_list]

        bundle_options.append(
            BundleOption(
                bundle_id=f"BNDL-REC-{idx+1}-{uuid.uuid4().hex[:6]}",
                resources=bundle_res_list,
                bundle_score=b_score,
                reasoning=reasons,
                greedy_reserved=False,
            )
        )

    # 3. Sort bundles descending by bundle_score
    bundle_options.sort(key=lambda b: b.bundle_score, reverse=True)
    return bundle_options


# ─────────────────────────────────────────────────────────────────────────────
# 3. CORE SERVICE ENTRYPOINT & MULTI-PATIENT PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

async def get_recommendations(
    patients: List[PatientIntakeItem],
    db: AsyncSession,
) -> RecommendationResponse:
    """
    Evaluates and returns top 3 ranked bundle recommendations per incoming patient.
    Enforces greedy provisional assignment across multi-patient mass casualty intakes.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Fetch live resource pool in 2 fast queries
    # Query A: All Resources
    res_stmt = select(Resource)
    resources_db = list((await db.execute(res_stmt)).scalars().all())

    # Query B: All Beds
    bed_stmt = select(Bed)
    beds_db = list((await db.execute(bed_stmt)).scalars().all())

    # Assemble normalized resource objects
    resource_pool: List[Dict[str, Any]] = []
    conflict_held_ids: Set[str] = set()

    for r in resources_db:
        st = r.status.value.upper()
        if r.held_by_tx or st == "TENTATIVE":
            conflict_held_ids.add(r.resource_id)

        est_wait = 0
        if r.estimated_ready_at and r.estimated_ready_at > now_utc:
            est_wait = int((r.estimated_ready_at - now_utc).total_seconds() / 60)

        resource_pool.append({
            "resource_id": r.resource_id,
            "type": r.type.value,
            "label": r.label,
            "status": st,
            "est_wait_minutes": est_wait,
            "is_bed": False,
        })

    for b in beds_db:
        st = b.status.value.upper()
        if st in ("OCCUPIED", "TENTATIVE_HOLD"):
            conflict_held_ids.add(b.id)

        est_wait = 0
        if b.estimated_ready_at and b.estimated_ready_at > now_utc:
            est_wait = int((b.estimated_ready_at - now_utc).total_seconds() / 60)

        resource_pool.append({
            "resource_id": b.id,
            "type": f"bed_{b.bed_type.value.lower()}",
            "label": f"Bed {b.bed_number} (Floor {b.floor})",
            "status": st,
            "floor": b.floor,
            "est_wait_minutes": est_wait,
            "is_bed": True,
        })

    # 2. Multi-patient sorting: highest acuity processed first
    sorted_patients = sorted(patients, key=lambda p: float(p.acuity_score), reverse=True)

    results: List[PatientRecommendation] = []
    excluded_for_lower_acuity: Set[str] = set()

    for patient in sorted_patients:
        req_categories = get_required_resource_categories(
            procedure_type=patient.procedure_type,
            clinical_notes=patient.clinical_notes,
        )

        candidate_bundles = generate_candidate_bundles(
            required_categories=req_categories,
            available_resources=resource_pool,
            conflict_held_ids=conflict_held_ids,
            excluded_resource_ids=excluded_for_lower_acuity,
            acuity_score=patient.acuity_score,
        )

        if not candidate_bundles:
            # Fallback: determine nearest ETA from unavailable candidate pool
            relevant_waits = [
                r.get("est_wait_minutes", 15)
                for r in resource_pool
                if any(match_resource_category(r["type"], cat) for cat in req_categories)
                and r.get("est_wait_minutes", 0) > 0
            ]
            nearest_eta = min(relevant_waits) if relevant_waits else 15

            results.append(
                PatientRecommendation(
                    patient_id=patient.patient_id,
                    procedure_type=patient.procedure_type,
                    acuity_score=patient.acuity_score,
                    recommendations=[],
                    fallback="no_ready_resources",
                    nearest_eta_minutes=nearest_eta,
                    partial_options=False,
                )
            )
        else:
            top_3 = candidate_bundles[:3]
            is_partial = len(top_3) < 3

            # Mark top pick as greedy_reserved and exclude its resources from subsequent patients
            top_pick = top_3[0]
            top_pick.greedy_reserved = True
            for res_item in top_pick.resources:
                excluded_for_lower_acuity.add(res_item.resource_id)

            results.append(
                PatientRecommendation(
                    patient_id=patient.patient_id,
                    procedure_type=patient.procedure_type,
                    acuity_score=patient.acuity_score,
                    recommendations=top_3,
                    fallback=None,
                    nearest_eta_minutes=None,
                    partial_options=is_partial,
                )
            )

    logger.info(
        f"AI Recommendation Engine evaluated {len(patients)} patients against "
        f"{len(resource_pool)} resources (greedy reserved {len(excluded_for_lower_acuity)} items)."
    )

    return RecommendationResponse(results=results)
