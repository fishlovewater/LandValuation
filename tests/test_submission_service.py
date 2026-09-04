import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError, PermissionDeniedError
from app.valuation.submissions.schemas import SubmitForReviewCommand
from app.valuation.submissions.service import SubmissionService


def actor(
    *,
    user_id=None,
    role_code="APPRAISER",
    permissions=("valuation.submit_review",),
):
    permission_records = [
        SimpleNamespace(permission_code=permission_code)
        for permission_code in permissions
    ]
    role = SimpleNamespace(
        role_code=role_code,
        is_active=True,
        permissions=permission_records,
    )
    return SimpleNamespace(user_id=user_id or uuid4(), roles=[role])


def command(*, request_id=None, case_version=1, run_id=None, document_id=None):
    return SubmitForReviewCommand(
        request_id=request_id or uuid4(),
        expected_case_version=case_version,
        source_validation_run_id=run_id or uuid4(),
        source_report_document_id=document_id or uuid4(),
    )


class SubmissionState:
    def __init__(self, owner_id, command_value):
        self.case = SimpleNamespace(
            case_id=uuid4(),
            created_by_user_id=owner_id,
            case_status="PROCESSING",
        )
        self.review = None
        self.submissions = []
        self.events = []
        self.calls = []
        self.flush_count = 0
        self.lock = asyncio.Lock()
        self.inputs = SimpleNamespace(
            case_version=command_value.expected_case_version,
            authoritative_report_form=SimpleNamespace(
                form_instance_id=uuid4(),
                case_id=self.case.case_id,
                version_no=command_value.expected_case_version,
            ),
            source_validation_run=SimpleNamespace(
                validation_run_id=command_value.source_validation_run_id,
                case_id=self.case.case_id,
                review_id=None,
                run_status="COMPLETED",
                form_instance_id=uuid4(),
                passed_count=12,
                warning_count=0,
                failed_count=0,
                rule_version_id=uuid4(),
                ruleset_snapshot={"ruleset_code": "COMPLETE_REPORT_VALIDATION_V1"},
                completed_at=datetime(2026, 9, 3, tzinfo=UTC),
                input_snapshot={"source": "valuation"},
            ),
            source_report_document=SimpleNamespace(
                document_id=command_value.source_report_document_id,
                case_id=self.case.case_id,
                document_type="complete-valuation-report",
                version_no=1,
                checksum_sha256="a" * 64,
                original_filename="report.pdf",
                mime_type="application/pdf",
                document_group_id=uuid4(),
                uploaded_at=datetime(2026, 9, 3, tzinfo=UTC),
                is_active=True,
            ),
            report_form=SimpleNamespace(
                form_instance_id=None,
                case_id=self.case.case_id,
                version_no=command_value.expected_case_version,
                form_status="FINAL",
                output_document_id=command_value.source_report_document_id,
            ),
            applied_fields=[
                {
                    "extracted_field_id": uuid4(),
                    "document_id": command_value.source_report_document_id,
                    "form_code": "F03",
                    "field_name": "unit_price",
                    "confirmed_value": "123.4500",
                    "source_page": 3,
                    "source_text": "單價 123.4500",
                    "confidence": Decimal("0.9500"),
                    "field_status": "APPLIED",
                    "confirmed_by_user_id": owner_id,
                    "confirmed_at": datetime(2026, 9, 3, tzinfo=UTC),
                }
            ],
            calculations={"F02": {"total": "246.9000"}},
            documents=[
                {
                    "document_id": command_value.source_report_document_id,
                    "document_type": "complete-valuation-report",
                    "version_no": 1,
                    "checksum_sha256": "a" * 64,
                }
            ],
            validation={
                "validation_run_id": command_value.source_validation_run_id,
                "run_status": "COMPLETED",
            },
        )
        self.inputs.report_form.form_instance_id = (
            self.inputs.authoritative_report_form.form_instance_id
        )
        self.inputs.source_validation_run.form_instance_id = (
            self.inputs.authoritative_report_form.form_instance_id
        )


