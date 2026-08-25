import pytest
from app.schemas.recommendation import BundleResourceItem
from app.services.recommendation import (
    calculate_bundle_score,
    calculate_resource_score,
    generate_candidate_bundles,
)


def test_resource_score_ready_and_proximity():
    # Fully ready resource on floor 2 (proximity bonus = 10)
    res = {
        "resource_id": "RES-OT-1",
        "label": "OT-1",
        "type": "ot",
        "status": "READY",
        "floor": 2,
        "est_wait_minutes": 0,
    }
    score, reason = calculate_resource_score(res, conflict_held_ids=set())
    # 40 (ready) + 10 (proximity) = 50.0
    assert score == 50.0
    assert "READY" in reason


def test_resource_score_wait_and_conflict_penalties():
    # Resource with 10 min wait time and active tentative hold
    res = {
        "resource_id": "RES-VENT-1",
        "label": "VENT-1",
        "type": "ventilator",
        "status": "CLEANING",
        "floor": 1,
        "est_wait_minutes": 10,
    }
    score, reason = calculate_resource_score(res, conflict_held_ids={"RES-VENT-1"})
    # 0 (not ready) + 5 (default proximity) - (10 * 2) - 15 (conflict) = 5 - 20 - 15 = -30.0
    assert score == -30.0


def test_bundle_score_with_acuity():
    resources = [
        BundleResourceItem(resource_id="RES-1", type="ot", label="OT-1", status="READY", score=50.0),
        BundleResourceItem(resource_id="RES-2", type="surgeon", label="SURG-1", status="READY", score=45.0),
    ]
    # Acuity 9.0: sum(95.0) + (9.0 * 5) = 95.0 + 45.0 = 140.0
    high_acuity_score = calculate_bundle_score(resources, acuity_score=9.0, conflict_risk=0)
    assert high_acuity_score == 140.0

    # Acuity 4.0: sum(95.0) + (4.0 * 5) = 95.0 + 20.0 = 115.0
    low_acuity_score = calculate_bundle_score(resources, acuity_score=4.0, conflict_risk=0)
    assert low_acuity_score == 115.0


def test_generate_candidate_bundles_top_3_and_ranking():
    pool = [
        {"resource_id": "OT-1", "type": "ot", "label": "OT-1", "status": "READY", "floor": 2, "est_wait_minutes": 0},
        {"resource_id": "OT-2", "type": "ot", "label": "OT-2", "status": "READY", "floor": 1, "est_wait_minutes": 0},
        {"resource_id": "SURG-1", "type": "surgeon", "label": "Dr. A", "status": "READY", "est_wait_minutes": 0},
        {"resource_id": "SURG-2", "type": "surgeon", "label": "Dr. B", "status": "READY", "est_wait_minutes": 0},
    ]

    bundles = generate_candidate_bundles(
        required_categories=["ot", "surgeon"],
        available_resources=pool,
        conflict_held_ids=set(),
        excluded_resource_ids=set(),
        acuity_score=8.0,
    )

    assert len(bundles) == 4
    # Ensure descending order
    for i in range(len(bundles) - 1):
        assert bundles[i].bundle_score >= bundles[i + 1].bundle_score


def test_generate_candidate_bundles_zero_ready():
    # Pool missing required surgeon
    pool = [
        {"resource_id": "OT-1", "type": "ot", "label": "OT-1", "status": "READY", "floor": 2, "est_wait_minutes": 0},
    ]

    bundles = generate_candidate_bundles(
        required_categories=["ot", "surgeon"],
        available_resources=pool,
        conflict_held_ids=set(),
        excluded_resource_ids=set(),
        acuity_score=8.0,
    )

    assert len(bundles) == 0
