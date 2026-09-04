from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError, PermissionDeniedError
from app.valuation.models import CaseRecord, FormInstanceRecord
from app.valuation.schemas import (
    CaseStatus,
    FormCode,
    FormCreate,
    FormDraftUpdate,
    FormStatus,
)
from app.valuation.service import ValuationService


def user_with_role(role_code: str = "APPRAISER"):
    role = SimpleNamespace(role_code=role_code, is_active=True, permissions=[])
    return SimpleNamespace(user_id=uuid4(), roles=[role])


def case_record(owner_id, case_status: str = CaseStatus.DRAFT.value) -> CaseRecord:
    return CaseRecord(
        case_id=uuid4(),
        case_no="CASE-001",
        case_title="測試案件",
        case_type="TEST",
        valuation_base_date="2026-08-25",
        city_code="C01",
        district_code="D01",
        case_status=case_status,
        created_by_user_id=owner_id,
        updated_by_user_id=owner_id,
    )


class FakeRepository:
    def __init__(self, case: CaseRecord) -> None:
        self.case = case
        self.form = None
        self.forms = []
        self.owner_filter = None
        self.source_document_matches = True
        self.case_reads = []

    async def get_case(self, case_id, for_update=False):
        self.case_reads.append((case_id, for_update))
        return self.case if self.case.case_id == case_id else None

    async def list_cases(self, *, owner_id, case_status, offset, limit):
        self.owner_filter = owner_id
        return [self.case]

    async def save_case(self, record):
        return record

    async def get_form(self, case_id, form_id):
        if self.form is None:
            return None
        if self.form.case_id != case_id or self.form.form_instance_id != form_id:
            return None
        return self.form

    async def save_form(self, record):
        return record

    async def next_form_version(self, case_id, form_code):
        existing = [
            item
            for item in self.forms + ([self.form] if self.form is not None else [])
            if item.case_id == case_id and item.form_code == form_code
        ]
        return max((item.version_no for item in existing), default=0) + 1

    async def create_form(self, record):
        if record.form_instance_id is None:
            record.form_instance_id = uuid4()
        self.forms.append(record)
        self.form = record
        return record

    async def document_belongs_to_case(self, case_id, document_id):
        return self.source_document_matches


@pytest.mark.asyncio
async def test_appraiser_list_is_scoped_to_own_cases() -> None:
    user = user_with_role()
    repository = FakeRepository(case_record(user.user_id))
    service = ValuationService(None, repository=repository)

    await service.list_cases(user, case_status=None, offset=0, limit=50)

    assert repository.owner_filter == user.user_id


@pytest.mark.asyncio
@pytest.mark.parametrize("role_code", ["REVIEWER", "INSPECTOR"])
async def test_reviewer_and_inspector_can_list_readable_cases(role_code) -> None:
    user = user_with_role(role_code)
    repository = FakeRepository(case_record(uuid4()))
    service = ValuationService(None, repository=repository)

    await service.list_cases(user, case_status=None, offset=0, limit=50)

    assert repository.owner_filter is None


@pytest.mark.asyncio
async def test_other_appraiser_cannot_read_case() -> None:
    user = user_with_role()
    record = case_record(uuid4())
    service = ValuationService(None, repository=FakeRepository(record))

    with pytest.raises(PermissionDeniedError):
        await service.get_case(record.case_id, user)


@pytest.mark.asyncio
async def test_archived_case_cannot_be_edited() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.ARCHIVED.value)
    service = ValuationService(None, repository=FakeRepository(record))

    with pytest.raises(AppError) as raised:
        await service._owned_editable_case(record.case_id, user)

    assert raised.value.code == "CASE_STATE_CONFLICT"
    assert raised.value.status_code == 409


@pytest.mark.asyncio
async def test_owned_editable_case_locks_case_row_before_editing() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    repository = FakeRepository(record)
    service = ValuationService(None, repository=repository)

    await service._owned_editable_case(record.case_id, user)

    assert repository.case_reads == [(record.case_id, True)]


@pytest.mark.asyncio
async def test_archive_case_locks_case_row_before_changing_status() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    repository = FakeRepository(record)
    service = ValuationService(None, repository=repository)

    await service.archive_case(record.case_id, user)

    assert repository.case_reads == [(record.case_id, True)]
    assert record.case_status == CaseStatus.ARCHIVED.value


@pytest.mark.asyncio
async def test_returned_appraiser_can_create_new_form_version_without_rewriting_history() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.REVISION_REQUIRED.value)
    repository = FakeRepository(record)
    previous = FormInstanceRecord(
        form_instance_id=uuid4(),
        case_id=record.case_id,
        form_code=FormCode.F03.value,
        version_no=1,
        form_status=FormStatus.FINAL.value,
        created_by_user_id=user.user_id,
        updated_by_user_id=user.user_id,
    )
    repository.forms.append(previous)
    repository.form = previous
    service = ValuationService(None, repository=repository)

    created = await service.create_form(
        record.case_id,
        FormCreate(form_code=FormCode.F03),
        user,
    )

    assert created.version_no == 2
    assert created.form_instance_id != previous.form_instance_id
    assert previous.version_no == 1
    assert previous.form_status == FormStatus.FINAL.value
    assert [item.version_no for item in repository.forms] == [1, 2]


