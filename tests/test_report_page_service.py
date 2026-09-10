from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.valuation.report_packages.page_schemas import (
    F02DraftUpdate,
    F02RFDraftUpdate,
    S01DraftUpdate,
)
from app.valuation.report_packages.page_service import ReportPageService
from app.valuation.report_packages.schemas import ReportPackageCreate
from app.valuation.report_packages.service import ReportPackageService


class FakeValuationRepository:
    def __init__(self, parcels) -> None:
        self.parcels = parcels

    async def list_parcels(self, case_id):
        return [item for item in self.parcels if item.case_id == case_id]


class FakeValuationService:
    def __init__(self, case, parcels) -> None:
        self.case = case
        self.repository = FakeValuationRepository(parcels)

    async def _owned_editable_case(self, case_id, user):
        assert case_id == self.case.case_id
        assert user.user_id == self.case.created_by_user_id
        return self.case

    async def get_case(self, case_id, user):
        assert case_id == self.case.case_id
        return self.case


class FakeReportRepository:
    def __init__(self, benchmarks) -> None:
        self.forms = {}
        self.benchmarks = benchmarks

    async def next_version(self, case_id, form_codes):
        del case_id, form_codes
        return 1

    async def create_forms(self, records):
        now = datetime.now(timezone.utc)
        for record in records:
            record.created_at = now
            record.updated_at = now
            self.forms[record.form_instance_id] = record
        return records

    async def get_form(self, case_id, form_instance_id):
        record = self.forms.get(form_instance_id)
        if record is None or record.case_id != case_id:
            return None
        return record

    async def get_forms(self, case_id, form_instance_ids):
        return [
            record
            for form_id, record in self.forms.items()
            if form_id in form_instance_ids and record.case_id == case_id
        ]

    async def save_form(self, record):
        record.updated_at = datetime.now(timezone.utc)
        return record

    async def list_benchmark_lands(self, case_id):
        return [item for item in self.benchmarks if item.case_id == case_id]

    async def get_benchmark_land(self, case_id, benchmark_land_id):
        return next(
            (
                item
                for item in self.benchmarks
                if item.case_id == case_id
                and item.benchmark_land_id == benchmark_land_id
            ),
            None,
        )

    async def document_belongs_to_case(self, case_id, document_id):
        del case_id, document_id
        return True

    async def get_comparison_analysis(self, case_id, analysis_id):
        del case_id, analysis_id
        return None

    async def list_comparison_targets(self, case_id, analysis_id):
        del case_id, analysis_id
        return []

    async def get_rule_version(self, rule_version_id):
        del rule_version_id
        return None

    async def select_default_formal_rule(self, case):
        del case
        return None


def page_service_fixture():
    user = SimpleNamespace(user_id=uuid4(), roles=[])
    case_id = uuid4()
    case = SimpleNamespace(
        case_id=case_id,
        case_no="QA-CASE-001",
        case_title="QA REPORT",
        case_type="QA",
        valuation_base_date=date(2026, 8, 26),
        city_code="QA-CITY",
        district_code="QA-DISTRICT",
        land_use_type="COMMERCIAL",
        case_status="DRAFT",
        created_by_user_id=user.user_id,
        updated_by_user_id=user.user_id,
    )
    parcel = SimpleNamespace(
        parcel_id=uuid4(),
        case_id=case_id,
        district_code="QA-DISTRICT",
        section_name="QA SECTION",
        subsection_name="",
        land_no="QA-LAND-1",
        area_sqm="100.0000",
        land_use_zone="QA ZONE",
        designated_use=None,
    )
    benchmarks = [
        SimpleNamespace(
            benchmark_land_id=uuid4(),
            case_id=case_id,
            parcel_id=parcel.parcel_id,
            benchmark_land_no="QA-B1",
            price_zone_no="QA-P1",
            is_active=True,
        ),
        SimpleNamespace(
            benchmark_land_id=uuid4(),
            case_id=case_id,
            parcel_id=parcel.parcel_id,
            benchmark_land_no="QA-B2",
            price_zone_no="QA-P2",
            is_active=True,
        ),
    ]
    repository = FakeReportRepository(benchmarks)
    valuation = FakeValuationService(case, [parcel])
    package_service = ReportPackageService(
        None,
        repository=repository,
        valuation=valuation,
    )
    page_service = ReportPageService(
        None,
        repository=repository,
        valuation=valuation,
    )
    return package_service, page_service, repository, case, benchmarks, user


