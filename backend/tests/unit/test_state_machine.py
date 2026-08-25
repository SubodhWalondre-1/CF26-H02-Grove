import pytest
from app.engine.coordinator import is_terminal_state, is_valid_transition


# 1. All documented valid transitions return True
@pytest.mark.unit
@pytest.mark.parametrize(
    "from_state,to_state",
    [
        ("CREATED", "QUEUED"),
        ("QUEUED", "ARBITRATING"),
        ("QUEUED", "PREPARING"),
        ("ARBITRATING", "PREPARING"),
        ("ARBITRATING", "ABORTED"),
        ("PREPARING", "COMMITTING"),
        ("PREPARING", "ROLLINGBACK"),
        ("COMMITTING", "COMMITTED"),
        ("ROLLINGBACK", "ABORTED"),
        ("COMMITTED", "ACTIVE"),
        ("ACTIVE", "COMPLETED"),
        ("ACTIVE", "CANCELLED"),
        ("ABORTED", "CLOSED"),
        ("COMPLETED", "CLOSED"),
    ],
)
def test_valid_transitions(from_state, to_state):
    assert is_valid_transition(from_state, to_state) is True


# 2. Backward transitions are invalid
@pytest.mark.unit
@pytest.mark.parametrize(
    "from_state,to_state",
    [
        ("COMMITTED", "QUEUED"),
        ("ABORTED", "PREPARING"),
        ("CLOSED", "ACTIVE"),
        ("COMPLETED", "ACTIVE"),
    ],
)
def test_backward_transitions_invalid(from_state, to_state):
    assert is_valid_transition(from_state, to_state) is False


# 3. Skipping states is invalid
@pytest.mark.unit
def test_skip_transition_invalid():
    assert is_valid_transition("CREATED", "PREPARING") is False
    assert is_valid_transition("QUEUED", "COMMITTED") is False


# 4. Same-state transition is invalid
@pytest.mark.unit
@pytest.mark.parametrize("state", ["QUEUED", "PREPARING", "COMMITTED", "ACTIVE"])
def test_self_transition_invalid(state):
    assert is_valid_transition(state, state) is False


# 5. Terminal state detection
@pytest.mark.unit
@pytest.mark.parametrize(
    "state,expected",
    [
        ("CLOSED", True),
        ("ABORTED", True),
        ("ACTIVE", False),
        ("PREPARING", False),
        ("COMMITTED", False),
        ("COMPLETED", False),
    ],
)
def test_terminal_state_detection(state, expected):
    assert is_terminal_state(state) is expected