class StatefulRepository:
    def __init__(self, state):
        self.state = state
        self.session = self

    async def lock_case(self, case_id):
        self.state.calls.append("lock_case")
        await self.state.lock.acquire()
        return self.state.case if self.state.case.case_id == case_id else None

    async def find_by_request(self, case_id, request_id):
        self.state.calls.append("find_by_request")
        return next(
            (
                item
                for item in self.state.submissions
                if item.case_id == case_id and item.request_id == request_id
            ),
            None,
        )

    async def lock_review_for_case(self, case_id):
        self.state.calls.append("lock_review_for_case")
        if self.state.review is None:
            return None
        latest = next(
            (
                item
                for item in self.state.submissions
                if item.submission_id == self.state.review.latest_submission_id
            ),
            None,
        )
        return SimpleNamespace(review=self.state.review, latest_submission=latest)

    async def load_submission_inputs(self, case_id, command_value):
        self.state.calls.append("load_submission_inputs")
        return self.state.inputs

    async def create_review(self, case_id, actor_id):
        self.state.calls.append("create_review")
        self.state.review = SimpleNamespace(
            review_id=uuid4(),
            case_id=case_id,
            review_status="RECEIVED",
            latest_submission_id=None,
            latest_submission=None,
        )
        return SimpleNamespace(review=self.state.review, latest_submission=None)

    async def create_submission(self, record):
        self.state.calls.append("create_submission")
        self.state.submissions.append(record)
        return record

    async def record_case_event(self, case_id, event_type, request_id, data):
        self.state.calls.append("record_case_event")
        self.state.events.append((case_id, event_type, request_id, data))

    async def flush(self):
        self.state.calls.append("flush")
        self.state.flush_count += 1
        if self.state.lock.locked():
            self.state.lock.release()


def setup_service(command_value=None, *, owner=None):
    command_value = command_value or command()
    owner = owner or actor()
    state = SubmissionState(owner.user_id, command_value)
    return (
        SubmissionService(None, repository=StatefulRepository(state)),
        state,
        owner,
        command_value,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["wrong_owner", "missing_permission"])
async def test_submit_requires_owner_and_permission(failure) -> None:
    service, state, owner, command_value = setup_service()
    submitting_actor = owner
    if failure == "wrong_owner":
        submitting_actor = actor()
    else:
        submitting_actor = actor(
            user_id=owner.user_id,
            role_code="REVIEWER",
            permissions=("review.execute",),
        )

    with pytest.raises(PermissionDeniedError) as raised:
        await service.submit(state.case.case_id, command_value, submitting_actor)

    assert raised.value.status_code == 403
    assert state.submissions == []


@pytest.mark.asyncio
async def test_submit_rejects_stale_case_version() -> None:
    service, state, owner, command_value = setup_service()
    state.inputs.case_version += 1

    with pytest.raises(AppError) as raised:
        await service.submit(state.case.case_id, command_value, owner)

    assert raised.value.code == "CASE_VERSION_CONFLICT"
    assert raised.value.status_code == 409
    assert state.submissions == []


