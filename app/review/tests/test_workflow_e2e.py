from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


@pytest.fixture
def workflow_data(postgres_connection):
    ids = SimpleNamespace(
        user_id=uuid4(),
        case_id=uuid4(),
        rule_version_id=uuid4(),
        high_rule_id=uuid4(),
        medium_rule_id=uuid4(),
        original_group_id=uuid4(),
        current_document_id=None,
        current_document_version=None,
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO auth.users
               (user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at)
               VALUES (%s, %s, %s, 'unused', 'E2E Reviewer', true, now(), now())""",
            (ids.user_id, f"e2e-{ids.user_id}", f"{ids.user_id}@example.test"),
        )
        cursor.execute(
            """INSERT INTO valuation.cases
               (case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status)
               VALUES (%s, %s, 'E2E Case', 'LAND', CURRENT_DATE,
                       'F', 'F01', 'DRAFT')""",
            (ids.case_id, f"E2E-{str(ids.case_id)[:8]}"),
        )
        cursor.execute(
            """INSERT INTO valuation.rule_versions
               (rule_version_id, rule_set_code, version_no, version_name,
                effective_from, status)
               VALUES (%s, %s, 1, 'E2E Rules', CURRENT_DATE, 'PUBLISHED')""",
            (ids.rule_version_id, f"E2E_{str(ids.rule_version_id)[:8]}"),
        )
        for rule_id, code, severity, expression in (
            (
                ids.high_rule_id,
                "ADJUSTMENT_RATE",
                "HIGH",
                '{"system_rate":"-5","tolerance":"0"}',
            ),
            (
                ids.medium_rule_id,
                "EXPERT_GRADE",
                "MEDIUM",
                '{"system_grade":"A"}',
            ),
        ):
            cursor.execute(
                """INSERT INTO valuation.validation_rules
                   (validation_rule_id, rule_version_id, rule_code, rule_name,
                    target_table, target_field_code, severity, rule_expression,
                    message_template)
                   VALUES (%s, %s, %s, %s, 'comparison', %s, %s, %s, %s)""",
                (
                    rule_id,
                    ids.rule_version_id,
                    code,
                    code,
                    code.lower(),
                    severity,
                    expression,
                    code,
                ),
            )
    postgres_connection.commit()
    yield ids
    with postgres_connection.cursor() as cursor:
        cursor.execute("DELETE FROM review.decisions WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (ids.case_id,))
        cursor.execute("DELETE FROM review.risk_summaries WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (ids.case_id,))
        cursor.execute("DELETE FROM review.findings WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.validation_findings WHERE validation_run_id IN (SELECT validation_run_id FROM valuation.validation_runs WHERE case_id = %s)", (ids.case_id,))
        cursor.execute("UPDATE review.reviews SET latest_validation_run_id = NULL WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.validation_runs WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM review.missing_items WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)", (ids.case_id,))
        cursor.execute("DELETE FROM review.reviews WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.parcels WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.documents WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.validation_rules WHERE rule_version_id = %s", (ids.rule_version_id,))
        cursor.execute("DELETE FROM valuation.rule_versions WHERE rule_version_id = %s", (ids.rule_version_id,))
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (ids.user_id,))
    postgres_connection.commit()


@pytest.fixture
def workflow_client(workflow_data):
    permissions = [SimpleNamespace(permission_code=code) for code in ("review.execute", "review.decide")]
    role = SimpleNamespace(role_code="APPRAISER", is_active=True, permissions=permissions)
    user = SimpleNamespace(user_id=workflow_data.user_id, roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def add_complete_inputs(connection, data, version=1):
    with connection.cursor() as cursor:
        if version == 1:
            for index, document_type in enumerate(("original", "land-register", "cadastral-map"), 1):
                group_id = data.original_group_id if document_type == "original" else uuid4()
                document_id = uuid4()
                if document_type == "original":
                    data.current_document_id = document_id
                    data.current_document_version = 1
                cursor.execute(
                    """INSERT INTO valuation.documents
                       (document_id, case_id, document_type, original_filename, mime_type,
                        bucket_name, object_key, checksum_sha256, file_size_bytes,
                        version_no, is_active, document_group_id)
                       VALUES (%s, %s, %s, %s, 'application/pdf', 'land-valuation',
                               %s, %s, 100, 1, true, %s)""",
                    (document_id, data.case_id, document_type, f"{document_type}.pdf",
                     f"cases/{data.case_id}/{document_type}.pdf", str(index) * 64, group_id),
                )
            cursor.execute(
                """INSERT INTO valuation.parcels
                   (case_id, district_code, section_name, land_no, area_sqm)
                   VALUES (%s, 'F01', '測試段', '1', 100.5)""",
                (data.case_id,),
            )
        else:
            data.current_document_id = uuid4()
            data.current_document_version = 2
            cursor.execute(
                """INSERT INTO valuation.documents
                   (document_id, case_id, document_type, original_filename, mime_type,
                    bucket_name, object_key, checksum_sha256, file_size_bytes,
                    version_no, is_active, document_group_id)
                   VALUES (%s, %s, 'original', 'original-v2.pdf', 'application/pdf',
                           'land-valuation', %s, %s, 120, 2, true, %s)""",
                (
                    data.current_document_id,
                    data.case_id,
                    f"cases/{data.case_id}/original-v2.pdf",
                    "d" * 64,
                    data.original_group_id,
                ),
            )
    connection.commit()


def analysis_payload(data, reported="-12", include_medium=True):
    payload = {
        "rule_version_id": str(data.rule_version_id),
        "adjustment_checks": [{
            "validation_rule_id": str(data.high_rule_id),
            "finding_code": "HIGH-RATE",
            "reported_rate": reported,
            "reported_text": f"調整率 {reported}%",
            "field_path": "comparables[0].adjustment_rate",
            "document_id": str(data.current_document_id),
            "document_version": data.current_document_version,
            "page_number": 3,
        }],
        "expert_checks": [],
    }
    if include_medium:
        payload["expert_checks"] = [{
            "validation_rule_id": str(data.medium_rule_id),
            "finding_code": "MEDIUM-GRADE",
            "reported_grade": "B",
            "reported_text": "報告評定 B 級",
            "field_path": "comparables[0].grade",
            "document_id": str(data.current_document_id),
            "document_version": data.current_document_version,
            "page_number": 4,
        }]
    return payload


def test_fixed_case_workflow_preserves_history(workflow_client, workflow_data, postgres_connection):
    created = workflow_client.post("/api/v1/review/cases", json={"case_id": str(workflow_data.case_id)}).json()
    review_id = created["review_id"]
    missing = workflow_client.post(f"/api/v1/review/cases/{review_id}/completeness-check").json()
    assert missing["review_status"] == "PENDING_MATERIALS"
    assert "DOC_LAND_REGISTER" in {item["item_code"] for item in missing["items"]}

    add_complete_inputs(postgres_connection, workflow_data)
    ready = workflow_client.post(f"/api/v1/review/cases/{review_id}/completeness-check").json()
    assert ready["review_status"] == "READY_FOR_REVIEW"

    run1 = workflow_client.post(f"/api/v1/review/cases/{review_id}/runs", json=analysis_payload(workflow_data)).json()
    findings1 = workflow_client.get(f"/api/v1/review/runs/{run1['validation_run_id']}/findings").json()
    assert {item["severity"] for item in findings1} == {"HIGH", "MEDIUM"}
    high = next(item for item in findings1 if item["severity"] == "HIGH")
    workflow_client.post(
        f"/api/v1/review/findings/{high['finding_id']}/decisions",
        json={"review_id": review_id, "decision": "PARTIALLY_ACCEPTED", "reason": "現勘資料支持部分調整", "after_value": {"rate": "-7"}},
    )
    workflow_client.post(f"/api/v1/review/cases/{review_id}/decision", json={"decision": "RETURNED_FOR_REVISION", "reason": "請依審查意見修正"})
    workflow_client.patch(f"/api/v1/review/cases/{review_id}", json={"review_status": "PREPROCESSING"})
    add_complete_inputs(postgres_connection, workflow_data, version=2)
    workflow_client.post(f"/api/v1/review/cases/{review_id}/completeness-check")

    run2 = workflow_client.post(f"/api/v1/review/cases/{review_id}/rerun", json=analysis_payload(workflow_data, reported="-10", include_medium=False)).json()
    new_finding = workflow_client.get(f"/api/v1/review/runs/{run2['validation_run_id']}/findings").json()[0]
    assert new_finding["supersedes_finding_id"] == high["finding_id"]
    workflow_client.post(
        f"/api/v1/review/findings/{new_finding['finding_id']}/decisions",
        json={"review_id": review_id, "decision": "ACCEPTED", "reason": "修正版證據已核對"},
    )
    assert workflow_client.get(f"/api/v1/review/runs/{run1['validation_run_id']}").status_code == 200
    assert len(workflow_client.get(f"/api/v1/review/cases/{review_id}/decisions").json()) == 3
    report = workflow_client.get(f"/api/v1/review/runs/{run2['validation_run_id']}/report").json()
    assert report["run"]["run_no"] == 2
    assert report["findings"][0]["decisions"][0]["reason"] == "修正版證據已核對"