@pytest.mark.asyncio
async def test_cross_case_document_reference_is_rejected() -> None:
    user = user_with_role()
    record = case_record(user.user_id)
    repository = FakeRepository(record)
    repository.source_document_matches = False
    service = ValuationService(None, repository=repository)

    with pytest.raises(AppError) as raised:
        await service._validate_source_document(record.case_id, uuid4())

    assert raised.value.code == "CROSS_CASE_REFERENCE"
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_submit_form_moves_draft_to_ready() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    repository = FakeRepository(record)
    repository.form = FormInstanceRecord(
        form_instance_id=uuid4(),
        case_id=record.case_id,
        form_code="F03",
        version_no=1,
        form_status=FormStatus.DRAFT.value,
        created_by_user_id=user.user_id,
        updated_by_user_id=user.user_id,
    )
    service = ValuationService(None, repository=repository)

    result = await service.submit_form(
        record.case_id,
        repository.form.form_instance_id,
        user,
    )

    assert result.form_status == FormStatus.READY.value
    assert result.updated_by_user_id == user.user_id


@pytest.mark.asyncio
async def test_final_form_cannot_be_submitted_again() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    repository = FakeRepository(record)
    repository.form = FormInstanceRecord(
        form_instance_id=uuid4(),
        case_id=record.case_id,
        form_code="F03",
        version_no=1,
        form_status=FormStatus.FINAL.value,
        created_by_user_id=user.user_id,
        updated_by_user_id=user.user_id,
    )
    service = ValuationService(None, repository=repository)

    with pytest.raises(AppError) as raised:
        await service.submit_form(
            record.case_id,
            repository.form.form_instance_id,
            user,
        )

    assert raised.value.code == "FORM_STATE_CONFLICT"


@pytest.mark.asyncio
async def test_report_package_page_cannot_be_overwritten_by_generic_form_api() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    repository = FakeRepository(record)
    repository.form = FormInstanceRecord(
        form_instance_id=uuid4(),
        case_id=record.case_id,
        form_code="S01",
        version_no=1,
        form_status=FormStatus.DRAFT.value,
        form_content={
            "report_type": "REPORT_COMPARISON_COMMERCIAL",
            "components": {},
            "data": {},
        },
        created_by_user_id=user.user_id,
        updated_by_user_id=user.user_id,
    )
    service = ValuationService(None, repository=repository)

    with pytest.raises(AppError) as raised:
        await service.update_form_draft(
            record.case_id,
            repository.form.form_instance_id,
            FormDraftUpdate(form_content={"data": {"invented": True}}),
            user,
        )

    assert raised.value.code == "REPORT_PAGE_API_REQUIRED"
    assert repository.form.form_content["components"] == {}


@pytest.mark.asyncio
async def test_report_package_page_cannot_bypass_specialized_submit_checks() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    repository = FakeRepository(record)
    repository.form = FormInstanceRecord(
        form_instance_id=uuid4(),
        case_id=record.case_id,
        form_code="F02",
        version_no=1,
        form_status=FormStatus.DRAFT.value,
        form_content={"report_type": "REPORT_COMPARISON_COMMERCIAL"},
        created_by_user_id=user.user_id,
        updated_by_user_id=user.user_id,
    )
    service = ValuationService(None, repository=repository)

    with pytest.raises(AppError) as raised:
        await service.submit_form(
            record.case_id,
            repository.form.form_instance_id,
            user,
        )

    assert raised.value.code == "REPORT_PAGE_VALIDATION_REQUIRED"
    assert repository.form.form_status == FormStatus.DRAFT.value


@pytest.mark.asyncio
@pytest.mark.parametrize("form_code", list(FormCode))
async def test_all_guide_forms_support_create_save_read_and_submit(
    form_code,
) -> None:
    user = user_with_role()
    case = case_record(user.user_id, CaseStatus.PROCESSING.value)
    repository = FakeRepository(case)
    service = ValuationService(None, repository=repository)

    created = await service.create_form(
        case.case_id,
        FormCreate(form_code=form_code),
        user,
    )
    saved = await service.update_form_draft(
        case.case_id,
        created.form_instance_id,
        FormDraftUpdate(prepared_date="2026-08-26"),
        user,
    )
    read = await service.get_form(
        case.case_id,
        created.form_instance_id,
        user,
    )
    submitted = await service.submit_form(
        case.case_id,
        created.form_instance_id,
        user,
    )

    assert created.form_code == form_code.value
    assert saved.prepared_date == date(2026, 8, 26)
    assert read.form_instance_id == created.form_instance_id
    assert submitted.form_status == FormStatus.READY.value
