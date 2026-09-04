from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.review.correction_service import CorrectionService


class _Session:
    def __init__(self, calls):
        self.calls = calls

    async def flush(self):
        self.calls.append("flush")


class _ReviewRepository:
    def __init__(
        self,
        calls,
        review,
        case,
        run,
        latest_submission=None,
        latest_original_document=None,
    ):
        self.calls = calls
        self.review = review
        self.case = case
        self.run = run
        self.latest_submission = latest_submission
        self.latest_original_document = latest_original_document
        self.session = _Session(calls)

    async def get(self, review_id, for_update=False):
        self.calls.append(("review", for_update))
        return self.review if review_id == self.review.review_id else None

    async def get_case(self, case_id, for_update=False):
        self.calls.append(("case", for_update))
        return self.case if case_id == self.case.case_id else None

    async def get_run(self, run_id):
        self.calls.append("run")
        return self.run if run_id == self.run.validation_run_id else None

    async def get_submission_provenance_by_id(
        self, submission_id, *, review_id, case_id
    ):
        self.calls.append("submission")
        if (
            self.latest_submission is None
            or submission_id != self.latest_submission["submission_id"]
            or review_id != self.review.review_id
            or case_id != self.case.case_id
        ):
            return None
        return dict(self.latest_submission)

    async def get_latest_original_document(self, case_id):
        self.calls.append("latest_document")
        if case_id != self.case.case_id:
            return None
        return self.latest_original_document

    async def list_findings(self, run_id):
        self.calls.append("findings")
        return []

    async def list_missing_items(self, review_id, open_only=True):
        self.calls.append("missing")
        return []

    async def create_decision(self, **values):
        self.calls.append("decision")
        return SimpleNamespace(**values)


class _CorrectionRepository:
    def __init__(self, calls, request=None):
        self.calls = calls
        self.request = request
        self.session = _Session(calls)

    async def get_request(self, request_id, for_update=False):
        self.calls.append(("request", for_update))
        return (
            self.request
            if self.request is not None
            and request_id == self.request.correction_request_id
            else None
        )

    async def active_for_review(self, review_id):
        self.calls.append("active")
        return self.request

    async def next_request_no(self, review_id):
        self.calls.append("next_request_no")
        return 1

    async def create_request(self, **values):
        self.calls.append("create_request")
        self.request = SimpleNamespace(
            correction_request_id=uuid4(), **values
        )
        return self.request

    async def create_items(self, rows):
        self.calls.append("create_items")
        return rows

    async def count_active_requests(self, review_id):
        self.calls.append("active_count")
        return 0

    async def count_not_evaluated_items(self, review_id):
        self.calls.append("not_evaluated")
        return 0


def _records(*, review_status="REVIEW_REQUIRED", finding_statuses=()):
    review_id = uuid4()
    case_id = uuid4()
    run_id = uuid4()
    review = SimpleNamespace(
        review_id=review_id,
        case_id=case_id,
        review_status=review_status,
        latest_validation_run_id=run_id,
        completed_at=None,
    )
    case = SimpleNamespace(case_id=case_id, case_status="REVISION_REQUIRED")
    run = SimpleNamespace(validation_run_id=run_id, run_status="COMPLETED")
    findings = [SimpleNamespace(status=status) for status in finding_statuses]
    return review, case, run, findings


@pytest.mark.asyncio
async def test_complete_review_locks_case_before_review_and_rechecks_review():
    calls = []
    review, case, run, _ = _records()
    repository = _ReviewRepository(calls, review, case, run)
    corrections = _CorrectionRepository(calls)

    await CorrectionService(repository, corrections).complete_review(
        review.review_id, "確認無誤", uuid4(), uuid4()
    )

    assert calls[:3] == [("review", False), ("case", True), ("review", True)]
    assert review.review_status == "REVIEW_COMPLETED"
    assert case.case_status == "REVIEW_COMPLETED"


