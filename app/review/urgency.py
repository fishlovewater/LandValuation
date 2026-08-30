"""Deadline urgency calculation and queue ranking primitives.

Deadline urgency is a separate value from content risk. It is derived at request
time from the case deadline and the configured thresholds, and is never
persisted on Review rows.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


UrgencyLevel = Literal["OVERDUE", "URGENT", "DUE_SOON", "NORMAL", "NOT_SET"]

# Deterministic queue ordering: the most pressing deadline sorts first.
URGENCY_RANK: dict[str, int] = {
    "OVERDUE": 0,
    "URGENT": 1,
    "DUE_SOON": 2,
    "NORMAL": 3,
    "NOT_SET": 4,
}


@dataclass(frozen=True)
class UrgencyThresholds:
    urgent_days: int = 3
    due_soon_days: int = 7


@dataclass(frozen=True)
class UrgencyResult:
    level: UrgencyLevel
    remaining_days: int | None


def classify_urgency(
    due_at: datetime | None,
    now: datetime,
    thresholds: UrgencyThresholds,
) -> UrgencyResult:
    if due_at is None:
        return UrgencyResult("NOT_SET", None)
    days = (due_at - now).days
    if due_at < now:
        return UrgencyResult("OVERDUE", days)
    if days <= thresholds.urgent_days:
        return UrgencyResult("URGENT", days)
    if days <= thresholds.due_soon_days:
        return UrgencyResult("DUE_SOON", days)
    return UrgencyResult("NORMAL", days)
