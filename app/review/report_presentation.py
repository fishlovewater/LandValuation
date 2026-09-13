"""Business-facing labels and sanitizers shared by review report exports.

The immutable report snapshot intentionally keeps technical provenance for
auditing.  Export renderers must use this module so reviewer-facing files do
not expose implementation identifiers, hashes, schemas, or raw enum values.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.valuation.rule_packs.coverage import NEW_TAIPEI_DISTRICTS


TAIPEI = timezone(timedelta(hours=8))

REVIEW_STATUS_LABELS = {
    "PENDING_MATERIALS": "待補資料",
    "PREPROCESSING": "資料整理中",
    "ANALYZING": "智慧審查中",
    "REVIEW_REQUIRED": "待人工判定",
    "EXPERT_REVIEW": "專業覆核中",
    "RETURNED_FOR_REVISION": "退回修正",
    "SUPPLEMENT_REQUIRED": "待補正",
    "APPROVED": "審查通過",
    "REVIEW_COMPLETED": "審查完成",
}

RUN_STATUS_LABELS = {
    "PENDING": "等待執行",
    "RUNNING": "執行中",
    "COMPLETED": "已完成",
    "FAILED": "執行失敗",
}

RISK_LABELS = {"HIGH": "高", "MEDIUM": "中", "LOW": "低", "NONE": "無"}
SEVERITY_LABELS = {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}

FINDING_TYPE_LABELS = {
    "RATE_OUT_OF_RANGE": "調整率異常",
    "GRADE_MISMATCH": "等級不一致",
    "MISSING_FIELD": "資料缺漏",
    "MISSING_DOCUMENT": "文件缺漏",
    "INCONSISTENT_VALUE": "資料不一致",
}

SOURCE_LABELS = {
    "PLATFORM": "平台送審",
    "EXTERNAL": "外部案件",
    "LEGACY": "舊版案件資料",
}

DOCUMENT_TYPE_LABELS = {
    "original": "原始估價報告",
    "generated-report": "估價報告",
    "complete-valuation-report": "完整估價報告",
    "review-report": "審查報告",
    "correction-request": "修正通知",
}

TRIAGE_LABELS = {
    "CONFIRMED_ISSUE": "確認有問題",
    "DISMISSED_FALSE_POSITIVE": "排除誤判",
    "EXPERT_REVIEW": "轉專業覆核",
    "OPEN": "尚未判定",
}

LEGACY_DECISIONS = frozenset(
    {"ACCEPTED", "REJECTED", "PARTIALLY_ACCEPTED", "REQUIRES_SUPPLEMENT"}
)

DECISION_LABELS = {
    "ACCEPTED": "接受",
    "REJECTED": "不接受",
    "PARTIALLY_ACCEPTED": "部分接受",
    "REQUIRES_SUPPLEMENT": "要求補充",
    "RETURNED_FOR_REVISION": "退回修正",
    "APPROVED": "審查通過",
    "REVIEW_COMPLETED": "完成審查",
}

URGENCY_LABELS = {
    "OVERDUE": "已逾期",
    "URGENT": "緊急",
    "DUE_SOON": "即將到期",
    "NORMAL": "正常",
    "NOT_SET": "未設定",
}

OUTCOME_LABELS = {
    "PENDING": "尚未重檢",
    "RESOLVED": "已解決",
    "STILL_PRESENT": "仍存在",
    "NOT_EVALUATED": "無法判定",
}

CORRECTION_STATUS_LABELS = {
    "DRAFT": "草稿",
    "SENT": "已送出",
    "RESUBMITTED": "已回件",
    "RECHECKING": "重檢中",
    "RECHECKED": "已重檢",
}

EVENT_LABELS = {
    "CORRECTION_SENT": "已送出修正通知",
    "CORRECTION_RESUBMITTED": "已收到修正回件",
    "CORRECTION_RECHECKED": "已完成新版重檢",
    "REVIEW_COMPLETED": "審查完成",
}

FIELD_LABELS = {
    "article": "條文",
    "law_name": "法規名稱",
    "title": "名稱",
    "document_title": "文件名稱",
    "source_title": "來源名稱",
    "name": "名稱",
    "section": "節次",
    "clause": "款項",
    "page": "頁次",
    "page_number": "頁次",
    "excerpt": "內容摘錄",
    "text": "內容",
    "content": "內容",
    "filename": "文件名稱",
    "original_filename": "文件名稱",
    "verification_status": "查核狀態",
}

VALUE_LABELS = {"VERIFIED": "已查核", "UNVERIFIED": "尚未查核"}

INTERNAL_KEYS = frozenset(
    {
        "bucket_name",
        "object_key",
        "bucket",
        "url",
        "source_id",
        "extracted_field_id",
        "document_id",
        "document_group_id",
        "document_version",
        "field_path",
        "bounding_box",
        "checksum_sha256",
        "sha256",
        "fingerprint",
        "schema_version",
        "submission_id",
        "external_input_snapshot_id",
        "provider",
        "model_id",
        "prompt_version",
    }
)


def local_time(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")


def district_label(code: str | None) -> str:
    if not code:
        return ""
    return NEW_TAIPEI_DISTRICTS.get(code, code)


def label(mapping: dict[str, str], value: str | None) -> str:
    if not value:
        return ""
    return mapping.get(value, value.replace("_", " "))


def decision_label(value: str) -> str:
    rendered = label(DECISION_LABELS, value)
    return f"{rendered}（舊流程歷史決策）" if value in LEGACY_DECISIONS else rendered


def readable_entries(entries: Any) -> list[str]:
    """Return human-readable evidence lines while omitting internal metadata."""
    if not entries:
        return []
    lines: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            parts: list[str] = []
            for key, value in entry.items():
                if value is None or key in INTERNAL_KEYS:
                    continue
                display_key = FIELD_LABELS.get(key)
                if display_key is None:
                    # Unknown snake_case keys are implementation details.  A
                    # readable scalar value may still be useful to reviewers.
                    if "_" in key:
                        continue
                    display_key = key
                rendered = VALUE_LABELS.get(str(value), str(value))
                parts.append(f"{display_key}：{rendered}")
            if parts:
                lines.append("；".join(parts))
        else:
            lines.append(str(entry))
    return lines


def readable_text(entries: Any) -> str:
    return "\n".join(readable_entries(entries))


def skipped_rule_text(item: Any) -> str:
    """Explain an unexecuted check without rule or missing-field codes."""
    return f"{item.rule_name}：{item.reason}"