@pytest.mark.asyncio
async def test_send_locks_case_before_review_and_request():
    calls = []
    review, case, run, findings = _records(finding_statuses=("CONFIRMED_ISSUE",))
    request = SimpleNamespace(
        correction_request_id=uuid4(),
        review_id=review.review_id,
        request_no=1,
        based_on_validation_run_id=run.validation_run_id,
        status="DRAFT",
        due_at=None,
        message="請修正",
        sent_by_user_id=None,
        sent_at=None,
    )
    repository = _ReviewRepository(calls, review, case, run)
    corrections = _CorrectionRepository(calls, request)

    async def list_findings(run_id):
        calls.append("findings")
        return findings

    repository.list_findings = list_findings

    await CorrectionService(repository, corrections).send(
        request.correction_request_id, uuid4(), uuid4()
    )

    assert calls[:5] == [
        ("request", False),
        ("review", False),
        ("case", True),
        ("review", True),
        ("request", True),
    ]
    assert request.status == "SENT"
    assert review.review_status == "RETURNED_FOR_REVISION"
    assert case.case_status == "REVISION_REQUIRED"


@pytest.mark.asyncio
async def test_create_draft_uses_submission_source_document_instead_of_live_latest():
    calls = []
    review, case, run, findings = _records()
    submission_id = uuid4()
    source_document_id = uuid4()
    source_document_group_id = uuid4()
    live_document_id = uuid4()
    review.latest_submission_id = submission_id
    findings.append(
        SimpleNamespace(
            finding_id=uuid4(),
            finding_code="ADJUSTMENT_RATE",
            finding_type="VALUE_MISMATCH",
            severity="HIGH",
            status="CONFIRMED_ISSUE",
        )
    )
    repository = _ReviewRepository(
        calls,
        review,
        case,
        run,
        latest_submission={
            "submission_id": submission_id,
            "source_report_document_id": source_document_id,
            "document_id": source_document_id,
            "version_no": 1,
            "document_group_id": source_document_group_id,
        },
        latest_original_document={
            "document_id": live_document_id,
            "version_no": 3,
            "document_group_id": uuid4(),
        },
    )

    async def list_findings(run_id):
        calls.append("findings")
        return findings

    repository.list_findings = list_findings
    corrections = _CorrectionRepository(calls)

    request = await CorrectionService(repository, corrections).create_draft(
        review.review_id,
        SimpleNamespace(
            due_at=datetime.now(UTC) + timedelta(days=1), message=" 請修正 "
        ),
        uuid4(),
    )

    assert request.base_document_id == source_document_id
    assert request.base_document_version == 1
    assert "submission" in calls
    assert "latest_document" not in calls


@pytest.mark.asyncio
async def test_create_draft_rejects_submission_pointer_without_owned_source_document():
    calls = []
    review, case, run, findings = _records()
    review.latest_submission_id = uuid4()
    findings.append(
        SimpleNamespace(
            finding_id=uuid4(),
            finding_code="ADJUSTMENT_RATE",
            finding_type="VALUE_MISMATCH",
            severity="HIGH",
            status="CONFIRMED_ISSUE",
        )
    )
    repository = _ReviewRepository(
        calls,
        review,
        case,
        run,
        latest_original_document={
            "document_id": uuid4(),
            "version_no": 3,
            "document_group_id": uuid4(),
        },
    )

    async def list_findings(run_id):
        calls.append("findings")
        return findings

    repository.list_findings = list_findings

    with pytest.raises(AppError) as raised:
        await CorrectionService(
            repository, _CorrectionRepository(calls)
        ).create_draft(
            review.review_id,
            SimpleNamespace(
                due_at=datetime.now(UTC) + timedelta(days=1), message="請修正"
            ),
            uuid4(),
        )

    assert raised.value.code == "CORRECTION_BASE_DOCUMENT_SUBMISSION_INVALID"
    assert raised.value.status_code == 409
    assert "submission" in calls
    assert "latest_document" not in calls


@pytest.mark.asyncio
async def test_create_draft_uses_legacy_latest_document_without_submission_pointer():
    calls = []
    review, case, run, findings = _records()
    source_document_id = uuid4()
    findings.append(
        SimpleNamespace(
            finding_id=uuid4(),
            finding_code="ADJUSTMENT_RATE",
            finding_type="VALUE_MISMATCH",
            severity="HIGH",
            status="CONFIRMED_ISSUE",
        )
    )
    repository = _ReviewRepository(
        calls,
        review,
        case,
        run,
        latest_original_document={
            "document_id": source_document_id,
            "version_no": 1,
            "document_group_id": uuid4(),
        },
    )

    async def list_findings(run_id):
        calls.append("findings")
        return findings

    repository.list_findings = list_findings
    corrections = _CorrectionRepository(calls)

    request = await CorrectionService(repository, corrections).create_draft(
        review.review_id,
        SimpleNamespace(
            due_at=datetime.now(UTC) + timedelta(days=1), message="請修正"
        ),
        uuid4(),
    )

    assert request.base_document_id == source_document_id
    assert request.base_document_version == 1
    assert "submission" not in calls
    assert "latest_document" in calls


