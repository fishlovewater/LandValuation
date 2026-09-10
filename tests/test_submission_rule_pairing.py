from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.review.rule_selection import rule_versions_are_handoff_compatible
from app.review.service import ReviewService
from app.valuation.submissions.snapshot import SNAPSHOT_SCHEMA_VERSION


def _rule(rule_set_code: str, *, paired_rule_set_code: str | None = None, rule_version_id=None):
    summary = {}
    if paired_rule_set_code is not None:
        summary["paired_rule_set_code"] = paired_rule_set_code
    return {
        "rule_version_id": rule_version_id or uuid4(),
        "rule_set_code": rule_set_code,
        "import_summary": summary,
    }


def test_same_rule_version_is_handoff_compatible_without_pair_metadata():
    rule_id = uuid4()
    source = _rule("PRODUCTION_RULES", rule_version_id=rule_id)
    selected = _rule("PRODUCTION_RULES", rule_version_id=rule_id)

    assert rule_versions_are_handoff_compatible(source, selected) is True


def test_distinct_rule_versions_require_reciprocal_pair_metadata():
    source = _rule("FORMAL_VALIDATION", paired_rule_set_code="REVIEW_EXECUTION")
    selected = _rule("REVIEW_EXECUTION", paired_rule_set_code="FORMAL_VALIDATION")

    assert rule_versions_are_handoff_compatible(source, selected) is True


def test_one_way_or_missing_pair_metadata_fails_closed():
    source = _rule("FORMAL_VALIDATION", paired_rule_set_code="REVIEW_EXECUTION")
    selected = _rule("REVIEW_EXECUTION")

    assert rule_versions_are_handoff_compatible(source, selected) is False
    assert rule_versions_are_handoff_compatible(None, selected) is False


def test_wrong_pair_target_fails_closed():
    source = _rule("FORMAL_VALIDATION", paired_rule_set_code="UNRELATED_RULES")
    selected = _rule("REVIEW_EXECUTION", paired_rule_set_code="FORMAL_VALIDATION")

    assert rule_versions_are_handoff_compatible(source, selected) is False


