import pytest

from app.core.exceptions import AppError
from app.review.status_policy import (
    REVIEW_CORRECTION_RECHECK_STATUSES,
    REVIEW_EDITABLE_STATUSES,
    REVIEW_LIMITED_STATUSES,
    REVIEW_MUTABLE_STATUSES,
    REVIEW_READ_ONLY_STATUSES,
    ensure_review_status_allowed,
)


def test_generic_review_mutations_are_limited_to_editable_states():
    assert REVIEW_MUTABLE_STATUSES == REVIEW_EDITABLE_STATUSES
    assert REVIEW_MUTABLE_STATUSES.isdisjoint(REVIEW_LIMITED_STATUSES)
    assert REVIEW_MUTABLE_STATUSES.isdisjoint(REVIEW_READ_ONLY_STATUSES)


def test_correction_recheck_is_limited_to_returned_for_revision():
    assert REVIEW_CORRECTION_RECHECK_STATUSES == {"RETURNED_FOR_REVISION"}


@pytest.mark.parametrize(
    "status",
    ["PENDING_MATERIALS", "RETURNED_FOR_REVISION", "SUPPLEMENT_REQUIRED", "APPROVED", "REVIEW_COMPLETED", "RUNNING", "COMPLETED"],
)
def test_non_editable_or_legacy_statuses_fail_safe_for_generic_mutation(status):
    with pytest.raises(AppError) as exc_info:
        ensure_review_status_allowed(status, REVIEW_MUTABLE_STATUSES, action="更新審查案件")

    assert exc_info.value.code == "REVIEW_STATE_CONFLICT"
    assert exc_info.value.status_code == 409
