import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.review.intake_forms as intake_forms
from app.core.exceptions import AppError
from app.review.repository import ReviewRepository
from app.review.workbench_repository import WorkbenchRepository
from app.review.workbench_service import WorkbenchService
from app.review.workbench_schemas import ExternalReviewCaseCreate
from app.valuation.documents.schemas import DocumentCategory


def test_version_diffs_compare_only_within_document_lineage():
    group_a = uuid4()
    group_b = uuid4()
    rows = [
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 1,
            "field_code": "adjustment_rate",
            "field_path": "comparables[0].adjustment_rate",
            "normalized_value": "-12",
            "raw_text": "-12%",
            "page_number": 3,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 2,
            "field_code": "adjustment_rate",
            "field_path": "comparables[0].adjustment_rate",
            "normalized_value": "-7",
            "raw_text": "-7%",
            "page_number": 3,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_b,
            "document_version": 1,
            "field_code": "adjustment_rate",
            "field_path": "comparables[0].adjustment_rate",
            "normalized_value": "-20",
            "raw_text": "-20%",
            "page_number": 8,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 1,
            "field_code": "adjustment_rate",
            "field_path": None,
            "normalized_value": "-15",
            "raw_text": "-15%",
            "page_number": 9,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 2,
            "field_code": "adjustment_rate",
            "field_path": None,
            "normalized_value": "-10",
            "raw_text": "-10%",
            "page_number": 9,
        },
    ]

    result = WorkbenchService._version_diffs(rows)

    assert len(result) == 2
    assert {item.document_group_id for item in result} == {group_a}
    by_path = {item.field_path: item for item in result}
    assert by_path["comparables[0].adjustment_rate"].previous.normalized_value == "-12"
    assert by_path["comparables[0].adjustment_rate"].current.normalized_value == "-7"
    assert by_path[None].previous.normalized_value == "-15"
    assert by_path[None].current.normalized_value == "-10"


def test_case_filters_support_dashboard_source_district_and_urgency():
    now = datetime(2026, 9, 12, 3, 0, tzinfo=UTC)

    filters, params = WorkbenchRepository._case_filters(
        "新店",
        None,
        "HIGH",
        "in_progress",
        case_source="PLATFORM",
        district="F01",
        urgency_level="DUE_SOON",
        urgency_now=now,
        urgent_days=3,
        due_soon_days=7,
    )

    assert "c.case_no ILIKE :q" in filters
    assert "r.current_risk_level = :risk_level" in filters
    assert "c.case_type <> :external_review_case_type" in filters
    assert "c.district_code = :district" in filters
    assert "r.review_status = ANY(:group_statuses)" in filters
    assert "r.due_at >= :urgency_now" in filters
    assert "remaining_days" not in params
    assert params["q"] == "%新店%"
    assert params["risk_level"] == "HIGH"
    assert params["district"] == "F01"
    assert params["external_review_case_type"] == "EXTERNAL_REVIEW"
    assert params["urgency_now"] == now
    assert params["urgent_days"] == 3
    assert params["due_soon_days"] == 7

    external_filters, _ = WorkbenchRepository._case_filters(
        None,
        None,
        None,
        None,
        case_source="EXTERNAL",
        urgency_level="NOT_SET",
    )
    assert "c.case_type = :external_review_case_type" in external_filters
    assert "r.due_at IS NULL" in external_filters


def test_create_external_case_persists_review_only_case_and_assigns_creator():
    actor_id = uuid4()
    created_case_id = uuid4()
    review_id = uuid4()

    class FakeWorkbenchRepository:
        def __init__(self):
            self.created = None

        async def case_no_exists(self, case_no: str) -> bool:
            assert case_no == "EXT-DEMO-001"
            return False

        async def create_external_case(self, record):
            record.case_id = created_case_id
            self.created = record
            return record

    class FakeSession:
        def __init__(self):
            self.flush_count = 0

        async def flush(self):
            self.flush_count += 1

    class FakeReviewRepository:
        def __init__(self):
            self.session = FakeSession()
            self.payload = None
            self.actor_id = None
            self.review = SimpleNamespace(
                review_id=review_id,
                review_status="RECEIVED",
                assigned_reviewer_id=None,
            )

        async def create(self, payload, creator_id):
            self.payload = payload
            self.actor_id = creator_id
            return self.review

    workbench_repository = FakeWorkbenchRepository()
    review_repository = FakeReviewRepository()
    service = WorkbenchService(workbench_repository, review_repository)
    payload = ExternalReviewCaseCreate(
        case_no="EXT-DEMO-001",
        case_title="外部查估案件",
        source_organization="外部查估公司",
        district_code="65000010",
        valuation_base_date=date(2026, 9, 1),
        received_at=datetime(2026, 9, 12, 2, 0, tzinfo=UTC),
        due_at=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )

    result = asyncio.run(service.create_external_case(payload, actor_id))

    assert workbench_repository.created.case_type == "EXTERNAL_REVIEW"
    assert workbench_repository.created.city_code == "65000000"
    assert workbench_repository.created.case_status == "IN_REVIEW"
    assert workbench_repository.created.requesting_agency == "外部查估公司"
    assert workbench_repository.created.created_by_user_id == actor_id
    assert review_repository.payload.case_id == created_case_id
    assert review_repository.actor_id == actor_id
    assert review_repository.review.assigned_reviewer_id == actor_id
    assert review_repository.session.flush_count == 1
    assert result.review_id == review_id
    assert result.case_id == created_case_id
    assert result.case_source == "EXTERNAL"


