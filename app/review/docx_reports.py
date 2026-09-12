"""Pure `.docx` renderer for an immutable Review risk report.

Body copy is business-facing Chinese. Structured evidence renders as readable
field/value rows, never raw JSON. Bucket names, object keys, and storage URLs
are never embedded.
"""

from datetime import datetime
from io import BytesIO
from typing import Any

from docx import Document

from app.review.reports import ReviewReport
from app.review.xlsx_reports import (
    LEGACY_DECISIONS,
    OUTCOME_LABELS,
    TRIAGE_LABELS,
    URGENCY_LABELS,
    _is_internal,
    _local,
)


def _readable_lines(entries: Any) -> list[str]:
    lines: list[str] = []
    if not entries:
        return lines
    for entry in entries:
        if isinstance(entry, dict):
            parts = [
                f"{key}：{value}"
                for key, value in entry.items()
                if value is not None and not _is_internal(key)
            ]
            if parts:
                lines.append("；".join(parts))
        else:
            lines.append(str(entry))
    return lines


def _key_value_table(document: Document, rows: list[tuple[str, Any]]) -> None:
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = str(label)
        cells[1].text = "" if value is None else str(value)
        for paragraph in cells[0].paragraphs:
            for run in paragraph.runs:
                run.bold = True


def build_review_docx(report: ReviewReport) -> bytes:
    document = Document()
    document.add_heading("土地估價審查風險報告", level=0)

    document.add_heading("案件基本資料", level=1)
    _key_value_table(
        document,
        [
            ("案件編號", report.case.case_no),
            ("案件名稱", report.case.case_title),
            ("行政區代碼", report.case.district_code),
            ("價格基準日", report.case.valuation_base_date),
            ("審查狀態", report.review_status),
            ("檢核批次", report.run.run_no),
            ("檢核完成時間", _local(report.run.completed_at)),
        ],
    )

    document.add_heading("檢核覆蓋率", level=1)
    coverage = report.review_coverage
    if coverage is None:
        document.add_paragraph("此歷史批次未保存檢核覆蓋率資訊。")
    else:
        _key_value_table(
            document,
            [
                ("適用規則總數", coverage.total_rule_count),
                ("已執行規則", coverage.executed_rule_count),
                ("未執行規則", coverage.skipped_rule_count),
            ],
        )
        if coverage.skipped_rules:
            document.add_paragraph("未執行不代表通過；以下項目因資料不足未進行自動檢核。")
            for item in coverage.skipped_rules:
                fields = "、".join(item.missing_field_codes) or "外部佐證資料"
                document.add_paragraph(
                    f"{item.rule_name}（{item.rule_code}）：{item.reason}；缺少：{fields}",
                    style="List Bullet",
                )

    provenance = report.input_provenance
    document.add_heading("審查輸入版本", level=1)
    if provenance is None:
        document.add_paragraph("此報告未提供審查輸入版本資訊。")
    else:
        source_label = {
            "PLATFORM": "平台送審",
            "EXTERNAL": "外部案件",
            "LEGACY": "舊版相容資料",
        }.get(provenance.source, provenance.source)
        _key_value_table(
            document,
            [
                ("資料來源", source_label),
                ("輸入版本", f"v{provenance.version_no}" if provenance.version_no is not None else ""),
                ("凍結時間", _local(provenance.frozen_at)),
                ("內容指紋", provenance.fingerprint or ""),
                ("快照格式", provenance.schema_version or ""),
            ],
        )
        if provenance.documents:
            document.add_paragraph("本次檢核使用文件", style="Intense Quote")
            for item in provenance.documents:
                filename = item.original_filename or str(item.document_id)
                document.add_paragraph(
                    f"{filename}／{item.document_type}／v{item.version_no}／"
                    f"SHA-256：{item.checksum_sha256}",
                    style="List Bullet",
                )

    document.add_heading("風險與期限", level=1)
    document.add_paragraph(
        "內容風險與期限緊急度為兩個獨立指標：風險反映報告內容問題，"
        "緊急度僅反映距離修正期限的天數。"
    )
    urgency = report.urgency
    _key_value_table(
        document,
        [
            ("內容風險等級", report.risk_summary.overall_risk_level),
            ("高風險疑點數", report.risk_summary.high_count),
            ("中風險疑點數", report.risk_summary.medium_count),
            ("低風險疑點數", report.risk_summary.low_count),
            ("缺件數", report.missing_item_count),
            (
                "期限緊急度",
                URGENCY_LABELS.get(urgency.level, urgency.level)
                if urgency
                else "未設定",
            ),
            ("剩餘天數", urgency.remaining_days if urgency else ""),
            ("修正期限", _local(urgency.due_at) if urgency else ""),
        ],
    )

    document.add_heading("疑點與證據", level=1)
    if not report.findings:
        document.add_paragraph("本次檢核未發現疑點。")
    for finding in report.findings:
        document.add_heading(
            f"{finding.finding_code}（{finding.severity}）", level=2
        )
        status = finding.status
        status_label = (
            f"{status}（舊流程歷史決策）"
            if status in LEGACY_DECISIONS
            else TRIAGE_LABELS.get(status, status)
        )
        _key_value_table(
            document,
            [
                ("疑點類型", finding.finding_type),
                ("人工判定", status_label),
                ("疑點說明", f"{finding.title}：{finding.description}"),
                ("原報告內容", finding.reported_text or ""),
                ("原報告數值", finding.reported_value or ""),
            ],
        )
        document.add_paragraph("法規依據", style="Intense Quote")
        for line in _readable_lines(finding.legal_basis) or ["（無）"]:
            document.add_paragraph(line, style="List Bullet")
        document.add_paragraph("查核證據", style="Intense Quote")
        for line in _readable_lines(finding.source_evidence) or ["（無）"]:
            document.add_paragraph(line, style="List Bullet")
        if finding.ai_assessment.reasoning_summary:
            document.add_paragraph("AI 輔助說明", style="Intense Quote")
            document.add_paragraph(finding.ai_assessment.reasoning_summary)
        for decision in finding.decisions:
            label = decision.decision
            if label in LEGACY_DECISIONS:
                label = f"{label}（舊流程歷史決策）"
            document.add_paragraph(
                f"人工紀錄：{label}／{decision.reason}"
                f"（{_local(decision.decided_at)}）"
            )

    document.add_heading("修正要求", level=1)
    if not report.correction_requests:
        document.add_paragraph("本批次未發出修正通知。")
    for request in report.correction_requests:
        document.add_heading(
            f"第 {request.request_no} 次修正通知（{request.status}）", level=2
        )
        _key_value_table(
            document,
            [
                ("通知內容", request.message),
                ("修正期限", _local(request.due_at)),
                ("送出時間", _local(request.sent_at)),
                ("原版本", request.base_document_version),
                ("回件版本", request.response_document_version or ""),
                ("回件時間", _local(request.resubmitted_at)),
            ],
        )
        for item in request.items:
            document.add_paragraph(
                f"{item.finding_code}：{item.issue_summary}", style="List Number"
            )
            document.add_paragraph(
                f"要求修正內容：{item.requested_correction}", style="List Bullet"
            )

    document.add_heading("新版重檢結果", level=1)
    rechecked_items = [
        (request, item)
        for request in report.correction_requests
        for item in request.items
    ]
    if not rechecked_items:
        document.add_paragraph("尚無新版重檢結果。")
    for request, item in rechecked_items:
        outcome = OUTCOME_LABELS.get(item.recheck_outcome, item.recheck_outcome)
        document.add_paragraph(
            f"第 {request.request_no} 次／{item.finding_code}：{outcome}"
            f"（{_local(request.rechecked_at)}）",
            style="List Bullet",
        )

    document.add_heading("審查結論", level=1)
    document.add_paragraph(f"審查狀態：{report.review_status}")
    if report.review_status != "REVIEW_COMPLETED":
        document.add_paragraph("智慧審查已完成；本報告仍可由審查人員進一步人工確認與補充決策。")
    if not report.case_decisions and not report.history:
        document.add_paragraph("本批次尚無案件層級審查紀錄。")
    for event in report.history:
        document.add_paragraph(
            f"{event.event_type}（{_local(event.occurred_at)}）：{event.reason or ''}",
            style="List Bullet",
        )
    for decision in report.case_decisions:
        label = decision.decision
        if label in LEGACY_DECISIONS:
            label = f"{label}（舊流程歷史決策）"
        document.add_paragraph(
            f"{label}（{_local(decision.decided_at)}）：{decision.reason or ''}",
            style="List Bullet",
        )

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()