@pytest.mark.asyncio
async def test_submit_rejects_non_completed_source_validation() -> None:
    service, state, owner, command_value = setup_service()
    state.inputs.source_validation_run.run_status = "RUNNING"

    with pytest.raises(AppError) as raised:
        await service.submit(state.case.case_id, command_value, owner)

    assert raised.value.code == "SUBMISSION_VALIDATION_NOT_COMPLETED"
    assert raised.value.status_code == 422


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("review_run", "SUBMISSION_SOURCE_RUN_INVALID"),
        ("other_case", "SUBMISSION_SOURCE_RUN_INVALID"),
        ("missing_snapshot", "SUBMISSION_VALIDATION_SNAPSHOT_REQUIRED"),
        ("missing_lineage", "SUBMISSION_SOURCE_LINEAGE_CONFLICT"),
    ],
)
def test_submit_rejects_non_valuation_or_incomplete_source_run(
    mutation, expected_code
) -> None:
    _service, state, _owner, command_value = setup_service()
    if mutation == "review_run":
        state.inputs.source_validation_run.review_id = uuid4()
    elif mutation == "other_case":
        state.inputs.source_validation_run.case_id = uuid4()
    elif mutation == "missing_snapshot":
        state.inputs.source_validation_run.input_snapshot = {}
    else:
        state.inputs.source_validation_run.form_instance_id = uuid4()

    with pytest.raises(AppError) as raised:
        SubmissionService._validate_readiness(state.inputs, command_value)

    assert raised.value.code == expected_code
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_submit_hides_report_from_other_case_or_version_as_not_found() -> None:
    service, state, owner, command_value = setup_service()
    state.inputs.report_form.output_document_id = uuid4()

    with pytest.raises(AppError) as raised:
        await service.submit(state.case.case_id, command_value, owner)

    assert raised.value.code == "RESOURCE_NOT_FOUND"
    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_submit_rejects_report_from_a_noncurrent_case_version() -> None:
    command_value = command(case_version=2)
    service, state, owner, _ = setup_service(command_value)
    state.inputs.case_version = 2
    state.inputs.authoritative_report_form.version_no = 2
    state.inputs.report_form.version_no = 1

    with pytest.raises(AppError) as raised:
        await service.submit(state.case.case_id, command_value, owner)

    assert raised.value.code == "RESOURCE_NOT_FOUND"
    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_submit_requires_applied_values() -> None:
    service, state, owner, command_value = setup_service()
    state.inputs.applied_fields = []

    with pytest.raises(AppError) as raised:
        await service.submit(state.case.case_id, command_value, owner)

    assert raised.value.code == "SUBMISSION_APPLIED_FIELDS_REQUIRED"
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_submit_rejects_any_applied_field_without_confirmed_value() -> None:
    service, state, owner, command_value = setup_service()
    state.inputs.applied_fields.append(
        {
            "extracted_field_id": uuid4(),
            "form_code": "F03",
            "field_name": "missing_value",
            "confirmed_value": None,
        }
    )

    with pytest.raises(AppError) as raised:
        await service.submit(state.case.case_id, command_value, owner)

    assert raised.value.code == "SUBMISSION_APPLIED_VALUE_REQUIRED"
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_submit_requires_formal_calculations() -> None:
    service, state, owner, command_value = setup_service()
    state.inputs.calculations = {}

    with pytest.raises(AppError) as raised:
        await service.submit(state.case.case_id, command_value, owner)

    assert raised.value.code == "SUBMISSION_CALCULATION_REQUIRED"
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_first_submit_creates_review_submission_pointer_and_event() -> None:
    service, state, owner, command_value = setup_service()

    result = await service.submit(state.case.case_id, command_value, owner)

    assert result.review_id == state.review.review_id
    assert result.submission_id == state.submissions[0].submission_id
    assert result.submission_no == 1
    assert result.case_status == "IN_REVIEW"
    assert state.review.latest_submission.submission_id == result.submission_id
    assert state.review.review_status == "RECEIVED"
    assert state.case.case_status == "IN_REVIEW"
    assert state.submissions[0].input_snapshot["case_version"] == 1
    assert state.submissions[0].input_snapshot["submitted_by_user_id"] == str(
        owner.user_id
    )
    assert state.submissions[0].input_snapshot["request_id"] == str(
        command_value.request_id
    )
    assert state.submissions[0].supersedes_submission_id is None
    assert state.inputs.source_validation_run.submission_id == result.submission_id
    assert state.events[0][1] == "SUBMITTED_FOR_REVIEW"
    assert state.flush_count == 2
    assert state.calls[:3] == [
        "lock_case",
        "find_by_request",
        "lock_review_for_case",
    ]


@pytest.mark.asyncio
async def test_submit_snapshot_contains_immutable_applied_field_evidence() -> None:
    service, state, owner, command_value = setup_service()
    field_id = state.inputs.applied_fields[0]["extracted_field_id"]
    confirmed_at = datetime(2026, 9, 3, 12, 34, 56, tzinfo=UTC)
    state.inputs.applied_fields[0].update(
        {
            "document_id": state.inputs.source_report_document.document_id,
            "source_page": 3,
            "source_text": "調整率 -12%",
            "confidence": Decimal("0.9500"),
            "field_status": "APPLIED",
            "confirmed_by_user_id": owner.user_id,
            "confirmed_at": confirmed_at,
        }
    )

    await service.submit(state.case.case_id, command_value, owner)

    assert state.submissions[0].input_snapshot["applied_fields"] == [
        {
            "extracted_field_id": str(field_id),
            "document_id": str(state.inputs.source_report_document.document_id),
            "form_code": "F03",
            "field_name": "unit_price",
            "confirmed_value": "123.4500",
            "source_page": 3,
            "source_text": "調整率 -12%",
            "confidence": "0.9500",
            "field_status": "APPLIED",
            "confirmed_by_user_id": str(owner.user_id),
            "confirmed_at": confirmed_at.isoformat(),
        }
    ]