def test_external_document_operations_reject_platform_case_before_storage_access():
    review_id = uuid4()

    class FakeWorkbenchRepository:
        session = object()

        async def get_case_summary(self, requested_review_id):
            assert requested_review_id == review_id
            return {"case_id": uuid4(), "case_type": "LAND_ACQUISITION"}

    class FakeReviewRepository:
        async def get(self, requested_review_id):
            assert requested_review_id == review_id
            return SimpleNamespace(review_id=review_id)

    service = WorkbenchService(FakeWorkbenchRepository(), FakeReviewRepository())

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            service.upload_external_document(
                review_id,
                DocumentCategory.ORIGINAL,
                object(),
                object(),
                object(),
            )
        )

    assert exc_info.value.code == "EXTERNAL_REVIEW_OPERATION_NOT_ALLOWED"
    assert exc_info.value.status_code == 409


def test_external_document_upload_rejects_generated_report_category():
    review_id = uuid4()
    case_id = uuid4()

    class FakeWorkbenchRepository:
        session = object()

        async def get_case_summary(self, requested_review_id):
            assert requested_review_id == review_id
            return {"case_id": case_id, "case_type": "EXTERNAL_REVIEW"}

    class FakeReviewRepository:
        async def get(self, requested_review_id):
            assert requested_review_id == review_id
            return SimpleNamespace(review_id=review_id, review_status="RECEIVED")

    service = WorkbenchService(FakeWorkbenchRepository(), FakeReviewRepository())

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            service.upload_external_document(
                review_id,
                DocumentCategory.COMPLETE_VALUATION_REPORT,
                object(),
                object(),
                object(),
            )
        )

    assert exc_info.value.code == "EXTERNAL_REVIEW_DOCUMENT_CATEGORY_INVALID"
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize("operation", ["upload", "extract", "confirm"])
def test_external_input_mutations_fail_closed_once_review_is_deciding(operation: str):
    review_id = uuid4()
    case_id = uuid4()
    document_id = uuid4()

    class FakeWorkbenchRepository:
        session = object()

        async def get_case_summary(self, requested_review_id):
            assert requested_review_id == review_id
            return {"case_id": case_id, "case_type": "EXTERNAL_REVIEW"}

    class FakeReviewRepository:
        async def get(self, requested_review_id):
            assert requested_review_id == review_id
            return SimpleNamespace(
                review_id=review_id,
                review_status="REVIEW_REQUIRED",
            )

    service = WorkbenchService(FakeWorkbenchRepository(), FakeReviewRepository())

    with pytest.raises(AppError) as exc_info:
        if operation == "upload":
            asyncio.run(
                service.upload_external_document(
                    review_id,
                    DocumentCategory.ORIGINAL,
                    object(),
                    object(),
                    object(),
                )
            )
        elif operation == "extract":
            asyncio.run(
                service.start_external_document_extraction(
                    review_id,
                    document_id,
                    object(),
                    object(),
                )
            )
        else:
            asyncio.run(
                service.confirm_external_document_extraction(
                    review_id,
                    document_id,
                    object(),
                    object(),
                    object(),
                )
            )

    assert exc_info.value.code == "REVIEW_STATE_CONFLICT"
    assert exc_info.value.status_code == 409


def test_workbench_preflight_rejects_returned_for_revision_bypass():
    review_id = uuid4()

    class FakeReviewRepository:
        async def get(self, requested_review_id, **_kwargs):
            assert requested_review_id == review_id
            return SimpleNamespace(
                review_id=review_id,
                review_status="RETURNED_FOR_REVISION",
            )

    service = WorkbenchService(SimpleNamespace(), FakeReviewRepository())

    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.preflight(review_id, uuid4()))

    assert exc_info.value.code == "REVIEW_STATE_CONFLICT"
    assert exc_info.value.status_code == 409


