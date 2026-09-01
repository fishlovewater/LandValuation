from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.valuation.report_packages.schemas import (
    ReportPackageCreate,
    ReportSectionStatus,
    ReportType,
)
from app.valuation.report_packages.service import ReportPackageService


def appraiser():
    return SimpleNamespace(user_id=uuid4(), roles=[])


def case_record(user_id):
    return SimpleNamespace(
        case_id=uuid4(),
        case_status="DRAFT",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )


class FakeValuationService:
    def __init__(self, case) -> None:
        self.case = case

    async def _owned_editable_case(self, case_id, user):
        assert case_id == self.case.case_id
        assert user.user_id == self.case.created_by_user_id
        return self.case

    async def get_case(self, case_id, user):
        assert case_id == self.case.case_id
        return self.case


class FakeReportRepository:
    def __init__(self) -> None:
        self.forms = {}
        self.document_types = set()

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

    async def latest_root(self, case_id):
        roots = [
            record
            for record in self.forms.values()
            if record.case_id == case_id
            and record.form_code == "F02"
            and record.form_content.get("report_type")
            == "REPORT_COMPARISON_COMMERCIAL"
        ]
        return max(roots, key=lambda record: record.version_no, default=None)

    async def active_document_types(self, case_id):
        del case_id
        return set(self.document_types)


def service_fixture():
    user = appraiser()
    case = case_record(user.user_id)
    repository = FakeReportRepository()
    service = ReportPackageService(
        None,
        repository=repository,
        valuation=FakeValuationService(case),
    )
    return service, repository, case, user


def test_report_requirements_have_fixed_six_page_order() -> None:
    response = ReportPackageService.requirements(
        ReportType.REPORT_COMPARISON_COMMERCIAL
    )

    assert response.page_count == 6
    assert [page.code for page in response.pages] == [
        "S01",
        "F02-RF",
        "F02",
        "MAP-01",
        "MAP-02",
        "MAP-03",
    ]


@pytest.mark.asyncio
async def test_create_report_builds_three_linked_form_instances() -> None:
    service, repository, case, user = service_fixture()

    response = await service.create(
        case.case_id,
        ReportPackageCreate(prepared_date=date(2026, 8, 26)),
        user,
    )

    assert response.report_type == ReportType.REPORT_COMPARISON_COMMERCIAL
    assert response.version_no == 1
    assert [component.code for component in response.components] == [
        "S01",
        "F02-RF",
        "F02",
    ]
    assert len({item.form_instance_id for item in response.components}) == 3
    assert case.case_status == "PROCESSING"

    root = repository.forms[response.report_id]
    assert root.form_code == "F02"
    assert root.form_content["report_id"] == str(response.report_id)
    assert root.form_content["official_schema_version"] == "ntpc-official-forms-2026-v1"
    assert set(root.form_content["components"]) == {"S01", "F02-RF", "F02"}
    for component in response.components:
        record = repository.forms[component.form_instance_id]
        assert record.version_no == response.version_no
        assert record.form_content["report_id"] == str(response.report_id)


@pytest.mark.asyncio
async def test_get_report_revalidates_component_relationships() -> None:
    service, repository, case, user = service_fixture()
    created = await service.create(
        case.case_id,
        ReportPackageCreate(),
        user,
    )

    response = await service.get(case.case_id, created.report_id, user)

    assert response.report_id == created.report_id
    assert [item.code for item in response.components] == ["S01", "F02-RF", "F02"]

    root = repository.forms[created.report_id]
    root.form_content["report_version"] = 99
    with pytest.raises(AppError) as raised:
        await service.get(case.case_id, created.report_id, user)
    assert raised.value.code == "REPORT_PACKAGE_CONFLICT"


@pytest.mark.asyncio
async def test_progress_is_derived_from_forms_and_active_map_documents() -> None:
    service, repository, case, user = service_fixture()

    empty = await service.progress(case.case_id, user)
    assert empty.report_id is None
    assert empty.completion_rate == "0.00"
    assert all(item.status == ReportSectionStatus.MISSING for item in empty.sections)

    created = await service.create(
        case.case_id,
        ReportPackageCreate(),
        user,
    )
    draft = await service.progress(case.case_id, user)
    assert draft.report_id == created.report_id
    assert [item.status for item in draft.sections[:3]] == [
        ReportSectionStatus.IN_PROGRESS,
        ReportSectionStatus.IN_PROGRESS,
        ReportSectionStatus.IN_PROGRESS,
    ]
    assert draft.completion_rate == "0.00"

    for component in created.components:
        repository.forms[component.form_instance_id].form_status = "READY"
    repository.document_types.update(
        {
            "map-section-sketch",
            "map-zoning",
            "map-land-value-section",
        }
    )

    complete = await service.progress(case.case_id, user)
    assert complete.completion_rate == "100.00"
    assert complete.blocking_errors == []
    assert all(
        item.status == ReportSectionStatus.COMPLETED for item in complete.sections
    )
