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
    if report.input_provenance is not None:
        provenance = report.input_provenance
        line(f"Input source {provenance.source}")
        if provenance.version_no is not None:
            line(f"Input version v{provenance.version_no}")
        if provenance.frozen_at is not None:
            line(f"Input frozen {provenance.frozen_at.isoformat()}")
        if provenance.fingerprint:
            line(f"Input fingerprint {provenance.fingerprint}")
        for document in provenance.documents:
            label = document.original_filename or str(document.document_id)
            line(
                f"Input document {label} | {document.document_type} | "
                f"v{document.version_no} | {document.checksum_sha256}"
            )
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
