import math
import pytest
from app.engine.arbiter import compute_effective_score


# 1. Score is always non-negative
@pytest.mark.unit
@pytest.mark.parametrize(
    "acuity,wait,coeff,crit",
    [
        (0.0, 0.0, 0.12, 1.0),  # absolute minimum
        (0.0, 0.0, 0.0, 0.0),  # all zeros → 0.0
        (1.0, 0.5, 0.01, 0.5),  # tiny values → still positive
    ],
)
def test_score_always_non_negative(acuity, wait, coeff, crit):
    score = compute_effective_score(acuity, wait, coeff, crit)
    assert score >= 0.0


# 2. Score increases monotonically with wait time (holding everything else constant)
@pytest.mark.unit
def test_score_increases_with_wait():
    scores = [
        compute_effective_score(6.0, w, 0.12, 1.5)
        for w in [0, 5, 10, 20, 60]
    ]
    assert scores == sorted(scores)


# 3. Score increases monotonically with base acuity
@pytest.mark.unit
def test_score_increases_with_acuity():
    scores = [
        compute_effective_score(a, 10.0, 0.12, 1.5)
        for a in [0, 2, 4, 6, 8, 10]
    ]
    assert scores == sorted(scores)


# 4. Criticality = 0 makes the score 0 regardless of acuity and wait
@pytest.mark.unit
def test_zero_criticality_means_zero_score():
    score = compute_effective_score(
        base_acuity=9.0,
        wait_minutes=100.0,
        wait_coefficient=0.12,
        criticality=0.0,
    )
    assert score == pytest.approx(0.0)


# 5. Very long wait time does not overflow (Python float-safe, but worth asserting it's finite)
@pytest.mark.unit
def test_very_long_wait_stays_finite():
    score = compute_effective_score(
        base_acuity=9.0,
        wait_minutes=1_000_000,
        wait_coefficient=0.12,
        criticality=1.5,
    )
    assert math.isfinite(score)
    assert score > 0


# 6. Formula is deterministic — same inputs always give same output
@pytest.mark.unit
def test_score_is_deterministic():
    s1 = compute_effective_score(6.0, 20.0, 0.12, 1.5)
    s2 = compute_effective_score(6.0, 20.0, 0.12, 1.5)
    assert s1 == s2
