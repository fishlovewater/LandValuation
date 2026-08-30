"""Pure `.xlsx` renderer for an immutable Review risk report.

The workbook is rendered from a single `ReviewReport` snapshot. It never reads
current database rows, never contains macros, and never exposes bucket names,
object keys, or storage URLs. No formula computes an appraisal value.
"""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from app.review.reports import ReviewReport


TAIPEI = timezone(timedelta(hours=8))

SHEET_SUMMARY = "案件摘要"
SHEET_FINDINGS = "疑點與修正要求"
SHEET_RECHECK = "新版重檢結果"
SHEET_HISTORY = "審查歷程"

FINDING_HEADERS = [
    "疑點編號",
    "疑點類型",
    "嚴重度",
    "人工判定",
    "疑點說明",
    "原報告頁碼",
    "原報告內容",
    "原報告數值",
    "法規依據",
    "查核證據",
    "建議修正方向",
    "AI 輔助說明",
]

RECHECK_HEADERS = [
    "修正通知編號",
    "疑點編號",
    "嚴重度",
    "問題摘要",
    "要求修正內容",
    "重檢結果",
    "新版疑點編號",
    "重檢時間",
]

HISTORY_HEADERS = ["事件", "發生時間", "說明"]

# Legacy stored decision values are historical only; they are never created by
# the correction workflow and must be labelled as such.
LEGACY_DECISIONS = frozenset(
    {"ACCEPTED", "REJECTED", "PARTIALLY_ACCEPTED", "REQUIRES_SUPPLEMENT"}
)

TRIAGE_LABELS = {
    "CONFIRMED_ISSUE": "確認有問題",
    "DISMISSED_FALSE_POSITIVE": "排除誤判",
    "EXPERT_REVIEW": "轉專業覆核",
    "OPEN": "尚未判定",
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


def _local(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")


def _readable(entries: Any) -> str:
    """Render structured evidence/legal basis as readable field: value lines."""
    if not entries:
        return ""
    lines: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            lines.append(
                "；".join(
                    f"{key}：{value}"
                    for key, value in entry.items()
                    if value is not None and not _is_internal(key)
                )
            )
        else:
            lines.append(str(entry))
    return "\n".join(line for line in lines if line)


def _is_internal(key: str) -> bool:
    return key in {"bucket_name", "object_key", "bucket", "url"}


def _finding_status_label(status: str) -> str:
    if status in LEGACY_DECISIONS:
        return f"{status}（舊流程歷史決策）"
    return TRIAGE_LABELS.get(status, status)


def _autosize(sheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _write_headers(sheet, headers: list[str]) -> None:
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(headers))}{max(sheet.max_row, 1)}"
    )


def build_review_xlsx(report: ReviewReport) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)

    _build_summary(workbook.create_sheet(SHEET_SUMMARY), report)
    _build_findings(workbook.create_sheet(SHEET_FINDINGS), report)
    _build_recheck(workbook.create_sheet(SHEET_RECHECK), report)
    _build_history(workbook.create_sheet(SHEET_HISTORY), report)

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _build_summary(sheet, report: ReviewReport) -> None:
    urgency = report.urgency
    rows = [
        ("案件編號", report.case.case_no),
        ("案件名稱", report.case.case_title),
        ("行政區代碼", report.case.district_code),
        ("價格基準日", report.case.valuation_base_date),
        ("審查狀態", report.review_status),
        ("檢核批次", report.run.run_no),
        ("檢核狀態", report.run.run_status),
        ("檢核開始", _local(report.run.started_at)),
        ("檢核完成", _local(report.run.completed_at)),
        ("內容風險等級", report.risk_summary.overall_risk_level),
        ("高風險疑點數", report.risk_summary.high_count),
        ("中風險疑點數", report.risk_summary.medium_count),
        ("低風險疑點數", report.risk_summary.low_count),
        ("缺件數", report.missing_item_count),
        ("風險原因", "、".join(str(item) for item in report.risk_summary.risk_reasons)),
        ("期限緊急度", URGENCY_LABELS.get(urgency.level, urgency.level) if urgency else "未設定"),
        ("剩餘天數", urgency.remaining_days if urgency else ""),
        ("修正期限", _local(urgency.due_at) if urgency else ""),
        ("修正通知次數", len(report.correction_requests)),
    ]
    sheet.append(["項目", "內容"])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for label, value in rows:
        sheet.append([label, value if value is not None else ""])
    for row in sheet.iter_rows(min_row=2, min_col=1, max_col=1):
        for cell in row:
            cell.font = Font(bold=True)
    _autosize(sheet, [22, 60])


def _build_findings(sheet, report: ReviewReport) -> None:
    _write_headers(sheet, FINDING_HEADERS)
    requested_by_finding = {
        item.finding_id: item
        for request in report.correction_requests
        for item in request.items
    }
    for finding in report.findings:
        requested = requested_by_finding.get(finding.finding_id)
        page = ""
        for evidence in finding.source_evidence:
            if isinstance(evidence, dict) and evidence.get("page"):
                page = evidence["page"]
                break
        sheet.append(
            [
                finding.finding_code,
                finding.finding_type,
                finding.severity,
                _finding_status_label(finding.status),
                f"{finding.title}：{finding.description}",
                page,
                finding.reported_text or "",
                finding.reported_value or "",
                _readable(finding.legal_basis),
                _readable(finding.source_evidence),
                requested.requested_correction if requested else "",
                finding.ai_assessment.reasoning_summary or "",
            ]
        )
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    _autosize(sheet, [22, 20, 10, 20, 40, 12, 24, 14, 32, 40, 32, 40])
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(FINDING_HEADERS))}{max(sheet.max_row, 1)}"
    )


def _build_recheck(sheet, report: ReviewReport) -> None:
    _write_headers(sheet, RECHECK_HEADERS)
    for request in report.correction_requests:
        for item in request.items:
            sheet.append(
                [
                    request.request_no,
                    item.finding_code,
                    item.severity,
                    item.issue_summary,
                    item.requested_correction,
                    item.recheck_outcome,
                    str(item.resulting_finding_id) if item.resulting_finding_id else "",
                    _local(request.rechecked_at),
                ]
            )
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    _autosize(sheet, [16, 22, 10, 36, 36, 14, 30, 18])
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(RECHECK_HEADERS))}{max(sheet.max_row, 1)}"
    )


def _build_history(sheet, report: ReviewReport) -> None:
    _write_headers(sheet, HISTORY_HEADERS)
    for event in report.history:
        sheet.append(
            [event.event_type, _local(event.occurred_at), event.reason or ""]
        )
    for request in report.correction_requests:
        sheet.append(
            [
                f"第 {request.request_no} 次修正通知（{request.status}）",
                _local(request.sent_at),
                request.message,
            ]
        )
    for decision in report.case_decisions:
        label = decision.decision
        if label in LEGACY_DECISIONS:
            label = f"{label}（舊流程歷史決策）"
        sheet.append([label, _local(decision.decided_at), decision.reason or ""])
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    _autosize(sheet, [34, 18, 60])
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(HISTORY_HEADERS))}{max(sheet.max_row, 1)}"
    )
