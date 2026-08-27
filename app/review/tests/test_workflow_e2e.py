from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


@pytest.fixture
def workflow_data(postgres_connection):
    data = SimpleNamespace(
        user_id=uuid4(), case_id=uuid4(), source_document_id=uuid4(),
        rule_version_id=uuid4(), adjustment_rule_id=uuid4(), expert_rule_id=uuid4(),
        original_group_id=uuid4(), v1_document_id=None, v2_document_id=None,
        v1_field_ids=set(), v2_field_ids=set(),
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO auth.users (user_id, username, email, password_hash,
               display_name, is_active, created_at, updated_at)
               VALUES (%s, %s, %s, 'unused', 'E2E Reviewer', true, now(), now())""",
            (data.user_id, f"e2e-{data.user_id}", f"{data.user_id}@example.test"),
        )
        cursor.execute(
            """INSERT INTO valuation.cases (case_id, case_no, case_title, case_type,
               valuation_base_date, city_code, district_code, case_status)
               VALUES (%s, %s, 'E2E Case', 'LAND', CURRENT_DATE, 'F', 'F01', 'DRAFT')""",
            (data.case_id, f"E2E-{str(data.case_id)[:8]}"),
        )
    postgres_connection.commit()
    yield data
    with postgres_connection.cursor() as cursor:
        cursor.execute("DELETE FROM review.decisions WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (data.case_id,))
        cursor.execute("DELETE FROM review.risk_summaries WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (data.case_id,))
        cursor.execute("DELETE FROM review.findings WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (data.case_id,))
        cursor.execute("DELETE FROM valuation.validation_findings WHERE validation_run_id IN (SELECT validation_run_id FROM valuation.validation_runs WHERE case_id = %s)", (data.case_id,))
        cursor.execute("UPDATE review.reviews SET latest_validation_run_id = NULL WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM valuation.validation_runs WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM review.missing_items WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (data.case_id,))
        cursor.execute("DELETE FROM review.reviews WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM valuation.extracted_fields WHERE extraction_run_id IN (SELECT extraction_run_id FROM valuation.extraction_runs WHERE case_id = %s)", (data.case_id,))
        cursor.execute("DELETE FROM valuation.extraction_runs WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM valuation.validation_rules WHERE rule_version_id = %s", (data.rule_version_id,))
        cursor.execute("DELETE FROM valuation.rule_versions WHERE rule_version_id = %s", (data.rule_version_id,))
        cursor.execute("DELETE FROM knowledge.documents WHERE document_id = %s", (data.source_document_id,))
        cursor.execute("DELETE FROM valuation.form_instances WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM valuation.parcels WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM valuation.documents WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (data.case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (data.user_id,))
    postgres_connection.commit()


@pytest.fixture
def workflow_client(workflow_data):
    permissions = [SimpleNamespace(permission_code=code) for code in ("review.execute", "review.decide")]
    user = SimpleNamespace(user_id=workflow_data.user_id, roles=[SimpleNamespace(role_code="APPRAISER", is_active=True, permissions=permissions)])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _insert_extraction(cursor, data, document_id, version, adjustment_rate, field_ids):
    extraction_run_id = uuid4()
    cursor.execute(
        """INSERT INTO valuation.extraction_runs (extraction_run_id, case_id, document_id,
           document_version, run_no, status, extractor_name, started_at, completed_at)
           VALUES (%s, %s, %s, %s, 1, 'COMPLETED', 'fixture', now() - interval '1 minute', now())""",
        (extraction_run_id, data.case_id, document_id, version),
    )
    for field_code, path, value_type, raw_text, normalized, page in (
        ("adjustment_rate", "comparables[0].adjustment_rate", "DECIMAL", f"Adjustment rate {adjustment_rate}%", f'"{adjustment_rate}"', 3),
        ("expert_grade", "comparables[0].grade", "TEXT", "Expert grade B", '"B"', 4),
    ):
        field_id = uuid4()
        field_ids.add(str(field_id))
        cursor.execute(
            """INSERT INTO valuation.extracted_fields (extracted_field_id, extraction_run_id,
               field_code, field_path, value_type, raw_text, normalized_value, page_number,
               verification_status, verified_by_user_id, verified_at, is_official)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, 'VERIFIED', %s, %s, true)""",
            (field_id, extraction_run_id, field_code, path, value_type, raw_text, normalized, page, data.user_id, datetime.now(UTC)),
        )


def add_complete_inputs(connection, data, version=1):
    with connection.cursor() as cursor:
        if version == 1:
            data.v1_document_id = uuid4()
            for document_type, document_id, checksum in (
                ("original", data.v1_document_id, "1" * 64),
                ("land-register", uuid4(), "2" * 64),
                ("cadastral-map", uuid4(), "3" * 64),
            ):
                cursor.execute(
                    """INSERT INTO valuation.documents (document_id, case_id, document_type,
                       original_filename, mime_type, bucket_name, object_key, checksum_sha256,
                       file_size_bytes, version_no, is_active, document_group_id)
                       VALUES (%s, %s, %s, %s, 'application/pdf', 'land-valuation', %s, %s,
                               100, 1, true, %s)""",
                    (document_id, data.case_id, document_type, f"{document_type}.pdf", f"cases/{data.case_id}/{document_type}.pdf", checksum, data.original_group_id if document_type == "original" else uuid4()),
                )
            cursor.execute("INSERT INTO valuation.parcels (case_id, district_code, section_name, land_no, area_sqm) VALUES (%s, 'F01', 'Test Section', '1', 100.5)", (data.case_id,))
            cursor.execute("INSERT INTO valuation.form_instances (form_instance_id, case_id, form_code, version_no, form_status) VALUES (%s, %s, 'F01', 1, 'READY')", (uuid4(), data.case_id))
            cursor.execute(
                """INSERT INTO knowledge.documents (document_id, document_code, title, document_type,
                   original_filename, mime_type, bucket_name, object_key, checksum_sha256,
                   file_size_bytes, version_no, effective_from, extraction_status,
                   publication_status, approved_by_user_id, approved_at)
                   VALUES (%s, %s, 'E2E Rule Source', 'REGULATION', 'source.pdf',
                           'application/pdf', 'land-valuation', %s, %s, 100, 1,
                           CURRENT_DATE, 'COMPLETED', 'PUBLISHED', %s, %s)""",
                (data.source_document_id, f"E2E-SOURCE-{str(data.source_document_id)[:8]}", f"knowledge/{data.source_document_id}/source.pdf", "a" * 64, data.user_id, datetime.now(UTC)),
            )
            cursor.execute(
                """INSERT INTO valuation.rule_versions (rule_version_id, rule_set_code, version_no,
                   version_name, effective_from, status, applicable_case_type,
                   applicable_district_code, selection_priority, source_document_id)
                   VALUES (%s, %s, 1, 'E2E Rules', CURRENT_DATE, 'PUBLISHED', 'LAND', 'F01', 10, %s)""",
                (data.rule_version_id, f"E2E-{str(data.rule_version_id)[:8]}", data.source_document_id),
            )
            for rule_id, rule_code, field_code, severity, expression in (
                (data.adjustment_rule_id, "ADJUSTMENT_RATE", "adjustment_rate", "HIGH", '{"system_rate":"-5","tolerance":"0"}'),
                (data.expert_rule_id, "EXPERT_GRADE", "expert_grade", "MEDIUM", '{"system_grade":"A"}'),
            ):
                cursor.execute(
                    """INSERT INTO valuation.validation_rules (validation_rule_id, rule_version_id,
                       rule_code, rule_name, target_form_code, target_table, target_field_code,
                       severity, rule_expression, message_template, is_active)
                       VALUES (%s, %s, %s, %s, 'F01', 'comparison', %s, %s, %s, %s, true)""",
                    (rule_id, data.rule_version_id, rule_code, rule_code, field_code, severity, expression, rule_code),
                )
            _insert_extraction(cursor, data, data.v1_document_id, 1, "-12", data.v1_field_ids)
        else:
            data.v2_document_id = uuid4()
            cursor.execute("UPDATE valuation.documents SET is_active = false WHERE document_id = %s", (data.v1_document_id,))
            cursor.execute(
                """INSERT INTO valuation.documents (document_id, case_id, document_type,
                   original_filename, mime_type, bucket_name, object_key, checksum_sha256,
                   file_size_bytes, version_no, is_active, document_group_id)
                   VALUES (%s, %s, 'original', 'original-v2.pdf', 'application/pdf',
                           'land-valuation', %s, %s, 120, 2, true, %s)""",
                (data.v2_document_id, data.case_id, f"cases/{data.case_id}/original-v2.pdf", "d" * 64, data.original_group_id),
            )
            _insert_extraction(cursor, data, data.v2_document_id, 2, "-10", data.v2_field_ids)
    connection.commit()


def _snapshot_field_ids(run):
    return {check["extracted_field_id"] for check in run["input_snapshot"]["checks"]}


def _snapshot_audit_field_ids(run):
    return {
        field["extracted_field_id"]
        for field in run["input_snapshot"]["field_snapshots"]
    }


def _evidence_field_ids(findings):
    return {evidence["extracted_field_id"] for finding in findings for evidence in finding["source_evidence"]}


def _assert_completed_after_started(run):
    assert datetime.fromisoformat(run["completed_at"]) >= datetime.fromisoformat(run["started_at"])


def test_fixed_case_workflow_preserves_trusted_history(workflow_client, workflow_data, postgres_connection):
    created = workflow_client.post("/api/v1/review/cases", json={"case_id": str(workflow_data.case_id)})
    assert created.status_code == 201
    review_id = created.json()["review_id"]
    assert workflow_client.post(f"/api/v1/review/cases/{review_id}/completeness-check").json()["review_status"] == "PENDING_MATERIALS"

    add_complete_inputs(postgres_connection, workflow_data)
    assert workflow_client.post(f"/api/v1/review/cases/{review_id}/completeness-check").json()["review_status"] == "READY_FOR_REVIEW"
    run1_response = workflow_client.post(f"/api/v1/review/cases/{review_id}/runs", json={})
    assert run1_response.status_code == 200
    run1 = run1_response.json()
    _assert_completed_after_started(run1)
    assert _snapshot_field_ids(run1) == workflow_data.v1_field_ids
    assert _snapshot_audit_field_ids(run1) == workflow_data.v1_field_ids
    findings1 = workflow_client.get(f"/api/v1/review/runs/{run1['validation_run_id']}/findings").json()
    assert _evidence_field_ids(findings1) == workflow_data.v1_field_ids

    high = next(item for item in findings1 if item["severity"] == "HIGH")
    assert workflow_client.post(f"/api/v1/review/findings/{high['finding_id']}/decisions", json={"review_id": review_id, "decision": "PARTIALLY_ACCEPTED", "reason": "Revision required", "after_value": {"rate": "-7"}}).status_code == 201
    assert workflow_client.post(f"/api/v1/review/cases/{review_id}/decision", json={"decision": "RETURNED_FOR_REVISION", "reason": "Correct original report"}).status_code == 201
    assert workflow_client.patch(f"/api/v1/review/cases/{review_id}", json={"review_status": "PREPROCESSING"}).status_code == 200

    add_complete_inputs(postgres_connection, workflow_data, version=2)
    assert workflow_client.post(f"/api/v1/review/cases/{review_id}/completeness-check").json()["review_status"] == "READY_FOR_REVIEW"
    run2_response = workflow_client.post(f"/api/v1/review/cases/{review_id}/rerun", json={})
    assert run2_response.status_code == 200
    run2 = run2_response.json()
    _assert_completed_after_started(run2)
    assert _snapshot_field_ids(run2) == workflow_data.v2_field_ids
    assert _snapshot_audit_field_ids(run2) == workflow_data.v2_field_ids
    assert workflow_data.v1_field_ids.isdisjoint(workflow_data.v2_field_ids)

    findings2 = workflow_client.get(f"/api/v1/review/runs/{run2['validation_run_id']}/findings").json()
    assert {item["supersedes_finding_id"] for item in findings2} == {item["finding_id"] for item in findings1}
    saved_run1 = workflow_client.get(f"/api/v1/review/runs/{run1['validation_run_id']}").json()
    saved_run2 = workflow_client.get(f"/api/v1/review/runs/{run2['validation_run_id']}").json()
    assert _snapshot_field_ids(saved_run1) == workflow_data.v1_field_ids
    assert _snapshot_audit_field_ids(saved_run1) == workflow_data.v1_field_ids
    assert saved_run1["input_snapshot"]["document"]["version_no"] == 1
    assert _snapshot_field_ids(saved_run2) == workflow_data.v2_field_ids
    assert _snapshot_audit_field_ids(saved_run2) == workflow_data.v2_field_ids
    assert saved_run2["input_snapshot"]["document"]["version_no"] == 2
    report1 = workflow_client.get(f"/api/v1/review/runs/{run1['validation_run_id']}/report").json()
    report2 = workflow_client.get(f"/api/v1/review/runs/{run2['validation_run_id']}/report").json()
    assert _evidence_field_ids(report1["findings"]) == workflow_data.v1_field_ids
    assert _evidence_field_ids(report2["findings"]) == workflow_data.v2_field_ids
    assert all(evidence["verification_status"] == "VERIFIED" for finding in report1["findings"] for evidence in finding["source_evidence"])
