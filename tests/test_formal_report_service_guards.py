from datetime import UTC, date, datetime
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
import app.valuation.report_packages.formal_service as formal_service_module
from app.valuation.report_packages.formal_service import (
    FormalReportService,
    _optional_official_template_assets,
)
from app.valuation.rule_packs.coverage import NEW_TAIPEI_CITYWIDE_SCOPE


def _case(**overrides):
    values = {
        "valuation_base_date": date(2026, 8, 28),
        "district_code": "65000010",
        "land_use_type": "COMMERCIAL",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rule(**overrides):
    values = {
        "status": "PUBLISHED",
        "import_status": "VERIFIED",
        "verified_at": datetime.now(UTC),
        "source_document_id": uuid4(),
        "source_checksum_sha256": "a" * 64,
        "formula_code": "NTPC_COMPARISON_V1",
        "rounding_code": "NTPC_LAND_PRICE_V1",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "land_use_types": ["COMMERCIAL"],
        "district_scope": dict(NEW_TAIPEI_CITYWIDE_SCOPE),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _StorageResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.closed = False
        self.released = False

    def read(self):
        return self.content

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


@pytest.mark.asyncio
async def test_optional_official_template_assets_are_disabled_without_object_keys(monkeypatch):
    monkeypatch.setattr(
        formal_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            official_report_blank_template_object_key=None,
            official_report_blank_template_manifest_object_key=None,
        ),
    )

    class _Storage:
        async def download(self, _object_key):
            raise AssertionError("disabled official template must not access MinIO")

    assert await _optional_official_template_assets(_Storage()) == (None, None)


@pytest.mark.asyncio
async def test_optional_official_template_assets_load_pdf_and_manifest_from_minio(monkeypatch):
    template = b"%PDF-official-template"
    manifest = {"manifest_version": "official-template-overlay-v1"}
    responses = {
        "templates/official/report.pdf": _StorageResponse(template),
        "templates/official/report.manifest.json": _StorageResponse(
            json.dumps(manifest).encode("utf-8")
        ),
    }
    monkeypatch.setattr(
        formal_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            official_report_blank_template_object_key="templates/official/report.pdf",
            official_report_blank_template_manifest_object_key=(
                "templates/official/report.manifest.json"
            ),
        ),
    )

    class _Storage:
        async def download(self, object_key):
            return responses[object_key]

    loaded_template, loaded_manifest = await _optional_official_template_assets(
        _Storage()
    )

    assert loaded_template == template
    assert loaded_manifest == manifest
    assert all(response.closed for response in responses.values())
    assert all(response.released for response in responses.values())


@pytest.mark.asyncio
async def test_optional_official_template_assets_reject_invalid_manifest_json(monkeypatch):
    monkeypatch.setattr(
        formal_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            official_report_blank_template_object_key="templates/official/report.pdf",
            official_report_blank_template_manifest_object_key=(
                "templates/official/report.manifest.json"
            ),
        ),
    )
    responses = {
        "templates/official/report.pdf": _StorageResponse(b"%PDF-template"),
        "templates/official/report.manifest.json": _StorageResponse(b"not-json"),
    }

    class _Storage:
        async def download(self, object_key):
            return responses[object_key]

    with pytest.raises(AppError) as raised:
        await _optional_official_template_assets(_Storage())

    assert raised.value.code == "OFFICIAL_TEMPLATE_MANIFEST_INVALID"


def test_formal_rule_guard_accepts_verified_citywide_commercial_rule():
    assert FormalReportService._validate_rule(_case(), _rule()) == "COMMERCIAL"


def test_formal_validation_snapshot_preserves_blank_values_and_map_identity():
    case_id = uuid4()
    report_id = uuid4()
    document_id = uuid4()
    group_id = uuid4()
    records = {
        code: SimpleNamespace(
            form_instance_id=uuid4(), version_no=2, form_status="DRAFT"
        )
        for code in ("S01", "F02-RF", "F02")
    }
    s01 = SimpleNamespace(model_dump=lambda **_kwargs: {"district_name": None})
    regional = SimpleNamespace(model_dump=lambda **_kwargs: {"factor_rows": []})
    comparison = SimpleNamespace(
        model_dump=lambda **_kwargs: {"benchmark_notes": None},
        calculation_snapshot={"benchmark_comparison_price": "109000"},
    )
    document = SimpleNamespace(
        document_id=document_id,
        document_group_id=group_id,
        version_no=2,
        checksum_sha256="a" * 64,
        original_filename="map.png",
        mime_type="image/png",
    )
    case = SimpleNamespace(
        case_id=case_id,
        case_no="CASE-1",
        case_title="Test case",
        case_type="valuation",
        valuation_base_date=date(2026, 9, 8),
        city_code="65000000",
        district_code="65000010",
        land_use_type="COMMERCIAL",
    )

    snapshot = FormalReportService._validation_input_snapshot(
        case=case,
        report_id=report_id,
        records=records,
        s01=s01,
        regional=regional,
        comparison=comparison,
        documents={"map-section-sketch": document},
        fingerprint="fingerprint-1",
    )

    assert snapshot["case_version"] == 2
    assert snapshot["report"]["data"]["S01"]["district_name"] is None
    assert snapshot["map_documents"]["map-section-sketch"]["document_id"] == str(document_id)


