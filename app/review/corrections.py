"""Pure correction-request gates and immutable snapshot helpers.

Review confirms, reports, and rechecks problems. It never edits an appraisal
report or chooses a formal appraisal value, so nothing here reads or writes an
`after_value` or `selection_source`.
"""

from dataclasses import dataclass
from typing import Any

from app.core.exceptions import AppError


@dataclass(frozen=True)
class CorrectionGateSummary:
    has_completed_run: bool
    open_count: int
    confirmed_count: int
    expert_count: int
    has_active_request: bool


def validate_correction_send(summary: CorrectionGateSummary) -> None:
    blockers: list[str] = []
    if not summary.has_completed_run:
        blockers.append("最新一次智慧審查尚未完成")
    if summary.open_count:
        blockers.append(f"尚有 {summary.open_count} 項疑點未判定")
    if summary.expert_count:
        blockers.append(f"尚有 {summary.expert_count} 項專業覆核")
    if not summary.confirmed_count:
        blockers.append("沒有確認成立的疑點")
    if summary.has_active_request:
        blockers.append("已有未完成修正通知")
    if blockers:
        raise AppError(
            "CORRECTION_REQUEST_BLOCKED",
            "；".join(blockers),
            409,
            {"blockers": blockers},
        )


@dataclass(frozen=True)
class ReviewCompletionSummary:
    has_completed_run: bool
    open_missing_count: int
    open_finding_count: int
    confirmed_finding_count: int
    expert_finding_count: int
    active_request_count: int
    non_rechecked_request_count: int
    not_evaluated_item_count: int


def validate_review_completion(reason: str, summary: ReviewCompletionSummary) -> None:
    blockers: list[str] = []
    if not reason.strip():
        blockers.append("完成審查必須填寫理由")
    if not summary.has_completed_run:
        blockers.append("最新一次智慧審查尚未完成")
    if summary.open_missing_count:
        blockers.append(f"仍有 {summary.open_missing_count} 項缺件")
    if summary.open_finding_count:
        blockers.append(f"仍有 {summary.open_finding_count} 項疑點未判定")
    if summary.confirmed_finding_count:
        blockers.append(f"仍有 {summary.confirmed_finding_count} 項疑點待修正")
    if summary.expert_finding_count:
        blockers.append(f"仍有 {summary.expert_finding_count} 項專業覆核")
    if summary.active_request_count or summary.non_rechecked_request_count:
        blockers.append("仍有修正通知尚未完成新版重檢")
    if summary.not_evaluated_item_count:
        blockers.append("仍有修正項目無法判定重檢結果")
    if blockers:
        raise AppError(
            "REVIEW_COMPLETION_BLOCKED",
            "；".join(blockers),
            409,
            {"blockers": blockers},
        )


def build_correction_item_snapshot(finding: Any) -> dict:
    """Freeze a confirmed finding into an immutable correction item snapshot.

    Only server-loaded finding evidence is copied. The client never supplies
    finding ids, evidence, legal basis, or any formal value.
    """
    return {
        "finding_id": finding.finding_id,
        "finding_code": finding.finding_code,
        "finding_type": finding.finding_type,
        "severity": finding.severity,
        "document_id": getattr(finding, "document_id", None),
        "document_version": getattr(finding, "document_version", None),
        "page_number": getattr(finding, "page_number", None),
        "reported_text": getattr(finding, "reported_text", None),
        "reported_value": getattr(finding, "reported_value", None),
        "legal_basis_snapshot": list(getattr(finding, "legal_basis", []) or []),
        "source_evidence_snapshot": list(
            getattr(finding, "source_evidence", []) or []
        ),
        "issue_summary": _issue_summary(finding),
        "requested_correction": _requested_correction(finding),
    }


def _issue_summary(finding: Any) -> str:
    title = getattr(finding, "title", None)
    description = getattr(finding, "description", None)
    parts = [part for part in (title, description) if part]
    return "：".join(parts) if parts else "確認成立之疑點"


def _requested_correction(finding: Any) -> str:
    return "請依審查確認之疑點與法規依據更正原估價報告後檢附新版文件。"
