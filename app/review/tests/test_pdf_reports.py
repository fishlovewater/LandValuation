from io import BytesIO

from pypdf import PdfReader

from app.review.pdf_reports import build_review_pdf
from app.review.reports import build_review_report
from app.review.tests.test_reports import report_input


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)


def test_pdf_matches_business_facing_report_sections():
    report = build_review_report(report_input())

    content = build_review_pdf(report)

    assert content.startswith(b"%PDF")
    text = _pdf_text(content)
    assert "土地估價審查報告" in text
    assert "CASE-REPORT-001" in text
    assert "外部案件" in text
    assert "external-report-v2.pdf" in text
    assert "高風險" in text
    assert "土地登記資料交叉檢核" in text
    assert "條文：第10條" in text
    for section in ["案件基本資料", "檢核覆蓋率", "審查文件", "風險與期限", "疑點與證據", "修正要求", "新版重檢結果", "審查結論"]:
        assert section in text


def test_pdf_hides_engineering_metadata():
    text = _pdf_text(build_review_pdf(build_review_report(report_input())))
    for hidden in [
        "SHA-256", "內容指紋", "快照格式", "平台送審識別碼",
        "LAND_REGISTER_CROSSCHECK", "LAND_REGISTER_AREA", "RATE-001",
        "RATE_OUT_OF_RANGE", "PARTIALLY_ACCEPTED", "REVIEW_REQUIRED",
        "source_id", "document_id", "field_path", "a" * 64, "b" * 64,
    ]:
        assert hidden not in text
