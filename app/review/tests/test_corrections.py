import pytest

from app.core.exceptions import AppError
from app.review.corrections import (
    CorrectionGateSummary,
    validate_correction_send,
)


@pytest.mark.parametrize(
    "summary, blocker",
    [
        (CorrectionGateSummary(False, 0, 1, 0, False), "最新一次智慧審查尚未完成"),
        (CorrectionGateSummary(True, 1, 1, 0, False), "尚有 1 項疑點未判定"),
        (CorrectionGateSummary(True, 0, 0, 1, False), "尚有 1 項專業覆核"),
        (CorrectionGateSummary(True, 0, 0, 0, False), "沒有確認成立的疑點"),
        (CorrectionGateSummary(True, 0, 1, 0, True), "已有未完成修正通知"),
    ],
)
def test_correction_send_gate_rejects_each_blocker(summary, blocker):
    with pytest.raises(AppError) as error:
        validate_correction_send(summary)
    assert blocker in str(error.value.message)
    assert error.value.code == "CORRECTION_REQUEST_BLOCKED"
    assert error.value.status_code == 409


def test_correction_send_gate_passes_when_clean():
    validate_correction_send(CorrectionGateSummary(True, 0, 1, 0, False))


from app.review.corrections import (  # noqa: E402
    ReviewCompletionSummary,
    validate_review_completion,
)


def _clean_completion_summary():
    return ReviewCompletionSummary(
        has_completed_run=True,
        open_missing_count=0,
        open_finding_count=0,
        confirmed_finding_count=0,
        expert_finding_count=0,
        active_request_count=0,
        non_rechecked_request_count=0,
        not_evaluated_item_count=0,
    )


def test_review_completion_requires_reason():
    with pytest.raises(AppError) as error:
        validate_review_completion("  ", _clean_completion_summary())
    assert "完成審查必須填寫理由" in str(error.value.message)


@pytest.mark.parametrize(
    "field, blocker",
    [
        ("has_completed_run", "最新一次智慧審查尚未完成"),
        ("open_missing_count", "仍有 1 項缺件"),
        ("open_finding_count", "仍有 1 項疑點未判定"),
        ("confirmed_finding_count", "仍有 1 項疑點待修正"),
        ("expert_finding_count", "仍有 1 項專業覆核"),
        ("active_request_count", "仍有修正通知尚未完成新版重檢"),
        ("non_rechecked_request_count", "仍有修正通知尚未完成新版重檢"),
        ("not_evaluated_item_count", "仍有修正項目無法判定重檢結果"),
    ],
)
def test_review_completion_gate_rejects_each_blocker(field, blocker):
    kwargs = _clean_completion_summary().__dict__.copy()
    kwargs[field] = False if field == "has_completed_run" else 1
    with pytest.raises(AppError) as error:
        validate_review_completion("完成", ReviewCompletionSummary(**kwargs))
    assert blocker in str(error.value.message)
    assert error.value.code == "REVIEW_COMPLETION_BLOCKED"


def test_review_completion_passes_when_clean():
    validate_review_completion("已確認無誤", _clean_completion_summary())


def test_review_completion_summary_has_no_invalid_value_field():
    assert "invalid_value_count" not in ReviewCompletionSummary.__dataclass_fields__
