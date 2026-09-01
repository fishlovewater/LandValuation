from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from app.valuation.report_packages.draft_pdf_builder import (
    build_three_page_draft_pdf,
    build_three_page_source_preserved_draft_pdf,
)
from app.valuation.report_packages.page_service import (
    looks_like_filled_three_page_report,
)


def test_three_page_draft_pdf_uses_supplied_a4_template() -> None:
    benchmark_id = uuid4()
    report_id = uuid4()
    pdf_bytes = build_three_page_draft_pdf(
        {
            "report_id": str(report_id),
            "version_no": 1,
            "context": {
                "case_id": str(uuid4()),
                "case_no": "QA-CASE-001",
                "case_title": "QA REPORT",
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
            "s01": {
                "district_name": "QA DISTRICT",
                "district_boundary": "QA BOUNDARY",
                "survey_date": "2026-08-26",
                "urban_plan_status": "QA PLAN",
                "land_use_zone": "QA ZONE",
                "building_coverage_rate": "70",
                "floor_area_ratio": "240",
                "prohibited_building": None,
                "restricted_building": None,
                "main_road_name": "QA ROAD",
                "main_road_width_m": "18",
                "average_road_width_m": "12",
                "observations": [],
                "notes": "",
                "site_opinion": "",
                "handler_name": "QA HANDLER",
                "section_head_name": None,
                "director_name": None,
                "appraiser_name": "QA APPRAISER",
            },
            "f02_rf": {
                "benchmark_land_id": str(benchmark_id),
                "comparison_analysis_id": None,
                "rule_version_id": None,
                "factor_rows": [],
                "other_influences": "",
                "notes": "",
                "appraiser_name": "QA APPRAISER",
            },
            "f02": {
                "benchmark_land_id": str(benchmark_id),
                "comparison_analysis_id": None,
                "comparison_targets": [],
                "benchmark_notes": "",
                "notes": "",
                "handler_name": "QA HANDLER",
                "section_head_name": None,
                "director_name": None,
                "appraiser_name": "QA APPRAISER",
            },
        }
    )

    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 3
    assert all(abs(float(page.mediabox.width) - 595.32) < 1 for page in reader.pages)
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "QA-CASE-001" in extracted
    assert "QA-P1" in extracted


def test_source_preserved_draft_keeps_only_first_three_filled_pages() -> None:
    source_buffer = BytesIO()
    target = canvas.Canvas(source_buffer, pagesize=A4)
    for page_number in range(1, 7):
        if page_number == 3:
            target.setPageSize(landscape(A4))
        elif page_number == 4:
            target.setPageSize(A4)
        target.drawString(72, 720, f"SOURCE-PAGE-{page_number}")
        target.showPage()
    target.save()

    result = build_three_page_source_preserved_draft_pdf(source_buffer.getvalue())

    reader = PdfReader(BytesIO(result))
    assert len(reader.pages) == 3
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "SOURCE-PAGE-1" in extracted
    assert "SOURCE-PAGE-3" in extracted
    assert "SOURCE-PAGE-4" not in extracted


def test_filled_report_detection_requires_all_three_known_headings() -> None:
    complete = "表1  地價區段勘查表\n表5－2 區域因素\n表4\n比較法調查估價表"
    assert looks_like_filled_three_page_report(complete)
    assert not looks_like_filled_three_page_report("表1 地價區段勘查表\n表5-2")