def test_external_preflight_blocks_any_field_not_fully_handled_and_returns_case_count():
    review_id = uuid4()
    case_id = uuid4()

    class FakeReviewRepository:
        async def get(self, requested_review_id, **_kwargs):
            assert requested_review_id == review_id
            return SimpleNamespace(
                review_id=review_id,
                case_id=case_id,
                review_status="RECEIVED",
            )

        async def get_case(self, requested_case_id):
            assert requested_case_id == case_id
            return SimpleNamespace(case_type="EXTERNAL_REVIEW")

        async def pending_external_fields(self, requested_case_id):
            assert requested_case_id == case_id
            return 3

    service = WorkbenchService(SimpleNamespace(), FakeReviewRepository())

    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.preflight(review_id, uuid4()))

    assert exc_info.value.code == "REVIEW_OCR_CONFIRMATION_REQUIRED"
    assert exc_info.value.status_code == 409
    assert exc_info.value.details == {"pending_external_field_count": 3}
    assert "確認並填表或排除" in exc_info.value.message


def test_pending_external_fields_uses_completed_status_allowlist():
    case_id = uuid4()

    class FakeSession:
        def __init__(self):
            self.statement = ""
            self.parameters = None

        async def scalar(self, statement, parameters):
            self.statement = str(statement)
            self.parameters = parameters
            return 0

    session = FakeSession()
    result = asyncio.run(ReviewRepository(session).pending_external_fields(case_id))

    assert result == 0
    assert session.parameters == {"case_id": case_id}
    assert "ef.field_status IS NULL" in session.statement
    assert "NOT IN ('APPLIED', 'AUTO_APPLIED', 'REJECTED')" in session.statement


def test_fill_review_form_finishes_human_confirmation_as_applied(monkeypatch):
    user_id = uuid4()
    form_id = uuid4()
    candidate = SimpleNamespace(
        extracted_field_id=uuid4(),
        extraction_id=uuid4(),
        case_id=uuid4(),
        document_id=uuid4(),
        form_code="F01",
        field_name="vendor_note",
        extracted_value="原始辨識內容",
        confirmed_value="人工確認內容",
        confirmed_by_user_id=user_id,
        confirmed_at=datetime.now(UTC),
        source_page=2,
        applied_form_instance_id=None,
        applied_at=None,
        field_status="CONFIRMED",
    )
    form = SimpleNamespace(
        form_instance_id=form_id,
        form_code="F01",
        source_document_id=candidate.document_id,
        version_no=1,
        form_status="DRAFT",
        form_content={
            "review_extraction_id": str(candidate.extraction_id),
            "review_fields": {},
        },
        updated_by_user_id=None,
    )

    class FakeValuationRepository:
        def __init__(self, _session):
            pass

        async def list_forms(self, requested_case_id):
            assert requested_case_id == candidate.case_id
            return [form]

        async def save_form(self, saved_form):
            assert saved_form is form

    monkeypatch.setattr(intake_forms, "ValuationRepository", FakeValuationRepository)

    asyncio.run(
        intake_forms.fill_review_form(
            object(), candidate, SimpleNamespace(user_id=user_id)
        )
    )

    assert candidate.field_status == "APPLIED"
    assert candidate.applied_form_instance_id == form_id
    assert candidate.applied_at is not None
    assert form.form_content["review_fields"]["vendor_note"]["value"] == "人工確認內容"


def test_run_projection_exposes_external_snapshot_metadata_without_snapshot_body():
    run_id = uuid4()
    case_id = uuid4()
    review_id = uuid4()
    snapshot_id = uuid4()
    created_at = datetime(2026, 9, 12, 7, 5, tzinfo=UTC)
    run = SimpleNamespace(
        validation_run_id=run_id,
        case_id=case_id,
        review_id=review_id,
        run_no=2,
        run_status="COMPLETED",
        passed_count=9,
        warning_count=1,
        failed_count=0,
        started_at=created_at,
        completed_at=created_at,
        triggered_by_user_id=uuid4(),
        rule_version_id=uuid4(),
        model_id=None,
        prompt_version=None,
        error_code=None,
        error_message=None,
        submission_id=None,
        external_input_snapshot_id=snapshot_id,
    )
    service = WorkbenchService(SimpleNamespace(), SimpleNamespace())

    projected = service._run_projection(
        run,
        {},
        {
            snapshot_id: {
                "snapshot_no": 2,
                "snapshot_schema_version": "external-review-input-v1",
                "input_fingerprint": "c" * 64,
                "created_at": created_at,
            }
        },
    )

    assert projected.external_input_snapshot_id == snapshot_id
    assert projected.external_input_snapshot_no == 2
    assert projected.external_input_snapshot_created_at == created_at
    assert projected.external_input_fingerprint == "c" * 64
    assert "input_snapshot" not in projected.model_dump()
