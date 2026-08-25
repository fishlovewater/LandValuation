from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.review.sorting import remaining_days, review_queue_key


@dataclass(frozen=True)
class QueueItem:
    case_no: str
    manual_priority: int
    due_at: datetime | None
    high_count: int
    medium_count: int
    received_at: datetime


def test_queue_key_prioritizes_manual_then_overdue_then_risk():
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    received = now - timedelta(days=3)
    cases = [
        QueueItem("NORMAL", 0, now + timedelta(days=5), 0, 0, received),
        QueueItem("HIGH", 0, now + timedelta(days=2), 2, 0, received),
        QueueItem("OVERDUE", 0, now - timedelta(hours=1), 0, 0, received),
        QueueItem("MANUAL", 10, now + timedelta(days=7), 0, 0, received),
    ]

    ordered = sorted(cases, key=lambda item: review_queue_key(item, now))

    assert [item.case_no for item in ordered] == ["MANUAL", "OVERDUE", "HIGH", "NORMAL"]


def test_queue_key_uses_medium_risk_then_due_date_then_received_time():
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    cases = [
        QueueItem("LATER", 0, now + timedelta(days=3), 0, 1, now - timedelta(days=4)),
        QueueItem("NEWER", 0, now + timedelta(days=2), 0, 1, now - timedelta(days=1)),
        QueueItem("OLDER", 0, now + timedelta(days=2), 0, 1, now - timedelta(days=2)),
        QueueItem("MORE_MEDIUM", 0, now + timedelta(days=5), 0, 2, now),
    ]

    ordered = sorted(cases, key=lambda item: review_queue_key(item, now))

    assert [item.case_no for item in ordered] == ["MORE_MEDIUM", "OLDER", "NEWER", "LATER"]


def test_remaining_days_handles_due_date_and_no_deadline():
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)

    assert remaining_days(now + timedelta(days=2), now) == 2
    assert remaining_days(None, now) is None
