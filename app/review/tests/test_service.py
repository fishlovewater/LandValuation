import pytest

from app.core.exceptions import AppError
from app.review.service import ensure_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("RECEIVED", "PREPROCESSING"),
        ("PREPROCESSING", "PENDING_MATERIALS"),
        ("PREPROCESSING", "READY_FOR_REVIEW"),
        ("READY_FOR_REVIEW", "ANALYZING"),
        ("ANALYZING", "REVIEW_REQUIRED"),
        ("REVIEW_REQUIRED", "APPROVED"),
        ("APPROVED", "REVIEW_COMPLETED"),
    ],
)
def test_legal_review_transition_returns_target(current: str, target: str):
    assert ensure_transition(current, target) == target


def test_illegal_review_transition_raises_conflict():
    with pytest.raises(AppError) as raised:
        ensure_transition("RECEIVED", "APPROVED")

    assert raised.value.code == "REVIEW_STATE_CONFLICT"
    assert raised.value.status_code == 409


def test_completed_review_cannot_transition():
    with pytest.raises(AppError):
        ensure_transition("REVIEW_COMPLETED", "PREPROCESSING")
