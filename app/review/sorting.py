from datetime import datetime
from typing import Protocol

from app.review.urgency import (
    URGENCY_RANK,
    UrgencyThresholds,
    classify_urgency,
)


class QueueSortable(Protocol):
    manual_priority: int
    due_at: datetime | None
    high_count: int
    medium_count: int
    received_at: datetime


def remaining_days(due_at: datetime | None, now: datetime) -> int | None:
    if due_at is None:
        return None
    return (due_at - now).days


def review_queue_key(
    item: QueueSortable,
    now: datetime,
    thresholds: UrgencyThresholds | None = None,
) -> tuple[int, int, int, int, int, datetime]:
    """Deterministic queue order.

    Deadline classification is delegated to urgency.py so the queue and the
    Workbench badges always agree on the same thresholds.
    """
    urgency = classify_urgency(
        item.due_at, now, thresholds or UrgencyThresholds()
    )
    due_rank = (
        urgency.remaining_days if urgency.remaining_days is not None else 2**31 - 1
    )
    return (
        -item.manual_priority,
        URGENCY_RANK[urgency.level],
        -item.high_count,
        -item.medium_count,
        due_rank,
        item.received_at,
    )
