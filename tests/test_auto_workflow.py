import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import UploadFile
from pydantic import ValidationError

from app.valuation.automation.schemas import AutomatedIntakeManifest
from app.valuation.automation.service import (
    AUTO_EXTRACT_MIME_TYPES,
    F04_AUTO_APPLY_FIELDS,
    AutomatedWorkflowService,
    classify_document,
)
import app.valuation.automation.service as automation_service
from app.valuation.documents.schemas import DocumentCategory
from app.valuation.extraction.field_catalog import F04_FIELD_ANALYSIS_FIELDS
from app.valuation.requirements import FORM_REQUIREMENTS
from app.main import app


def manifest_payload() -> dict:
    return {
        "case": {
            "case_no": "AUTO-TEST-001",
            "case_title": "自動流程測試案件",
            "case_type": "土地徵收補償市價查估",
            "valuation_base_date": "2026-08-27",
            "city_code": "65000000",
            "district_code": "65000010",
            "land_use_type": "COMMERCIAL",
        },
        "parcels": [
            {
                "district_code": "65000010",
                "section_name": "測試段",
                "subsection_name": "",
                "land_no": "1",
                "area_sqm": "100.0000",
            }
        ],
        "benchmark_lands": [
            {
                "parcel_index": 0,
                "benchmark_land_no": "BM-001",
                "price_zone_no": "Z-001",
            }
        ],
    }


def test_intake_manifest_collects_case_parcel_and_benchmark_once() -> None:
    manifest = AutomatedIntakeManifest.model_validate_json(
        json.dumps(manifest_payload(), ensure_ascii=False)
    )

    assert manifest.case.district_code == "65000010"
    assert manifest.parcels[0].land_no == "1"
    assert manifest.benchmark_lands[0].parcel_index == 0


def test_intake_manifest_rejects_non_new_taipei_or_cross_district_parcel() -> None:
    invalid = manifest_payload()
    invalid["case"]["district_code"] = "123"
    with pytest.raises(ValidationError):
        AutomatedIntakeManifest.model_validate(invalid)

    invalid = manifest_payload()
    invalid["parcels"][0]["district_code"] = "65000270"
    with pytest.raises(ValidationError):
        AutomatedIntakeManifest.model_validate(invalid)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("土地登記謄本.pdf", DocumentCategory.LAND_REGISTER),
        ("地籍圖.pdf", DocumentCategory.CADASTRAL_MAP),
        ("地價區段略圖.png", DocumentCategory.MAP_SECTION_SKETCH),
        ("地價使用分區圖.pdf", DocumentCategory.MAP_ZONING),
        ("地價區段圖.jpg", DocumentCategory.MAP_LAND_VALUE_SECTION),
        ("未知資料.pdf", DocumentCategory.ORIGINAL),
    ],
)
def test_filename_classification_is_conservative(filename, expected) -> None:
    category, source = classify_document(filename, "application/pdf")

    assert category == expected
    assert source in {"FILENAME_RULE", "SAFE_FALLBACK"}


def test_manifest_override_is_explicit_and_invalid_values_are_rejected() -> None:
    category, source = classify_document(
        "無法辨識.pdf",
        "application/pdf",
        "land-register",
    )
    assert category == DocumentCategory.LAND_REGISTER
    assert source == "MANIFEST_OVERRIDE"

    with pytest.raises(Exception):
        classify_document("無法辨識.pdf", "application/pdf", "invented-category")


def test_simplified_workflow_is_exposed_as_three_swagger_operations() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/valuation/auto-workflows/intake" in paths
    assert "/api/v1/valuation/cases/{case_id}/auto-workflow/review" in paths
    assert "/api/v1/valuation/cases/{case_id}/auto-workflow/confirm" in paths
    intake = paths["/api/v1/valuation/auto-workflows/intake"]["post"]
    assert "multipart/form-data" in intake["requestBody"]["content"]
    body_schema = intake["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_name = body_schema["$ref"].split("/")[-1]
    files_schema = app.openapi()["components"]["schemas"][body_name]["properties"][
        "files"
    ]
    assert files_schema["items"] == {"type": "string", "format": "binary"}


def test_automated_intake_extracts_pdf_and_xlsx_sources() -> None:
    assert "application/pdf" in AUTO_EXTRACT_MIME_TYPES
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in AUTO_EXTRACT_MIME_TYPES
    )


