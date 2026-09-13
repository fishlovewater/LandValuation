"""Business-facing PDF renderer for the immutable review report snapshot."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.review.report_presentation import (
    CORRECTION_STATUS_LABELS,
    DOCUMENT_TYPE_LABELS,
    EVENT_LABELS,
    FINDING_TYPE_LABELS,
    OUTCOME_LABELS,
    REVIEW_STATUS_LABELS,
    RISK_LABELS,
    SEVERITY_LABELS,
    SOURCE_LABELS,
    TRIAGE_LABELS,
    URGENCY_LABELS,
    decision_label,
    district_label,
    label,
    local_time,
    readable_entries,
    skipped_rule_text,
)
from app.review.reports import ReviewReport


FONT = "MicrosoftJhengHei"
FONT_PATHS = (
    Path("C:/Windows/Fonts/msjh.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
)
font_path = next((path for path in FONT_PATHS if path.exists()), None)
if font_path is not None:
    pdfmetrics.registerFont(TTFont(FONT, str(font_path), subfontIndex=0))
else:  # pragma: no cover - compatibility fallback outside the deployment image
    FONT = "MSung-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _text(value: object) -> str:
    return escape("" if value is None else str(value)).replace("\n", "<br/>")


def build_review_pdf(report: ReviewReport) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="土地估價審查報告",
        author="土地徵收補償市價查估系統",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ChineseTitle", parent=base["Title"], fontName=FONT,
            fontSize=19, leading=25, alignment=TA_CENTER,
            textColor=colors.HexColor("#173F67"), spaceAfter=9 * mm,
        ),
        "h1": ParagraphStyle(
            "ChineseH1", parent=base["Heading1"], fontName=FONT,
            fontSize=13, leading=18, textColor=colors.HexColor("#173F67"),
            spaceBefore=5 * mm, spaceAfter=2.5 * mm,
        ),
        "h2": ParagraphStyle(
            "ChineseH2", parent=base["Heading2"], fontName=FONT,
            fontSize=11, leading=16, textColor=colors.HexColor("#244F78"),
            spaceBefore=3 * mm, spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "ChineseBody", parent=base["BodyText"], fontName=FONT,
            fontSize=9.5, leading=15, textColor=colors.HexColor("#26384A"),
        ),
        "small": ParagraphStyle(
            "ChineseSmall", parent=base["BodyText"], fontName=FONT,
            fontSize=8.5, leading=13, textColor=colors.HexColor("#52677A"),
        ),
    }
    story: list = [Paragraph("土地估價審查報告", styles["title"])]

    def heading(value: str, level: int = 1) -> None:
        story.append(Paragraph(_text(value), styles[f"h{level}"]))

    def paragraph(value: object, *, small: bool = False) -> None:
        story.append(Paragraph(_text(value), styles["small" if small else "body"]))
        story.append(Spacer(1, 1.5 * mm))

    def key_values(rows: list[tuple[str, object]]) -> None:
        data = [
            [Paragraph(_text(key), styles["small"]), Paragraph(_text(value), styles["body"])]
            for key, value in rows
        ]
        table = Table(data, colWidths=[42 * mm, 117 * mm], splitByRow=0)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF4F9")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#173F67")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CAD8E5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 2 * mm)])

    heading("案件基本資料")
    key_values([
        ("案件編號", report.case.case_no),
        ("案件名稱", report.case.case_title),
        ("行政區", district_label(report.case.district_code)),
        ("價格基準日", report.case.valuation_base_date),
        ("審查狀態", label(REVIEW_STATUS_LABELS, report.review_status)),
        ("審查完成時間", local_time(report.run.completed_at)),
    ])

    heading("檢核覆蓋率")
    coverage = report.review_coverage
    if coverage is None:
        paragraph("此歷史批次未保存檢核覆蓋率資訊。")
    else:
        key_values([
            ("適用規則總數", coverage.total_rule_count),
            ("已執行規則", coverage.executed_rule_count),
            ("未執行規則", coverage.skipped_rule_count),
        ])
        if coverage.skipped_rules:
            paragraph("未執行不代表通過；以下項目因資料不足未進行自動檢核。")
            for item in coverage.skipped_rules:
                paragraph(f"• {skipped_rule_text(item)}", small=True)

    heading("審查文件")
    provenance = report.input_provenance
    if provenance is None:
        paragraph("此報告未提供審查文件資訊。")
    else:
        key_values([
            ("資料來源", label(SOURCE_LABELS, provenance.source)),
            ("輸入版本", f"v{provenance.version_no}" if provenance.version_no is not None else ""),
            ("資料確認時間", local_time(provenance.frozen_at)),
        ])
        for item in provenance.documents:
            paragraph(
                f"• {item.original_filename or '未命名文件'}／"
                f"{label(DOCUMENT_TYPE_LABELS, item.document_type)}／v{item.version_no}",
                small=True,
            )

    heading("風險與期限")
    paragraph("內容風險反映報告問題；期限緊急度僅反映距離修正期限的天數。", small=True)
    urgency = report.urgency
    key_values([
        ("內容風險等級", label(RISK_LABELS, report.risk_summary.overall_risk_level)),
        ("高風險疑點數", report.risk_summary.high_count),
        ("中風險疑點數", report.risk_summary.medium_count),
        ("低風險疑點數", report.risk_summary.low_count),
        ("缺件數", report.missing_item_count),
        ("期限緊急度", label(URGENCY_LABELS, urgency.level) if urgency else "未設定"),
        ("剩餘天數", urgency.remaining_days if urgency else ""),
        ("修正期限", local_time(urgency.due_at) if urgency else ""),
    ])

    heading("疑點與證據")
    if not report.findings:
        paragraph("本次檢核未發現疑點。")
    requested_by_finding = {
        item.finding_id: item
        for request in report.correction_requests
        for item in request.items
    }
    for finding in report.findings:
        heading(f"{finding.title}（{label(SEVERITY_LABELS, finding.severity)}風險）", 2)
        key_values([
            ("疑點類型", label(FINDING_TYPE_LABELS, finding.finding_type)),
            ("人工判定", TRIAGE_LABELS.get(finding.status, decision_label(finding.status))),
            ("疑點說明", finding.description),
            ("原報告內容", finding.reported_text or ""),
            ("原報告數值", finding.reported_value or ""),
        ])
        paragraph("法規依據")
        for line in readable_entries(finding.legal_basis) or ["（無）"]:
            paragraph(f"• {line}", small=True)
        paragraph("查核證據")
        for line in readable_entries(finding.source_evidence) or ["（無）"]:
            paragraph(f"• {line}", small=True)
        requested = requested_by_finding.get(finding.finding_id)
        if requested:
            paragraph(f"建議修正方向：{requested.requested_correction}")
        if finding.ai_assessment.reasoning_summary:
            paragraph(f"AI 輔助說明：{finding.ai_assessment.reasoning_summary}")

    heading("修正要求")
    if not report.correction_requests:
        paragraph("本批次未發出修正通知。")
    for request in report.correction_requests:
        heading(f"第 {request.request_no} 次修正通知（{label(CORRECTION_STATUS_LABELS, request.status)}）", 2)
        key_values([
            ("通知內容", request.message),
            ("修正期限", local_time(request.due_at)),
            ("送出時間", local_time(request.sent_at)),
            ("原版本", request.base_document_version),
            ("回件版本", request.response_document_version or ""),
            ("回件時間", local_time(request.resubmitted_at)),
        ])
        for item in request.items:
            paragraph(f"• {item.issue_summary}：{item.requested_correction}", small=True)

    heading("新版重檢結果")
    rechecked_items = [(request, item) for request in report.correction_requests for item in request.items]
    if not rechecked_items:
        paragraph("尚無新版重檢結果。")
    for request, item in rechecked_items:
        paragraph(
            f"• 第 {request.request_no} 次：{item.issue_summary}－"
            f"{label(OUTCOME_LABELS, item.recheck_outcome)}（{local_time(request.rechecked_at)}）",
            small=True,
        )

    heading("審查結論")
    paragraph(f"審查狀態：{label(REVIEW_STATUS_LABELS, report.review_status)}")
    if report.review_status != "REVIEW_COMPLETED":
        paragraph("智慧審查已完成；本報告仍可由審查人員進一步人工確認與補充決策。")
    if not report.case_decisions and not report.history:
        paragraph("本批次尚無案件層級審查紀錄。")
    for event in report.history:
        paragraph(f"• {label(EVENT_LABELS, event.event_type)}（{local_time(event.occurred_at)}）：{event.reason or ''}", small=True)
    for decision in report.case_decisions:
        paragraph(f"• {decision_label(decision.decision)}（{local_time(decision.decided_at)}）：{decision.reason or ''}", small=True)

    document.build(story)
    return output.getvalue()
