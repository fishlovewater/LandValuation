"""Conservative automatic transcription; uncertain fields stay human-reviewed."""
import re
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.review.intake_forms import mapped_value, fill_review_form


def compact(value):
    return re.sub(r"[\s,，]", "", str(value)).casefold()


def uncertainty_reasons(candidate, candidates):
    reasons = []
    value = candidate.extracted_value
    try:
        confidence = Decimal(str(candidate.confidence))
        if not confidence.is_finite() or confidence < Decimal(str(get_settings().review_auto_fill_confidence)):
            reasons.append("辨識信心不足")
    except (InvalidOperation, ValueError):
        reasons.append("缺少有效信心分數")
    if value is None or value == "" or value == [] or value == {}:
        reasons.append("欄位沒有有效值")
    if not candidate.source_page or not candidate.source_text:
        reasons.append("缺少來源頁碼或原文")
    elif isinstance(value, (str, int, float)) and compact(value) not in compact(candidate.source_text):
        reasons.append("辨識值需要核對來源原文")
    if any(token in candidate.field_name for token in ("weight", "decision", "reason", "adoption", "approval", "_id", "grade", "adjustment", "factor")):
        reasons.append("此欄位涉及專業判斷或關聯，需人工確認")
    if isinstance(value, (list, dict)):
        reasons.append("多筆明細需人工核對")
    peers = [item for item in candidates if item is not candidate and item.field_name == candidate.field_name]
    if any(compact(item.extracted_value) != compact(value) for item in peers):
        reasons.append("同名欄位的辨識值不一致")
    try:
        mapped_value(SimpleNamespace(form_code=candidate.form_code, field_name=candidate.field_name,
                                     confirmed_value=value))
    except AppError:
        reasons.append("欄位格式不符合表單要求")
    # Values that look like merged OCR rows are never silently treated as one fact.
    if isinstance(value, str) and ("\n" in value or "|" in value or "│" in value):
        reasons.append("可能混入其他欄位文字")
    return reasons


async def apply_unambiguous_fields(session, extraction, candidates, user):
    reasons_by_id = {}
    for candidate in candidates:
        reasons = uncertainty_reasons(candidate, candidates)
        if reasons:
            reasons_by_id[str(candidate.extracted_field_id)] = reasons
        else:
            await fill_review_form(session, candidate, user, automatic=True)
    extraction.extraction_metadata = {
        **(extraction.extraction_metadata or {}),
        "review_intake": {"policy": "review-auto-fill-v1",
                          "confidence_threshold": get_settings().review_auto_fill_confidence,
                          "uncertainties": reasons_by_id},
    }
    await session.flush()