def test_intake_file_checksum_is_repeatable_and_rewinds_upload() -> None:
    upload = UploadFile(filename="duplicate.pdf", file=BytesIO(b"same source bytes"))

    checksum = AutomatedWorkflowService._source_file_checksum(upload)

    assert checksum == AutomatedWorkflowService._source_file_checksum(upload)
    assert upload.file.read() == b"same source bytes"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["bedrock", "ollama"])
async def test_supported_ai_field_analysis_scans_every_official_form(
    monkeypatch, provider_name
) -> None:
    analyzed_form_codes: list[str] = []

    class FakeFieldAnalysisService:
        def __init__(self, session) -> None:
            assert session is None

        async def analyze(self, _case_id, _document_id, payload, _user) -> None:
            analyzed_form_codes.append(payload.form_code.value)

    monkeypatch.setattr(
        automation_service,
        "get_settings",
        lambda: SimpleNamespace(ai_provider=provider_name),
    )
    monkeypatch.setattr(
        automation_service,
        "FieldAnalysisService",
        FakeFieldAnalysisService,
    )
    service = object.__new__(AutomatedWorkflowService)
    service.session = None
    warnings: list[str] = []

    await service._optional_ai_analysis(
        uuid4(),
        uuid4(),
        False,
        SimpleNamespace(),
        warnings,
    )

    assert analyzed_form_codes == ["F01", "F02", "F02-RF", "F03", "F04", "S01"]
    assert warnings == []


def test_missing_items_are_based_on_actual_requirements_not_report_presence() -> None:
    complete = AutomatedWorkflowService._workflow_missing_items(
        pending=0,
        has_parcels=True,
        has_benchmarks=True,
        has_report=True,
        land_use_type="COMMERCIAL",
        readiness_blockers=[],
    )
    assert complete == []

    missing = AutomatedWorkflowService._workflow_missing_items(
        pending=2,
        has_parcels=False,
        has_benchmarks=False,
        has_report=False,
        land_use_type="COMMERCIAL",
        readiness_blockers=["FORMAL_RULE_VERSION_MISSING"],
    )
    assert missing == [
        "AI_CANDIDATES_REQUIRE_CONFIRMATION",
        "PARCELS_REQUIRED",
        "BENCHMARK_LAND_REQUIRED",
        "COMMERCIAL_REPORT_REQUIRED",
        "FORMAL_RULE_VERSION_MISSING",
    ]

@pytest.mark.parametrize(
    ("field_name", "raw_value", "expected"),
    [
        ("transaction_total_price", "45,000,000", Decimal("45000000")),
        ("land_area_sqm", "123.4500", Decimal("123.4500")),
        ("transaction_date", "103/05/26", date(2014, 5, 26)),
        ("transaction_no", "TP-001", "TP-001"),
    ],
)
def test_confirmed_codex_f01_values_are_normalized_only_when_unambiguous(
    field_name, raw_value, expected
) -> None:
    assert (
        AutomatedWorkflowService._normalized_confirmed_f01_value(
            field_name, raw_value
        )
        == expected
    )

def test_guidance_requirements_match_f01_calculation_inputs() -> None:
    assert FORM_REQUIREMENTS["F01"].required_fields == (
        "transaction_no",
        "transaction_date",
        "transaction_total_price",
        "location",
        "land_area_sqm",
    )
    assert "valuation_base_date" in FORM_REQUIREMENTS["F03"].required_fields
    assert FORM_REQUIREMENTS["S01"].required_fields == (
        "administrative_area",
        "valuation_base_date",
        "price_zone_no",
        "zone_boundary_description",
        "urban_plan_scope",
        "land_use_zone_category",
        "main_road_name",
        "main_road_width_m",
        "survey_date",
    )


