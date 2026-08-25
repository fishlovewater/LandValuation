from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.review.reports import ReviewReport


def build_review_pdf(report: ReviewReport) -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=0)
    width, height = A4
    y = height - 48

    def line(value: str, font="Helvetica", size=10):
        nonlocal y
        if y < 48:
            pdf.showPage()
            y = height - 48
        pdf.setFont(font, size)
        pdf.drawString(48, y, value)
        y -= size + 8

    line("Review Report", "Helvetica-Bold", 16)
    line(f"Case {report.case.case_no}")
    line(f"Run {report.run.run_no}")
    line(f"Risk {report.risk_summary.overall_risk_level}")
    line(
        "Counts HIGH={high} MEDIUM={medium} LOW={low} MISSING={missing}".format(
            high=report.risk_summary.high_count,
            medium=report.risk_summary.medium_count,
            low=report.risk_summary.low_count,
            missing=report.risk_summary.missing_item_count,
        )
    )
    y -= 8
    line("Findings", "Helvetica-Bold", 12)
    for finding in report.findings:
        line(
            f"{finding.finding_code} | {finding.severity} | {finding.status}"
        )
    pdf.save()
    return output.getvalue()