@pytest.mark.parametrize(
    ("case", "rule", "expected_code"),
    [
        (
            _case(land_use_type="RESIDENTIAL"),
            _rule(land_use_types=["RESIDENTIAL"]),
            "FORMAL_REPORT_TEMPLATE_LAND_USE_UNSUPPORTED",
        ),
        (
            _case(),
            _rule(district_scope={"mode": "INCLUDE", "district_codes": ["65000010"]}),
            "FORMAL_RULE_SCOPE_NOT_CITYWIDE",
        ),
        (
            _case(),
            _rule(status="RETIRED"),
            "FORMAL_RULE_AUDIT_FAILED",
        ),
    ],
)
def test_formal_rule_guard_rejects_unsafe_rule_or_template(case, rule, expected_code):
    with pytest.raises(AppError) as exc_info:
        FormalReportService._validate_rule(case, rule)
    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_formal_validation_locks_case_before_reading_writable_records():
    calls = []

    class _Pages:
        async def _read_records(self, case_id, report_id, user, *, for_update=False):
            calls.append(for_update)
            raise RuntimeError("stop after lock probe")

    service = FormalReportService(
        None,
        pages=_Pages(),
        repository=SimpleNamespace(),
    )

    with pytest.raises(RuntimeError, match="stop after lock probe"):
        await service.validate(uuid4(), uuid4(), SimpleNamespace(), None)

    assert calls == [True]


@pytest.mark.asyncio
async def test_formal_validation_rechecks_request_after_case_lock():
    calls = []
    case_id = uuid4()
    report_id = uuid4()
    request_id = uuid4()
    existing = SimpleNamespace(
        validation_run_id=uuid4(),
        case_id=case_id,
        passed_count=12,
        warning_count=0,
        failed_count=0,
        completed_at=datetime.now(UTC),
        ruleset_snapshot={},
    )

    class _Repository:
        def __init__(self):
            self.lookup_count = 0

        async def validation_for_request(self, case, report, request):
            calls.append("request_lookup")
            self.lookup_count += 1
            return None if self.lookup_count == 1 else existing

    class _Pages:
        async def _read_records(self, case, report, user, *, for_update=False):
            calls.append(("case_lock", for_update))
            return SimpleNamespace(), {}

    repository = _Repository()
    service = FormalReportService(None, pages=_Pages(), repository=repository)
    response = await service.validate(case_id, report_id, SimpleNamespace(), request_id)

    assert response.validation_run_id == existing.validation_run_id
    assert calls == [
        "request_lookup",
        ("case_lock", True),
        "request_lookup",
    ]


@pytest.mark.asyncio
async def test_formal_calculation_can_skip_optional_comparison_analysis():
    case_id = uuid4()
    report_id = uuid4()
    user = SimpleNamespace(user_id=uuid4())
    case = _case(case_id=case_id)
    case.case_no = "CASE-OPTIONAL"
    case.case_title = "Optional comparison"
    case.case_type = "valuation"
    case.city_code = "65000000"
    regional = SimpleNamespace(
        rule_version_id=uuid4(),
        benchmark_land_id=None,
        comparison_analysis_id=None,
        factor_rows=[],
        calculation_status="NOT_CALCULATED",
        calculation_snapshot={},
        calculated_at=None,
        calculated_by_user_id=None,
        regional_adjustment_rates={},
        model_dump=lambda **_: {},
    )
    comparison = SimpleNamespace(
        comparison_workflow_enabled=False,
        comparison_targets=[],
        benchmark_comparison_price=None,
        calculation_status="NOT_CALCULATED",
        calculation_snapshot={},
        calculated_at=None,
        calculated_by_user_id=None,
        benchmark_notes="",
        model_dump=lambda **_: {},
    )
    records = {"F02-RF": object(), "F02": object()}
    rule = _rule(rule_version_id=regional.rule_version_id, version_no=1)
    saved = []

    class _Pages:
        async def _ensure_default_formal_rule(self, case, record, data, user):
            del case, record, user
            return data

        async def _save_data(self, record, data, user):
            del record, user
            saved.append(data)

    class _Repository:
        async def get_rule_version(self, rule_version_id):
            assert rule_version_id == rule.rule_version_id
            return rule

    service = FormalReportService(
        None,
        pages=_Pages(),
        repository=_Repository(),
    )
    response = await service._calculate_without_comparison(
        case_id=case_id,
        report_id=report_id,
        case=case,
        records=records,
        regional=regional,
        comparison=comparison,
        user=user,
    )

    assert response.comparison_analysis_id is None
    assert response.benchmark_comparison_price is None
    assert response.targets == []
    assert regional.calculation_status == "CALCULATED"
    assert comparison.calculation_status == "CALCULATED"
    assert comparison.calculation_snapshot["comparison_workflow_enabled"] is False
    assert saved == [regional, comparison]