def test_f04_ai_catalog_only_auto_applies_safe_non_calculated_fields() -> None:
    assert "valuation_base_date" in F04_FIELD_ANALYSIS_FIELDS
    assert "price_zone_no" in F04_FIELD_ANALYSIS_FIELDS
    assert "case_note" in F04_FIELD_ANALYSIS_FIELDS

    assert "valuation_base_date" in F04_AUTO_APPLY_FIELDS
    assert "price_zone_no" in F04_AUTO_APPLY_FIELDS
    assert "case_note" in F04_AUTO_APPLY_FIELDS

    for protected in (
        "benchmark_valuation_id",
        "benchmark_land_price",
        "rule_version_id",
        "parcel_rows",
        "parcel_adjustment_rate",
        "parcel_unit_price",
        "parcel_total_value",
        "parcel_market_price",
        "trial_price_raw",
        "total_adjustment_rate_raw",
    ):
        assert protected not in F04_AUTO_APPLY_FIELDS


@pytest.mark.asyncio
async def test_confirmed_f04_evidence_creates_draft_and_defers_calculated_fields(
    monkeypatch,
) -> None:
    case_id = uuid4()
    form_id = uuid4()
    user = SimpleNamespace(user_id=uuid4())
    candidates = [
        SimpleNamespace(field_name="valuation_base_date", confirmed_value="115/09/01"),
        SimpleNamespace(field_name="price_zone_no", confirmed_value="Z-001"),
        SimpleNamespace(field_name="case_note", confirmed_value="人工確認備註"),
        SimpleNamespace(field_name="parcel_market_price", confirmed_value="999999"),
    ]

    class ScalarResult:
        def all(self):
            return candidates

    class FakeSession:
        async def scalars(self, _statement):
            return ScalarResult()

    class FakeValuation:
        def __init__(self):
            self.created_payload = None

        async def list_forms(self, _case_id, _user):
            return []

        async def get_case(self, _case_id, _user):
            return SimpleNamespace(valuation_base_date=date(2026, 9, 1))

        async def create_form(self, _case_id, payload, _user):
            self.created_payload = payload
            return SimpleNamespace(
                form_instance_id=form_id,
                form_code="F04",
                version_no=1,
            )

    class FakeExtractionRepository:
        def __init__(self):
            self.applied = []

        async def apply_candidate(self, candidate, applied_form_id):
            self.applied.append((candidate.field_name, applied_form_id))

    updates: list[dict] = []

    class FakeF01F04Service:
        def __init__(self, _session):
            pass

        async def update(self, _case_id, _form_id, code, payload, _user):
            assert code == "F04"
            updates.append(payload.model_dump(exclude_unset=True))

    monkeypatch.setattr(automation_service, "F01F04Service", FakeF01F04Service)
    service = object.__new__(AutomatedWorkflowService)
    service.session = FakeSession()
    service.valuation = FakeValuation()
    service.extraction_repository = FakeExtractionRepository()
    warnings: list[str] = []

    result = await service._apply_confirmed_f04_candidates(case_id, user, warnings)

    assert result == form_id
    assert service.valuation.created_payload.form_code.value == "F04"
    assert service.valuation.created_payload.prepared_date == date(2026, 9, 1)
    assert {next(iter(item)) for item in updates} == {
        "valuation_base_date",
        "price_zone_no",
        "notes",
    }
    assert {item["valuation_base_date"] for item in updates if "valuation_base_date" in item} == {
        date(2026, 9, 1)
    }
    assert service.extraction_repository.applied == [
        ("valuation_base_date", form_id),
        ("price_zone_no", form_id),
        ("case_note", form_id),
    ]
    assert "F04_CONFIRMED_CANDIDATES_AWAIT_FORMAL_DEPENDENCIES" in warnings
