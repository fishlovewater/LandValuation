from app.review.pdf_reports import build_review_pdf
from app.review.reports import build_review_report
from app.review.tests.test_reports import report_input


def test_pdf_contains_case_run_risk_and_one_row_per_finding():
    report = build_review_report(report_input())

    content = build_review_pdf(report)

    assert content.startswith(b"%PDF")
    assert b"CASE-REPORT-001" in content
    assert b"Run 2" in content
    assert b"Risk HIGH" in content
    assert b"RATE-001" in content
    assert b"localhost" not in content
