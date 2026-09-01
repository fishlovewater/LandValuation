import pytest
from pypdf.errors import PdfReadError

from app.core.exceptions import AppError
from app.valuation.pdf_errors import build_pdf_safely


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (FileNotFoundError(), "PDF_TEMPLATE_MISSING", 500),
        (PermissionError(), "PDF_FILE_ACCESS_FAILED", 500),
        (OSError(), "PDF_FILE_IO_FAILED", 500),
        (KeyError("case_no"), "PDF_INPUT_INVALID", 422),
        (RuntimeError("六頁草稿 PDF 產生後頁數驗證失敗"), "PDF_OUTPUT_VALIDATION_FAILED", 500),
        (RuntimeError("正式六頁 PDF 缺少附圖：地籍圖"), "PDF_REQUIRED_DATA_MISSING", 422),
        (RuntimeError("unknown"), "PDF_GENERATION_FAILED", 500),
    ],
)
def test_pdf_failure_is_converted_to_specific_app_error(error, code, status):
    def fail():
        raise error

    with pytest.raises(AppError) as captured:
        build_pdf_safely(fail)
    assert captured.value.code == code
    assert captured.value.status_code == status


def test_invalid_uploaded_pdf_has_source_specific_error():
    def fail():
        raise PdfReadError("broken")

    with pytest.raises(AppError) as captured:
        build_pdf_safely(fail, source_is_user_upload=True)
    assert captured.value.code == "PDF_SOURCE_INVALID"
    assert captured.value.status_code == 422
