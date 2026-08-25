from datetime import datetime
from typing import Protocol


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
) -> tuple[int, int, int, int, int, datetime]:
    days = remaining_days(item.due_at, now)
    is_overdue = item.due_at is not None and item.due_at < now
    due_rank = days if days is not None else 2**31 - 1
    return (
        -item.manual_priority,
        0 if is_overdue else 1,
        -item.high_count,
        -item.medium_count,
        due_rank,
        item.received_at,
    )
