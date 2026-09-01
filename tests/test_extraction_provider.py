import subprocess
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from openpyxl import Workbook

from app.core.config import Settings
from app.core.exceptions import AppError
from app.valuation.extraction.provider import (
    AutoPdfExtractionProvider,
    ExtractionResult,
    LocalOcrPdfExtractionProvider,
    LocalPdfExtractionProvider,
    TextractPdfExtractionProvider,
    XlsxExtractionProvider,
    build_document_extraction_provider,
)


def xlsx_bytes() -> bytes:
    output = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "案件資料"
    sheet.append(["估價基準日", "114年9月1日"])
    sheet.append(["比準地地號", "金美段489地號"])
    formula_sheet = workbook.create_sheet("試算")
    formula_sheet["A1"] = "合計"
    formula_sheet["B1"] = "=SUM(1,2)"
    workbook.save(output)
    workbook.close()
    return output.getvalue()


@pytest.mark.asyncio
async def test_xlsx_extracts_sheet_names_cells_formulas_and_candidates() -> None:
    result = await XlsxExtractionProvider().extract(xlsx_bytes())

    assert result.provider == "LOCAL_XLSX"
    assert result.page_count == 2
    assert "[工作表：案件資料]" in result.text
    assert "[A1] 估價基準日 | [B1] 114年9月1日" in result.text
    assert "[工作表：試算]" in result.text
    assert "[B1] =SUM(1,2)" in result.text
    assert result.candidates == ()


@pytest.mark.asyncio
async def test_xlsx_comparison_target_creates_structured_f01_candidates() -> None:
    output = BytesIO()
    workbook = Workbook()
    workbook.active.title = "02徵收土地清冊"
    workbook.active.append(["行政區", "金山區"])
    target = workbook.create_sheet("06比較標的資料")
    target.append(["欄位", "資料內容"])
    target.append(["實例編號", "1"])
    target.append(["交易日期", "114年5月28日"])
    target.append(["行政區", "新北市金山區"])
    target.append(["段", "溫泉段"])
    target.append(["地號", "218"])
    target.append(["面積", "111.85"])
    target.append(["土地正常單價", "184763"])
    workbook.save(output)
    workbook.close()

    result = await XlsxExtractionProvider().extract(output.getvalue())
    values = {item.field_name: item.value for item in result.candidates}

    assert all(item.form_code == "F01" for item in result.candidates)
    assert values["case_and_instance_refs"] == "1"
    assert values["transaction_date"] == "114年5月28日"
    assert values["property_registry_fields"] == "新北市金山區溫泉段218地號"
    assert values["land_area"] == "111.85"
    assert values["normal_land_unit_price_raw"] == "184763"


@pytest.mark.asyncio
async def test_invalid_xlsx_has_clear_error() -> None:
    with pytest.raises(AppError) as captured:
        await XlsxExtractionProvider().extract(b"not-an-xlsx")
    assert captured.value.code == "XLSX_SOURCE_INVALID"


class StubProvider:
    def __init__(self, result: ExtractionResult) -> None:
        self.provider_name = result.provider
        self.result = result
        self.calls = 0

    async def extract(self, content: bytes) -> ExtractionResult:
        self.calls += 1
        return self.result


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads = []
        self.deletes = []

    def put_object(self, **kwargs) -> None:
        self.uploads.append(kwargs)

    def delete_object(self, **kwargs) -> None:
        self.deletes.append(kwargs)


class FakeTextractClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.started_with = None
        self.get_calls = []

    def start_document_text_detection(self, **kwargs):
        self.started_with = kwargs
        return {"JobId": "job-1"}

    def get_document_text_detection(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.responses.pop(0)


def textract_settings() -> Settings:
    return Settings(
        _env_file=None,
        document_extraction_provider="auto",
        textract_region="ap-northeast-1",
        textract_s3_bucket="temporary-textract-bucket",
        textract_poll_interval_seconds=0.1,
        textract_timeout_seconds=10,
    )


def local_ocr_settings() -> Settings:
    return Settings(
        _env_file=None,
        document_extraction_provider="auto",
        local_ocr_languages="chi_tra+eng",
        local_ocr_dpi=300,
        local_ocr_psm=1,
        local_ocr_timeout_seconds=10,
        local_ocr_max_pages=5,
    )


def blank_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_blank_pdf_has_no_text_or_candidates() -> None:
    result = await LocalPdfExtractionProvider().extract(blank_pdf())

    assert result.page_count == 1
    assert result.text == ""
    assert result.candidates == ()
    assert result.provider == "LOCAL_PDF"


def test_benchmark_land_heading_is_not_mistaken_for_land_number() -> None:
    benchmark_pattern = dict(LocalPdfExtractionProvider._patterns)[
        "benchmark_land_no"
    ]

    assert benchmark_pattern.search("比準地或各比較標的") is None
    assert benchmark_pattern.search("比準地：宗地流水號") is None


def test_explicit_benchmark_land_number_label_can_be_extracted() -> None:
    benchmark_pattern = dict(LocalPdfExtractionProvider._patterns)[
        "benchmark_land_no"
    ]

    match = benchmark_pattern.search("比準地地號：已確認的文件值")

    assert match is not None
    assert match.group("value") == "已確認的文件值"


@pytest.mark.asyncio
async def test_auto_provider_keeps_local_result_when_pdf_has_text() -> None:
    local = StubProvider(
        ExtractionResult(
            text="文字型 PDF",
            page_count=1,
            candidates=(),
            provider="LOCAL_PDF",
        )
    )
    textract = StubProvider(
        ExtractionResult(
            text="不應使用",
            page_count=1,
            candidates=(),
            provider="TEXTRACT",
        )
    )
    local_ocr = StubProvider(
        ExtractionResult(
            text="不應使用 OCR",
            page_count=1,
            candidates=(),
            provider="LOCAL_OCR",
        )
    )

    result = await AutoPdfExtractionProvider(
        local_provider=local,
        local_ocr_provider=local_ocr,
        textract_provider=textract,
    ).extract(b"pdf")

    assert result.provider == "LOCAL_PDF"
    assert local.calls == 1
    assert local_ocr.calls == 0
    assert textract.calls == 0


@pytest.mark.asyncio
async def test_auto_provider_uses_textract_when_local_pdf_has_no_text() -> None:
    local = StubProvider(
        ExtractionResult(
            text="",
            page_count=1,
            candidates=(),
            provider="LOCAL_PDF",
        )
    )
    textract = StubProvider(
        ExtractionResult(
            text="掃描文件文字",
            page_count=1,
            candidates=(),
            provider="TEXTRACT",
        )
    )
    local_ocr = StubProvider(
        ExtractionResult(
            text="本機 OCR 備援",
            page_count=1,
            candidates=(),
            provider="LOCAL_OCR",
        )
    )

    result = await AutoPdfExtractionProvider(
        local_provider=local,
        local_ocr_provider=local_ocr,
        textract_provider=textract,
    ).extract(b"pdf")

    assert result.provider == "TEXTRACT"
    assert local.calls == 1
    assert local_ocr.calls == 0
    assert textract.calls == 1


@pytest.mark.asyncio
async def test_auto_provider_uses_local_ocr_without_textract_settings() -> None:
    local = StubProvider(
        ExtractionResult(
            text="",
            page_count=1,
            candidates=(),
            provider="LOCAL_PDF",
        )
    )
    local_ocr = StubProvider(
        ExtractionResult(
            text="本機 OCR 文字",
            page_count=1,
            candidates=(),
            provider="LOCAL_OCR",
        )
    )

    result = await AutoPdfExtractionProvider(
        local_provider=local,
        local_ocr_provider=local_ocr,
    ).extract(b"pdf")

    assert result.provider == "LOCAL_OCR"
    assert local.calls == 1
    assert local_ocr.calls == 1


def test_auto_factory_without_aws_settings_still_supports_local_pdf() -> None:
    settings = Settings(
        _env_file=None,
        document_extraction_provider="auto",
        textract_region=None,
        textract_s3_bucket=None,
    )

    provider = build_document_extraction_provider(settings)

    assert isinstance(provider, AutoPdfExtractionProvider)
    assert provider.textract_provider is None
    assert isinstance(provider.local_ocr_provider, LocalOcrPdfExtractionProvider)


@pytest.mark.asyncio
async def test_local_ocr_renders_pdf_parses_tsv_and_cleans_temp_files() -> None:
    calls = []
    rendered_image = None
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t98.0\t估價基準日",
            "5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t98.0\t：",
            "5\t1\t1\t1\t1\t3\t0\t0\t1\t1\t98.0\t115",
            "5\t1\t1\t1\t1\t4\t0\t0\t1\t1\t98.0\t年",
            "5\t1\t1\t1\t1\t5\t0\t0\t1\t1\t98.0\t8",
            "5\t1\t1\t1\t1\t6\t0\t0\t1\t1\t98.0\t月",
            "5\t1\t1\t1\t1\t7\t0\t0\t1\t1\t98.0\t25",
            "5\t1\t1\t1\t1\t8\t0\t0\t1\t1\t98.0\t日",
        ]
    )

    def runner(command: list[str], timeout: float):
        nonlocal rendered_image
        calls.append((command, timeout))
        if command[0] == "pdftoppm":
            rendered_image = Path(f"{command[-1]}-1.png")
            rendered_image.write_bytes(b"png")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, tsv, "")

    provider = LocalOcrPdfExtractionProvider(
        local_ocr_settings(),
        command_runner=runner,
        executable_finder=lambda name: name,
    )

    result = await provider.extract(blank_pdf())

    assert result.provider == "LOCAL_OCR"
    assert result.text == "估價基準日：115年8月25日"
    assert result.candidates[0].field_name == "valuation_base_date"
    assert result.candidates[0].value == "115年8月25日"
    assert result.candidates[0].confidence == Decimal("0.9800")
    assert calls[0][0][0] == "pdftoppm"
    assert calls[1][0][0] == "tesseract"
    assert calls[1][0][calls[1][0].index("--psm") + 1] == "1"
    assert rendered_image is not None
    assert not rendered_image.exists()


