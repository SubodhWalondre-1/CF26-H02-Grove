import pytest
from app.engine.arbiter import compute_effective_score, select_winner


# 1. Basic Effective Score formula: (base_acuity + wait_contribution) * resource_criticality
@pytest.mark.unit
def test_effective_score_basic():
    score = compute_effective_score(
        base_acuity=6.0,
        wait_minutes=20.0,
        wait_coefficient=0.12,
        criticality=1.5,
    )
    assert score == pytest.approx(12.6, rel=1e-3)
    # (6.0 + 20 * 0.12) * 1.5 = (6.0 + 2.4) * 1.5 = 12.6


# 2. Zero acuity patient still generates a score via wait time
@pytest.mark.unit
def test_effective_score_zero_acuity():
    score = compute_effective_score(
        base_acuity=0.0,
        wait_minutes=30.0,
        wait_coefficient=0.12,
        criticality=1.0,
    )
    assert score == pytest.approx(3.6, rel=1e-3)


# 3. Zero wait time — score is purely acuity × criticality
@pytest.mark.unit
def test_effective_score_zero_wait():
    score = compute_effective_score(
        base_acuity=8.0,
        wait_minutes=0.0,
        wait_coefficient=0.12,
        criticality=2.0,
    )
    assert score == pytest.approx(16.0, rel=1e-3)


# 4. Higher criticality multiplies the total correctly
@pytest.mark.unit
def test_effective_score_high_criticality():
    score = compute_effective_score(
        base_acuity=5.0,
        wait_minutes=10.0,
        wait_coefficient=0.10,
        criticality=2.5,
    )
    assert score == pytest.approx(15.0, rel=1e-3)
    # (5.0 + 1.0) * 2.5 = 15.0


# 5. Winner selection — higher score wins
@pytest.mark.unit
def test_select_winner_higher_score():
    candidates = [
        {"tx_id": "TX-A", "effective_score": 9.0, "created_at": "2026-08-24T09:00:00Z"},
        {"tx_id": "TX-B", "effective_score": 12.6, "created_at": "2026-08-24T09:00:01Z"},
    ]
    winner = select_winner(candidates)
    assert winner["tx_id"] == "TX-B"


# 6. Tie-breaking — earlier created_at wins when scores are equal
@pytest.mark.unit
def test_select_winner_tie_breaks_by_created_at():
    candidates = [
        {"tx_id": "TX-A", "effective_score": 10.0, "created_at": "2026-08-24T09:00:00Z"},
        {"tx_id": "TX-B", "effective_score": 10.0, "created_at": "2026-08-24T09:00:02Z"},
    ]
    winner = select_winner(candidates)
    assert winner["tx_id"] == "TX-A"  # created earlier


# 7. Single candidate — always wins
@pytest.mark.unit
def test_select_winner_single_candidate():
    candidates = [
        {"tx_id": "TX-A", "effective_score": 5.0, "created_at": "2026-08-24T09:00:00Z"}
    ]
    winner = select_winner(candidates)
    assert winner["tx_id"] == "TX-A"


# 8. Empty candidates list raises ValueError
@pytest.mark.unit
def test_select_winner_empty_raises():
    with pytest.raises(ValueError):
        select_winner([])


# 9. Configurable coefficient — changing coefficient changes score
@pytest.mark.unit
def test_effective_score_custom_coefficient():
    score_low = compute_effective_score(
        base_acuity=6.0,
        wait_minutes=10.0,
        wait_coefficient=0.05,
        criticality=1.0,
    )
    score_high = compute_effective_score(
        base_acuity=6.0,
        wait_minutes=10.0,
        wait_coefficient=0.20,
        criticality=1.0,
    )
    assert score_high > score_low