def _paired_submission_snapshot():
    case_id = uuid4()
    report_form_id = uuid4()
    report_document_id = uuid4()
    report_document_group_id = uuid4()
    source_rule_id = uuid4()
    review_rule_id = uuid4()
    source_document_id = uuid4()
    source_validation_run_id = uuid4()
    submitted_by = uuid4()
    field_id = uuid4()

    source_rule = {
        "rule_version_id": str(source_rule_id),
        "rule_set_code": "FORMAL_VALIDATION",
        "version_no": 1,
        "version_name": "Formal validation",
        "status": "PUBLISHED",
        "effective_from": "2026-09-01",
        "effective_to": None,
        "applicable_case_type": "LAND",
        "applicable_district_code": "65000010",
        "selection_priority": 90,
        "source_document_id": str(source_document_id),
        "import_summary": {"paired_rule_set_code": "REVIEW_EXECUTION"},
    }
    review_rule = {
        "rule_version_id": str(review_rule_id),
        "rule_set_code": "REVIEW_EXECUTION",
        "version_no": 1,
        "version_name": "Review execution",
        "status": "PUBLISHED",
        "effective_from": "2026-09-01",
        "effective_to": None,
        "applicable_case_type": "LAND",
        "applicable_district_code": "65000010",
        "selection_priority": 100,
        "source_document_id": str(source_document_id),
        "import_summary": {"paired_rule_set_code": "FORMAL_VALIDATION"},
    }
    report_document = {
        "document_id": str(report_document_id),
        "document_type": "complete-valuation-report",
        "original_filename": "report.pdf",
        "mime_type": "application/pdf",
        "version_no": 1,
        "document_group_id": str(report_document_group_id),
        "checksum_sha256": "a" * 64,
        "file_size_bytes": 128,
        "uploaded_at": "2026-09-10T00:00:00+00:00",
        "is_active": True,
    }
    report_form = {
        "form_instance_id": str(report_form_id),
        "case_id": str(case_id),
        "form_code": "F03",
        "version_no": 1,
        "form_status": "FINAL",
        "output_document_id": str(report_document_id),
        "form_content": {"report_type": "REPORT_COMPARISON_COMMERCIAL"},
    }
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "case_version": 1,
        "submitted_by_user_id": str(submitted_by),
        "request_id": str(uuid4()),
        "applied_fields": [
            {
                "extracted_field_id": str(field_id),
                "document_id": str(report_document_id),
                "form_code": "F03",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12",
                "source_page": 1,
                "source_text": "adjustment rate -12%",
                "confidence": "0.95",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(submitted_by),
                "confirmed_at": "2026-09-10T00:00:00+00:00",
            }
        ],
        "calculations": {},
        "documents": [report_document],
        "validation": {
            "validation_run_id": str(source_validation_run_id),
            "form_instance_id": str(report_form_id),
            "rule_version_id": str(source_rule_id),
        },
        "execution_context": {
            "schema_version": "valuation-review-execution-v1",
            "case": {
                "case_id": str(case_id),
                "case_no": "PAIR-001",
                "case_title": "Pairing contract",
                "case_type": "LAND",
                "district_code": "65000010",
                "valuation_base_date": "2026-09-10",
                "form_codes": ["F03"],
            },
            "source_validation_run": {
                "validation_run_id": str(source_validation_run_id),
                "case_id": str(case_id),
                "form_instance_id": str(report_form_id),
                "run_status": "COMPLETED",
                "passed_count": 1,
                "warning_count": 0,
                "failed_count": 0,
                "rule_version_id": str(source_rule_id),
                "input_snapshot": {"input_fingerprint": "b" * 64},
                "ruleset_snapshot": {"ruleset_code": "FORMAL_VALIDATION"},
                "completed_at": "2026-09-10T00:01:00+00:00",
            },
            "report": {
                "form": report_form,
                "authoritative_form": dict(report_form),
                "document": {"case_id": str(case_id), **report_document},
            },
            "rule_selection": {
                "source_rule_version": source_rule,
                "rule_version": review_rule,
                "rule_source": {
                    "document_id": str(source_document_id),
                    "checksum_sha256": "c" * 64,
                    "version_no": 1,
                    "effective_from": "2026-09-01",
                    "effective_to": None,
                },
                "validation_rules": [
                    {
                        "validation_rule_id": str(uuid4()),
                        "rule_version_id": str(review_rule_id),
                        "rule_code": "ADJUSTMENT_RATE",
                        "rule_name": "Adjustment rate",
                        "target_form_code": "F03",
                        "target_table": "comparison",
                        "target_field_code": "adjustment_rate",
                        "severity": "HIGH",
                        "rule_expression": '{"system_rate":"-5","tolerance":"0"}',
                        "message_template": "Adjustment rate mismatch",
                        "is_active": True,
                    }
                ],
            },
        },
    }
    return SimpleNamespace(case_id=case_id), snapshot


def test_review_snapshot_accepts_reciprocally_paired_rule_versions():
    review, snapshot = _paired_submission_snapshot()
    _document, fields = ReviewService._snapshot_trusted_inputs(snapshot)

    context = ReviewService._snapshot_trusted_run_context(review, snapshot, fields)

    assert context.rule_version["rule_set_code"] == "REVIEW_EXECUTION"
    assert context.prepared_rules[0].rule["rule_code"] == "ADJUSTMENT_RATE"


def test_review_snapshot_rejects_one_way_rule_pairing():
    review, snapshot = _paired_submission_snapshot()
    snapshot["execution_context"]["rule_selection"]["source_rule_version"][
        "import_summary"
    ]["paired_rule_set_code"] = "UNRELATED"
    _document, fields = ReviewService._snapshot_trusted_inputs(snapshot)

    with pytest.raises(AppError) as raised:
        ReviewService._snapshot_trusted_run_context(review, snapshot, fields)

    assert raised.value.code == "SUBMISSION_SNAPSHOT_INVALID"
