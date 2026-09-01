from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.valuation.report_packages.complete_draft_pdf_builder import (
    build_six_page_draft_pdf,
    build_six_page_formal_pdf,
)


def _data() -> dict:
    benchmark_id = uuid4()
    return {
        "report_id": str(uuid4()),
        "version_no": 1,
        "context": {
            "case_id": str(uuid4()),
            "case_no": "QA-SIX-001",
            "case_title": "QA SIX PAGE REPORT",
            "valuation_base_date": "2026-08-26",
            "city_code": "QA-CITY",
            "district_code": "QA-DISTRICT",
            "land_use_type": "COMMERCIAL",
            "parcels": [],
            "benchmark_lands": [
                {
                    "benchmark_land_id": str(benchmark_id),
                    "parcel_id": str(uuid4()),
                    "benchmark_land_no": "QA-B1",
                    "price_zone_no": "QA-P1",
                }
            ],
        },
        "s01": {"observations": [], "notes": "", "site_opinion": ""},
        "f02_rf": {
            "benchmark_land_id": str(benchmark_id),
            "factor_rows": [],
            "other_influences": "",
            "notes": "",
        },
        "f02": {
            "benchmark_land_id": str(benchmark_id),
            "comparison_targets": [],
            "benchmark_notes": "",
            "notes": "",
        },
    }


def _one_page_pdf() -> bytes:
    output = BytesIO()
    target = canvas.Canvas(output, pagesize=A4)
    target.drawString(80, 500, "QA USER UPLOADED MAP")
    target.save()
    return output.getvalue()


def test_six_page_draft_uses_uploaded_map_and_missing_placeholders() -> None:
    result = build_six_page_draft_pdf(
        _data(),
        {
            "map-section-sketch": {
                "filename": "qa-map.pdf",
                "mime_type": "application/pdf",
                "content": _one_page_pdf(),
            }
        },
    )

    reader = PdfReader(BytesIO(result))
    assert len(reader.pages) == 6
    assert all(abs(float(page.mediabox.width) - A4[0]) < 1 for page in reader.pages)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "QA USER UPLOADED MAP" in text
    assert "MAP-01" in text
    assert "MAP-02" in text
    assert "MAP-03" in text
    assert text.count("尚未上傳正式附圖文件") == 2


def test_six_page_formal_requires_and_preserves_all_maps() -> None:
    document = {
        "filename": "qa-map.pdf",
        "mime_type": "application/pdf",
        "content": _one_page_pdf(),
    }
    result = build_six_page_formal_pdf(
        _data(),
        {
            "map-section-sketch": document,
            "map-zoning": document,
            "map-land-value-section": document,
        },
    )

    reader = PdfReader(BytesIO(result))
    assert len(reader.pages) == 6
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert text.count("QA USER UPLOADED MAP") == 3
    assert "DRAFT" not in text
