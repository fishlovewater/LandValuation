import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.review.service import ReviewService, ensure_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("RECEIVED", "PREPROCESSING"),
        ("PREPROCESSING", "PENDING_MATERIALS"),
        ("PREPROCESSING", "READY_FOR_REVIEW"),
        ("READY_FOR_REVIEW", "ANALYZING"),
        ("ANALYZING", "REVIEW_REQUIRED"),
        ("REVIEW_REQUIRED", "APPROVED"),
        ("APPROVED", "REVIEW_COMPLETED"),
    ],
)
def test_legal_review_transition_returns_target(current: str, target: str):
    assert ensure_transition(current, target) == target


def test_illegal_review_transition_raises_conflict():
    with pytest.raises(AppError) as raised:
        ensure_transition("RECEIVED", "APPROVED")

    assert raised.value.code == "REVIEW_STATE_CONFLICT"
    assert raised.value.status_code == 409


def test_completed_review_cannot_transition():
    with pytest.raises(AppError):
        ensure_transition("REVIEW_COMPLETED", "PREPROCESSING")


def test_external_review_freezes_documents_fields_and_run_input_before_execution():
    review_id = uuid4()
    case_id = uuid4()
    actor_id = uuid4()
    document_id = uuid4()
    group_id = uuid4()
    field_id = uuid4()
    captured = {}

    class FakeRepository:
        async def get_case(self, requested_case_id):
            assert requested_case_id == case_id
            return SimpleNamespace(case_id=case_id, case_type="EXTERNAL_REVIEW")

        async def list_external_snapshot_documents(self, requested_case_id):
            assert requested_case_id == case_id
            return [{
                "document_id": document_id,
                "document_group_id": group_id,
                "document_type": "original",
                "original_filename": "report-v2.pdf",
                "mime_type": "application/pdf",
                "checksum_sha256": "a" * 64,
                "version_no": 2,
                "uploaded_at": datetime(2026, 9, 12, 7, 0, tzinfo=UTC),
            }]

        async def list_external_snapshot_fields(self, requested_case_id):
            assert requested_case_id == case_id
            return [{
                "extracted_field_id": field_id,
                "document_id": document_id,
                "document_group_id": group_id,
                "document_version": 2,
                "form_code": "F01",
                "field_name": "parcel_area",
                "extracted_value": "126.00",
                "confirmed_value": "126.00",
                "confidence": Decimal("0.94"),
                "source_page": 3,
                "source_text": "宗地面積 126.00 平方公尺",
                "field_status": "APPLIED",
                "confirmed_by_user_id": actor_id,
                "confirmed_at": datetime(2026, 9, 12, 7, 2, tzinfo=UTC),
            }]

        async def create_external_input_snapshot(self, **values):
            captured.update(values)
            return SimpleNamespace(external_input_snapshot_id=uuid4(), **values)

    service = ReviewService(FakeRepository())
    review = SimpleNamespace(
        review_id=review_id,
        case_id=case_id,
        latest_submission_id=None,
    )
    run_input = {
        "case": {"case_no": "EXT-001"},
        "document": {"document_id": str(document_id), "version_no": 2},
    }

    frozen = asyncio.run(
        service._freeze_external_review_input(review, actor_id, run_input)
    )

    assert frozen is not None
    assert captured["snapshot_schema_version"] == "external-review-input-v1"
    assert captured["review_id"] == review_id
    assert captured["case_id"] == case_id
    assert captured["actor_id"] == actor_id
    assert len(captured["input_fingerprint"]) == 64
    snapshot = captured["input_snapshot"]
    assert snapshot["schema_version"] == "external-review-input-v1"
    assert snapshot["documents"][0]["document_id"] == str(document_id)
    assert snapshot["documents"][0]["version_no"] == 2
    assert snapshot["resolved_fields"][0]["field_name"] == "parcel_area"
    assert snapshot["resolved_fields"][0]["confidence"] == "0.94"
    assert snapshot["resolved_fields"][0]["source_page"] == 3
    assert snapshot["run_input"] == run_input


def test_platform_review_does_not_create_external_input_snapshot():
    class FakeRepository:
        async def get_case(self, _case_id):
            raise AssertionError("platform snapshot path must not read mutable case data")

    service = ReviewService(FakeRepository())
    review = SimpleNamespace(
        review_id=uuid4(),
        case_id=uuid4(),
        latest_submission_id=uuid4(),
    )

    result = asyncio.run(
        service._freeze_external_review_input(review, uuid4(), {"case": {}})
    )

    assert result is None