def test_formal_rule_level_resolution_supports_all_factor_shapes() -> None:
    levels = [
        SimpleNamespace(
            level_code="L1",
            level_name="優",
            range_min=Decimal("60"),
            range_max=None,
            qualitative_value="第二種商業區",
        ),
        SimpleNamespace(
            level_code="L2",
            level_name="普通",
            range_min=Decimal("0"),
            range_max=Decimal("59.999999"),
            qualitative_value="住宅區",
        ),
    ]

    assert ReportPageService._resolve_rule_level("L1", levels) == "L1"
    assert ReportPageService._resolve_rule_level("優", levels) == "L1"
    assert ReportPageService._resolve_rule_level("70%", levels) == "L1"
    assert (
        ReportPageService._resolve_rule_level("第二種商業區", levels)
        == "L1"
    )
    assert ReportPageService._resolve_rule_level("無對應資料", levels) is None


@pytest.mark.asyncio
async def test_create_package_initializes_three_typed_page_drafts() -> None:
    packages, pages, repository, case, benchmarks, user = page_service_fixture()
    created = await packages.create(case.case_id, ReportPackageCreate(), user)

    s01 = await pages.get_s01(case.case_id, created.report_id, user)
    assert s01.context.case_no == "QA-CASE-001"
    assert s01.data.observations == []
    assert s01.page_schema_version == "s01-draft-v1"

    root = repository.forms[created.report_id]
    assert root.form_content["page_schema_version"] == "f02-draft-v1"
    assert root.form_content["data"]["comparison_targets"] == []


@pytest.mark.asyncio
async def test_update_s01_preserves_package_metadata_and_maps_case_context() -> None:
    packages, pages, repository, case, benchmarks, user = page_service_fixture()
    created = await packages.create(case.case_id, ReportPackageCreate(), user)

    response = await pages.update_s01(
        case.case_id,
        created.report_id,
        S01DraftUpdate(
            district_name="QA DISTRICT NAME",
            district_boundary="QA BOUNDARY",
            survey_date=date(2026, 8, 26),
            observations=[
                {
                    "item_code": "parking_convenience",
                    "facility_name": "QA PARKING",
                    "walking_distance_m": "120",
                    "distance_type": "WALKING",
                    "origin_type": "BENCHMARK_LAND_ENTRANCE",
                    "source_type": "MANUAL_CONFIRMED",
                    "source_notes": "QA ROUTE EVIDENCE",
                    "confirmed_by_user": True,
                }
            ],
        ),
        user,
    )

    assert response.context.parcels[0].land_no == "QA-LAND-1"
    assert response.data.district_boundary == "QA BOUNDARY"
    assert "CONFIRMED_SURVEY_OBSERVATION_MISSING" not in response.warnings
    stored = repository.forms[response.form_instance_id].form_content
    assert stored["report_id"] == str(created.report_id)
    assert stored["data"]["observations"][0]["distance_type"] == "WALKING"


@pytest.mark.asyncio
async def test_f02_and_f02_rf_reject_cross_page_benchmark_conflict() -> None:
    packages, pages, repository, case, benchmarks, user = page_service_fixture()
    created = await packages.create(case.case_id, ReportPackageCreate(), user)

    await pages.update_f02_rf(
        case.case_id,
        created.report_id,
        F02RFDraftUpdate(benchmark_land_id=benchmarks[0].benchmark_land_id),
        user,
    )
    with pytest.raises(AppError) as raised:
        await pages.update_f02(
            case.case_id,
            created.report_id,
            F02DraftUpdate(benchmark_land_id=benchmarks[1].benchmark_land_id),
            user,
        )
    assert raised.value.code == "REPORT_CROSS_PAGE_CONFLICT"