@pytest.mark.asyncio
async def test_retry_returns_same_submission_and_review_ids() -> None:
    service, state, owner, command_value = setup_service()
    first = await service.submit(state.case.case_id, command_value, owner)
    retry_service = SubmissionService(None, repository=StatefulRepository(state))

    second = await retry_service.submit(state.case.case_id, command_value, owner)

    assert second.submission_id == first.submission_id
    assert second.review_id == first.review_id
    assert len(state.submissions) == 1
    assert len(state.events) == 1


@pytest.mark.asyncio
async def test_reused_request_with_different_inputs_conflicts() -> None:
    service, state, owner, command_value = setup_service()
    await service.submit(state.case.case_id, command_value, owner)
    changed = command(
        request_id=command_value.request_id,
        case_version=command_value.expected_case_version,
        run_id=uuid4(),
        document_id=command_value.source_report_document_id,
    )

    with pytest.raises(AppError) as raised:
        await SubmissionService(
            None,
            repository=StatefulRepository(state),
        ).submit(state.case.case_id, changed, owner)

    assert raised.value.code == "SUBMISSION_REQUEST_CONFLICT"
    assert raised.value.status_code == 409
    assert len(state.submissions) == 1


@pytest.mark.asyncio
async def test_concurrent_same_request_creates_one_submission() -> None:
    _, state, owner, command_value = setup_service()
    services = [
        SubmissionService(None, repository=StatefulRepository(state)),
        SubmissionService(None, repository=StatefulRepository(state)),
    ]

    first, second = await asyncio.gather(
        *(service.submit(state.case.case_id, command_value, owner) for service in services)
    )

    assert first.submission_id == second.submission_id
    assert len(state.submissions) == 1
    assert len(state.events) == 1


@pytest.mark.asyncio
async def test_new_submission_requires_a_newer_case_version() -> None:
    service, state, owner, first_command = setup_service()
    await service.submit(state.case.case_id, first_command, owner)

    state.case.case_status = "REVISION_REQUIRED"
    unchanged = command(
        request_id=uuid4(),
        case_version=first_command.expected_case_version,
        run_id=first_command.source_validation_run_id,
        document_id=first_command.source_report_document_id,
    )

    with pytest.raises(AppError) as raised:
        await SubmissionService(
            None,
            repository=StatefulRepository(state),
        ).submit(state.case.case_id, unchanged, owner)

    assert raised.value.code == "CASE_VERSION_CONFLICT"
    assert raised.value.status_code == 409
    assert len(state.submissions) == 1


@pytest.mark.asyncio
async def test_revision_submission_accepts_a_newer_case_version() -> None:
    service, state, owner, first_command = setup_service()
    await service.submit(state.case.case_id, first_command, owner)

    state.case.case_status = "REVISION_REQUIRED"
    newer = command(
        request_id=uuid4(),
        case_version=first_command.expected_case_version + 1,
        run_id=uuid4(),
        document_id=uuid4(),
    )
    state.inputs.case_version = newer.expected_case_version
    state.inputs.authoritative_report_form.version_no = newer.expected_case_version
    state.inputs.report_form.version_no = newer.expected_case_version
    state.inputs.source_validation_run.validation_run_id = newer.source_validation_run_id
    state.inputs.source_report_document.document_id = newer.source_report_document_id
    state.inputs.report_form.output_document_id = newer.source_report_document_id
    state.inputs.applied_fields[0]["document_id"] = newer.source_report_document_id
    state.inputs.documents[0]["document_id"] = newer.source_report_document_id

    result = await SubmissionService(
        None,
        repository=StatefulRepository(state),
    ).submit(state.case.case_id, newer, owner)

    assert result.submission_no == 2
    assert len(state.submissions) == 2
    assert state.submissions[1].supersedes_submission_id == state.submissions[0].submission_id
