from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.review.urgency import UrgencyResult, UrgencyThresholds, classify_urgency
from app.review.schemas import UrgencySettingsUpdate


@pytest.mark.parametrize(
    ("days", "level"),
    [
        (-1, "OVERDUE"),
        (0, "URGENT"),
        (3, "URGENT"),
        (4, "DUE_SOON"),
        (7, "DUE_SOON"),
        (8, "NORMAL"),
    ],
)
def test_urgency_boundaries(days, level):
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    result = classify_urgency(now + timedelta(days=days), now, UrgencyThresholds(3, 7))
    assert result.level == level
    assert result.remaining_days == days


def test_no_deadline_is_not_set():
    result = classify_urgency(None, datetime.now(UTC), UrgencyThresholds(3, 7))
    assert result == UrgencyResult("NOT_SET", None)


def test_default_thresholds_are_three_and_seven():
    thresholds = UrgencyThresholds()
    assert (thresholds.urgent_days, thresholds.due_soon_days) == (3, 7)


@pytest.mark.parametrize(
    "payload",
    [
        {"urgent_days": -1, "due_soon_days": 7},
        {"urgent_days": 3, "due_soon_days": 3},
        {"urgent_days": 8, "due_soon_days": 7},
        {"urgent_days": 0, "due_soon_days": 0},
    ],
)
def test_settings_schema_rejects_invalid_threshold_pairs(payload):
    with pytest.raises(ValidationError):
        UrgencySettingsUpdate(**payload)


def test_settings_schema_accepts_valid_pair():
    settings = UrgencySettingsUpdate(urgent_days=0, due_soon_days=1)
    assert (settings.urgent_days, settings.due_soon_days) == (0, 1)