def test_report_provenance_projects_platform_submission_without_storage_path():
    review_id = uuid4()
    case_id = uuid4()
    submission_id = uuid4()
    document_id = uuid4()
    group_id = uuid4()
    evidence_document_id = uuid4()
    evidence_group_id = uuid4()
    submitted_at = datetime(2026, 9, 12, 7, 0, tzinfo=UTC)

    class FakeRepository:
        async def get_submission_provenance_by_id(self, requested_id, *, review_id, case_id):
            assert requested_id == submission_id
            assert review_id == review_id_expected
            assert case_id == case_id_expected
            return {
                "submission_id": submission_id,
                "submission_no": 3,
                "submitted_at": submitted_at,
                "input_fingerprint": "c" * 64,
                "source_report_document_id": document_id,
                "input_snapshot": {
                    "documents": [
                        {
                            "document_id": str(document_id),
                            "document_group_id": str(group_id),
                            "document_type": "complete-valuation-report",
                            "original_filename": "platform-report-v3.pdf",
                            "version_no": 3,
                            "checksum_sha256": "d" * 64,
                        },
                        {
                            "document_id": str(evidence_document_id),
                            "document_group_id": str(evidence_group_id),
                            "document_type": "land-register",
                            "original_filename": "land-register-v2.pdf",
                            "version_no": 2,
                            "checksum_sha256": "e" * 64,
                        },
                    ]
                },
            }

    review_id_expected = review_id
    case_id_expected = case_id
    service = ReviewService(FakeRepository())
    run = SimpleNamespace(
        submission_id=submission_id,
        external_input_snapshot_id=None,
        run_no=4,
        started_at=submitted_at,
        input_snapshot={},
    )
    review = SimpleNamespace(review_id=review_id, case_id=case_id)

    provenance = asyncio.run(service._report_input_provenance(run, review))

    assert provenance.source == "PLATFORM"
    assert provenance.version_no == 3
    assert provenance.submission_id == submission_id
    assert provenance.fingerprint == "c" * 64
    assert len(provenance.documents) == 2
    assert provenance.documents[0].original_filename == "platform-report-v3.pdf"
    assert provenance.documents[0].checksum_sha256 == "d" * 64
    assert provenance.documents[1].document_id == evidence_document_id
    assert provenance.documents[1].original_filename == "land-register-v2.pdf"
    assert "object_key" not in provenance.model_dump()


def test_report_provenance_projects_external_snapshot_documents_only():
    review_id = uuid4()
    case_id = uuid4()
    snapshot_id = uuid4()
    document_id = uuid4()
    group_id = uuid4()
    frozen_at = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)

    class FakeRepository:
        async def get_external_input_snapshot_provenance_by_id(self, requested_id, *, review_id, case_id):
            assert requested_id == snapshot_id
            assert review_id == review_id_expected
            assert case_id == case_id_expected
            return {
                "external_input_snapshot_id": snapshot_id,
                "snapshot_no": 2,
                "snapshot_schema_version": "external-review-input-v1",
                "input_fingerprint": "e" * 64,
                "created_at": frozen_at,
                "input_snapshot": {
                    "documents": [{
                        "document_id": str(document_id),
                        "document_group_id": str(group_id),
                        "document_type": "original",
                        "original_filename": "external-report-v2.pdf",
                        "version_no": 2,
                        "checksum_sha256": "f" * 64,
                        "object_key": "cases/secret/internal-object-key.pdf",
                    }],
                    "resolved_fields": [{"field_name": "parcel_area", "confirmed_value": "126"}],
                    "run_input": {"case": {"case_no": "EXT-001"}},
                },
            }

    review_id_expected = review_id
    case_id_expected = case_id
    service = ReviewService(FakeRepository())
    run = SimpleNamespace(
        submission_id=None,
        external_input_snapshot_id=snapshot_id,
        run_no=2,
        started_at=frozen_at,
        input_snapshot={},
    )
    review = SimpleNamespace(review_id=review_id, case_id=case_id)

    provenance = asyncio.run(service._report_input_provenance(run, review))

    assert provenance.source == "EXTERNAL"
    assert provenance.version_no == 2
    assert provenance.external_input_snapshot_id == snapshot_id
    assert provenance.documents[0].document_id == document_id
    assert provenance.documents[0].document_group_id == group_id
    assert provenance.documents[0].original_filename == "external-report-v2.pdf"
    serialized = provenance.model_dump_json()
    assert "object_key" not in serialized
    assert "resolved_fields" not in serialized
    assert "run_input" not in serialized
