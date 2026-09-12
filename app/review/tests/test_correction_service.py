"""Pure behavior tests for correction snapshot building and gates."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.review.corrections import build_correction_item_snapshot
from app.review.correction_service import CorrectionService
from app.review.schemas import CorrectionResubmissionCreate


class _Finding:
    def __init__(self, **values):
        self.__dict__.update(values)


def _finding(**overrides):
    base = dict(
        finding_id="11111111-1111-1111-1111-111111111111",
        finding_code="RULE:field",
        finding_type="RATE_OUT_OF_RANGE",
        severity="HIGH",
        document_id="22222222-2222-2222-2222-222222222222",
        document_version=1,
        page_number=3,
        reported_text="調整率 -12%",
        reported_value="-12",
        legal_basis=[{"rule_code": "ADJUSTMENT_RATE"}],
        source_evidence=[{"extracted_field_id": "f1"}],
        title="調整率超出允許差異",
        description="需人工核對",
    )
    base.update(overrides)
    return _Finding(**base)


def test_snapshot_copies_finding_evidence_and_legal_basis():
    snapshot = build_correction_item_snapshot(_finding())
    assert snapshot["finding_code"] == "RULE:field"
    assert snapshot["finding_type"] == "RATE_OUT_OF_RANGE"
    assert snapshot["severity"] == "HIGH"
    assert snapshot["page_number"] == 3
    assert snapshot["reported_value"] == "-12"
    assert snapshot["legal_basis_snapshot"] == [{"rule_code": "ADJUSTMENT_RATE"}]
    assert snapshot["source_evidence_snapshot"] == [{"extracted_field_id": "f1"}]
    assert snapshot["issue_summary"]
    assert snapshot["requested_correction"]


def test_snapshot_never_contains_formal_value_or_selection_source():
    snapshot = build_correction_item_snapshot(_finding())
    assert "after_value" not in snapshot
    assert "selection_source" not in snapshot
    assert "value" not in snapshot


def test_submission_base_document_uses_frozen_snapshot_version():
    document_id = uuid4()
    provenance = {
        "source_report_document_id": document_id,
        "input_snapshot": {
            "documents": [
                {
                    "document_id": str(document_id),
                    "version_no": 3,
                }
            ]
        },
    }

    projected = CorrectionService._submission_base_document(provenance)

    assert projected == {"document_id": document_id, "version_no": 3}


def test_submission_base_document_rejects_source_missing_from_frozen_snapshot():
    provenance = {
        "source_report_document_id": uuid4(),
        "input_snapshot": {
            "documents": [
                {
                    "document_id": str(uuid4()),
                    "version_no": 1,
                }
            ]
        },
    }

    assert CorrectionService._submission_base_document(provenance) is None


def _external_resubmission_fixture(extraction_state):
    case_id = uuid4()
    review_id = uuid4()
    request_id = uuid4()
    base_document_id = uuid4()
    response_document_id = uuid4()
    actor_id = uuid4()
    request = SimpleNamespace(
        correction_request_id=request_id,
        review_id=review_id,
        status="SENT",
        base_document_id=base_document_id,
        base_document_version=1,
        response_document_id=None,
        response_document_version=None,
        resubmitted_by_user_id=None,
        resubmitted_at=None,
    )
    review = SimpleNamespace(
        review_id=review_id,
        case_id=case_id,
        review_status="RETURNED_FOR_REVISION",
    )
    case = SimpleNamespace(case_id=case_id, case_type="EXTERNAL_REVIEW")

    class FakeSession:
        def __init__(self):
            self.flush_count = 0

        async def flush(self):
            self.flush_count += 1

    class FakeCorrections:
        def __init__(self):
            self.session = FakeSession()

        async def valid_resubmission_document(self, **values):
            assert values["case_id"] == case_id
            assert values["base_document_id"] == base_document_id
            assert values["base_document_version"] == 1
            assert values["document_id"] == response_document_id
            assert values["document_version"] == 2
            return {
                "document_id": response_document_id,
                "version_no": 2,
                "document_group_id": uuid4(),
            }

        async def external_resubmission_extraction_state(self, requested_case_id, document_id):
            assert requested_case_id == case_id
            assert document_id == response_document_id
            return extraction_state

    corrections = FakeCorrections()
    service = CorrectionService(SimpleNamespace(), corrections)
    payload = CorrectionResubmissionCreate(
        document_id=response_document_id,
        document_version=2,
    )
    return service, corrections, request, payload, actor_id, case, review, response_document_id


def test_external_resubmission_requires_completed_extraction_before_registration():
    service, corrections, request, payload, actor_id, case, review, _ = (
        _external_resubmission_fixture(None)
    )

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            service._register_locked_resubmission(
                request,
                payload,
                actor_id,
                case=case,
                review=review,
            )
        )

    assert exc_info.value.code == "EXTERNAL_RESUBMISSION_EXTRACTION_REQUIRED"
    assert request.status == "SENT"
    assert corrections.session.flush_count == 0


def test_external_resubmission_requires_all_extracted_candidates_to_be_resolved():
    state = {
        "extraction_id": uuid4(),
        "extraction_status": "COMPLETED",
        "pending_candidate_count": 2,
    }
    service, corrections, request, payload, actor_id, case, review, _ = (
        _external_resubmission_fixture(state)
    )

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            service._register_locked_resubmission(
                request,
                payload,
                actor_id,
                case=case,
                review=review,
            )
        )

    assert exc_info.value.code == "EXTERNAL_RESUBMISSION_CONFIRMATION_REQUIRED"
    assert request.status == "SENT"
    assert corrections.session.flush_count == 0


def test_external_resubmission_registers_only_after_extraction_and_confirmation():
    state = {
        "extraction_id": uuid4(),
        "extraction_status": "COMPLETED",
        "pending_candidate_count": 0,
    }
    service, corrections, request, payload, actor_id, case, review, document_id = (
        _external_resubmission_fixture(state)
    )

    result = asyncio.run(
        service._register_locked_resubmission(
            request,
            payload,
            actor_id,
            case=case,
            review=review,
        )
    )

    assert result is request
    assert request.status == "RESUBMITTED"
    assert request.response_document_id == document_id
    assert request.response_document_version == 2
    assert request.resubmitted_by_user_id == actor_id
    assert request.resubmitted_at is not None
    assert corrections.session.flush_count == 1