@pytest.mark.asyncio
async def test_local_ocr_reports_missing_system_dependencies() -> None:
    provider = LocalOcrPdfExtractionProvider(
        local_ocr_settings(),
        executable_finder=lambda _name: None,
    )

    with pytest.raises(AppError) as error:
        await provider.extract(blank_pdf())

    assert error.value.code == "LOCAL_OCR_DEPENDENCY_MISSING"


@pytest.mark.asyncio
async def test_textract_extracts_paginated_lines_and_cleans_temporary_s3() -> None:
    s3 = FakeS3Client()
    textract = FakeTextractClient(
        [
            {
                "JobStatus": "SUCCEEDED",
                "DocumentMetadata": {"Pages": 2},
                "Blocks": [
                    {
                        "BlockType": "LINE",
                        "Page": 1,
                        "Text": "估價基準日：115年8月25日",
                        "Confidence": 98.76,
                    }
                ],
                "NextToken": "page-2",
            },
            {
                "JobStatus": "SUCCEEDED",
                "DocumentMetadata": {"Pages": 2},
                "Blocks": [
                    {
                        "BlockType": "LINE",
                        "Page": 2,
                        "Text": "第二頁內容",
                        "Confidence": 97.0,
                    }
                ],
            },
        ]
    )
    provider = TextractPdfExtractionProvider(
        textract_settings(),
        s3_client=s3,
        textract_client=textract,
        sleep=lambda _seconds: None,
    )

    result = await provider.extract(b"pdf-data")

    assert result.provider == "TEXTRACT"
    assert result.page_count == 2
    assert result.text == "估價基準日：115年8月25日\n\n第二頁內容"
    assert result.candidates[0].field_name == "valuation_base_date"
    assert result.candidates[0].value == "115年8月25日"
    assert result.candidates[0].confidence == Decimal("0.9876")
    assert textract.get_calls[1]["NextToken"] == "page-2"
    assert len(s3.uploads) == 1
    assert len(s3.deletes) == 1
    assert s3.uploads[0]["Key"] == s3.deletes[0]["Key"]


@pytest.mark.asyncio
async def test_textract_partial_result_is_rejected_and_temporary_s3_is_cleaned() -> None:
    s3 = FakeS3Client()
    textract = FakeTextractClient(
        [{"JobStatus": "PARTIAL_SUCCESS", "DocumentMetadata": {"Pages": 2}}]
    )
    provider = TextractPdfExtractionProvider(
        textract_settings(),
        s3_client=s3,
        textract_client=textract,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(AppError) as error:
        await provider.extract(b"pdf-data")

    assert error.value.code == "TEXTRACT_PARTIAL_SUCCESS"
    assert len(s3.deletes) == 1