@pytest.mark.asyncio
async def test_complete_review_rejects_a_run_from_an_older_submission():
    calls = []
    review, case, run, _ = _records()
    review.latest_submission_id = uuid4()
    run.submission_id = uuid4()
    repository = _ReviewRepository(calls, review, case, run)

    with pytest.raises(AppError) as raised:
        await CorrectionService(repository, _CorrectionRepository(calls)).complete_review(
            review.review_id, "確認無誤", uuid4(), uuid4()
        )

    assert getattr(raised.value, "code", None) == "REVIEW_SUBMISSION_STALE"
    assert review.review_status == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_recheck_requires_a_newer_valuation_submission():
    calls = []
    review, case, run, _ = _records(review_status="RETURNED_FOR_REVISION")
    previous_submission_id = uuid4()
    review.latest_submission_id = previous_submission_id
    run.submission_id = previous_submission_id
    request = SimpleNamespace(
        correction_request_id=uuid4(),
        review_id=review.review_id,
        based_on_validation_run_id=run.validation_run_id,
        status="RESUBMITTED",
        response_document_id=uuid4(),
        response_document_version=2,
    )
    repository = _ReviewRepository(calls, review, case, run)
    corrections = _CorrectionRepository(calls, request)

    with pytest.raises(AppError) as raised:
        await CorrectionService(
            repository,
            corrections,
            review_service=SimpleNamespace(),
        ).recheck(request.correction_request_id, uuid4())

    assert getattr(raised.value, "code", None) == "REVIEW_RESUBMISSION_REQUIRED"
    assert getattr(raised.value, "status_code", None) == 409
    assert request.status == "RESUBMITTED"


@pytest.mark.asyncio
async def test_recheck_rejects_when_response_document_is_not_latest_submission():
    calls = []
    review, case, run, _ = _records(review_status="RETURNED_FOR_REVISION")
    previous_submission_id = uuid4()
    latest_submission_id = uuid4()
    response_v2_document_id = uuid4()
    latest_v3_document_id = uuid4()
    review.latest_submission_id = latest_submission_id
    run.submission_id = previous_submission_id
    request = SimpleNamespace(
        correction_request_id=uuid4(),
        review_id=review.review_id,
        based_on_validation_run_id=run.validation_run_id,
        status="RESUBMITTED",
        response_document_id=response_v2_document_id,
        response_document_version=2,
    )
    latest_submission = {
        "submission_id": latest_submission_id,
        "source_report_document_id": latest_v3_document_id,
    }
    repository = _ReviewRepository(
        calls, review, case, run, latest_submission=latest_submission
    )

    class _ReviewService:
        async def check_completeness(self, *_args):
            raise AssertionError("recheck must reject before starting a Run")

    with pytest.raises(AppError) as raised:
        await CorrectionService(
            repository,
            _CorrectionRepository(calls, request),
            review_service=_ReviewService(),
        ).recheck(request.correction_request_id, uuid4())

    assert raised.value.code == "CORRECTION_RECHECK_DOCUMENT_MISMATCH"
    assert raised.value.status_code == 409
    assert request.status == "RESUBMITTED"
    assert "submission" in calls
    assert "flush" not in calls


@pytest.mark.asyncio
async def test_complete_review_rejects_already_completed_review():
    calls = []
    review, case, run, _ = _records(review_status="REVIEW_COMPLETED")
    repository = _ReviewRepository(calls, review, case, run)

    with pytest.raises(Exception) as raised:
        await CorrectionService(repository, _CorrectionRepository(calls)).complete_review(
            review.review_id, "再次完成", uuid4(), uuid4()
        )

    assert getattr(raised.value, "code", None) == "REVIEW_ALREADY_COMPLETED"
    assert "decision" not in calls
