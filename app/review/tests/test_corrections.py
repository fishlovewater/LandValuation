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
