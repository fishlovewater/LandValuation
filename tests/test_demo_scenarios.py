from types import SimpleNamespace
from uuid import uuid4

from app.demo.fixtures import DEMO_CASE_NO, demo_scenarios
from app.demo.lifecycle import (
    DEMO_REVIEW_RULE_SET_CODE,
    _UploadBatch,
    _build_scenario_submission_snapshot,
    _new_seed_material,
)
from app.review.service import ReviewService


def test_demo_scenarios_cover_expected_lifecycle_states() -> None:
    scenarios = demo_scenarios()

    assert [scenario.key for scenario in scenarios] == [
        "draft",
        "processing",
        "in_review",
        "revision_required",
        "review_completed",
        "archived",
    ]
    assert [scenario.case_status for scenario in scenarios] == [
        "DRAFT",
        "PROCESSING",
        "IN_REVIEW",
        "REVISION_REQUIRED",
        "REVIEW_COMPLETED",
        "ARCHIVED",
    ]
    assert len({scenario.case_no for scenario in scenarios}) == len(scenarios)
    assert next(scenario for scenario in scenarios if scenario.key == "processing").case_no == DEMO_CASE_NO
    assert next(scenario for scenario in scenarios if scenario.key == "in_review").review_status == "RECEIVED"


def test_demo_review_snapshot_uses_production_review_contract() -> None:
    material = _new_seed_material()
    uploads = _UploadBatch(material)
    scenario = next(
        item for item in uploads.scenario_materials if item.fixture.key == "in_review"
    )
    uploads.extend(
        [
            {
                "document_id": material.knowledge_document_id,
                "document_type": "REGULATION",
                "filename": "knowledge.pdf",
                "object_key": "knowledge/demo.pdf",
                "bucket_name": "land-valuation",
                "checksum_sha256": "a" * 64,
                "file_size_bytes": 1,
                "storage_etag": "etag-knowledge",
            },
            {
                "document_id": scenario.report_document_id,
                "document_type": "complete-valuation-report",
                "filename": "report.pdf",
                "object_key": "cases/demo/report.pdf",
                "bucket_name": "land-valuation",
                "checksum_sha256": "b" * 64,
                "file_size_bytes": 100,
                "storage_etag": "etag-report",
                "scenario_key": "in_review",
            },
        ]
    )

    snapshot = _build_scenario_submission_snapshot(
        scenario,
        uploads,
        appraiser_id=uuid4(),
    )
    review = SimpleNamespace(case_id=scenario.case_id)

    _document, trusted_fields = ReviewService._snapshot_trusted_inputs(snapshot)
    trusted_context = ReviewService._snapshot_trusted_run_context(
        review,
        snapshot,
        trusted_fields,
    )

    assert snapshot["schema_version"] == "valuation-review-submission-v1"
    assert len(trusted_fields) == 2
    assert trusted_context.rule_version["rule_set_code"] == DEMO_REVIEW_RULE_SET_CODE