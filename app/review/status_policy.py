"""Central Review-state policy for interactive mutations.

Workflow transitions remain defined in :mod:`app.review.service`.  This module
answers the separate question of whether a user-facing operation is allowed in
the current state.  Unknown/legacy states are intentionally fail-closed.
"""

from collections.abc import Collection

from app.core.exceptions import AppError


REVIEW_EDITABLE_STATUSES = frozenset(
    {
        "RECEIVED",
        "PREPROCESSING",
        "READY_FOR_REVIEW",
        "ANALYZING",
        "REVIEW_REQUIRED",
        "EXPERT_REVIEW",
    }
)
REVIEW_LIMITED_STATUSES = frozenset(
    {
        "PENDING_MATERIALS",
        "RETURNED_FOR_REVISION",
        "SUPPLEMENT_REQUIRED",
    }
)
REVIEW_READ_ONLY_STATUSES = frozenset({"APPROVED", "REVIEW_COMPLETED"})

# Generic initial/recovery validation.  RETURNED_FOR_REVISION must use the
# correction recheck flow so that the new submission/document lineage is
# validated before the next run.
REVIEW_STARTABLE_STATUSES = frozenset(
    {"RECEIVED", "PREPROCESSING", "PENDING_MATERIALS", "READY_FOR_REVIEW"}
)
REVIEW_TRIAGE_STATUSES = frozenset({"REVIEW_REQUIRED", "EXPERT_REVIEW"})
REVIEW_CORRECTION_REQUEST_STATUSES = frozenset({"REVIEW_REQUIRED"})
REVIEW_COMPLETION_STATUSES = frozenset({"REVIEW_REQUIRED"})
REVIEW_SUPPLEMENT_REQUEST_STATUSES = frozenset(
    {"PENDING_MATERIALS", "SUPPLEMENT_REQUIRED"}
)
REVIEW_CORRECTION_RECHECK_STATUSES = frozenset({"RETURNED_FOR_REVISION"})

# External source data may be prepared before the immutable review run, or as a
# narrowly scoped input/revision recovery action.  It must not be changed while
# a reviewer is deciding an already-frozen run, nor after completion.
REVIEW_EXTERNAL_INPUT_MUTATION_STATUSES = frozenset(
    {
        "RECEIVED",
        "PREPROCESSING",
        "PENDING_MATERIALS",
        "READY_FOR_REVIEW",
        "RETURNED_FOR_REVISION",
        "SUPPLEMENT_REQUIRED",
    }
)

# Generic metadata/review mutations are allowed only during normal pending or
# in-progress review. Limited states keep only their explicitly named recovery
# actions below; they are otherwise read-only.
REVIEW_MUTABLE_STATUSES = REVIEW_EDITABLE_STATUSES
REVIEW_CANONICAL_STATUSES = (
    REVIEW_EDITABLE_STATUSES | REVIEW_LIMITED_STATUSES | REVIEW_READ_ONLY_STATUSES
)


def ensure_review_status_allowed(
    current: str,
    allowed: Collection[str],
    *,
    action: str,
) -> None:
    """Reject mutations outside their explicitly allowed Review states."""

    if current in allowed:
        return
    raise AppError(
        "REVIEW_STATE_CONFLICT",
        f"目前案件狀態不可{action}",
        409,
        {"current": current, "allowed": sorted(allowed)},
    )


__all__ = [
    "REVIEW_CANONICAL_STATUSES",
    "REVIEW_COMPLETION_STATUSES",
    "REVIEW_CORRECTION_RECHECK_STATUSES",
    "REVIEW_CORRECTION_REQUEST_STATUSES",
    "REVIEW_EDITABLE_STATUSES",
    "REVIEW_EXTERNAL_INPUT_MUTATION_STATUSES",
    "REVIEW_LIMITED_STATUSES",
    "REVIEW_MUTABLE_STATUSES",
    "REVIEW_READ_ONLY_STATUSES",
    "REVIEW_STARTABLE_STATUSES",
    "REVIEW_SUPPLEMENT_REQUEST_STATUSES",
    "REVIEW_TRIAGE_STATUSES",
    "ensure_review_status_allowed",
]
