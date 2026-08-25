from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


@pytest.fixture
def runnable_review(postgres_connection):
    user_id, case_id, review_id = uuid4(), uuid4(), uuid4()
    rule_version_id, validation_rule_id = uuid4(), uuid4()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'not-used', 'Run Tester', true, now(), now())
            """,
            (user_id, f"run-{user_id}", f"{user_id}@example.test"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status
            ) VALUES (%s, %s, 'Run API Case', 'LAND', CURRENT_DATE,
                      'F', 'F01', 'DRAFT')
            """,
            (case_id, f"RUN-{str(case_id)[:8]}"),
        )
        cursor.execute(
            """
            INSERT INTO review.reviews (
                review_id, case_id, review_status, started_by_user_id
            ) VALUES (%s, %s, 'READY_FOR_REVIEW', %s)
            """,
            (review_id, case_id, user_id),
        )
        cursor.execute(
            """
            INSERT INTO valuation.rule_versions (
                rule_version_id, rule_set_code, version_no, version_name,
                effective_from, status
            ) VALUES (%s, %s, 1, 'Run Test Rules', CURRENT_DATE, 'PUBLISHED')
            """,
            (rule_version_id, f"RUN_TEST_{str(rule_version_id)[:8]}"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.validation_rules (
                validation_rule_id, rule_version_id, rule_code, rule_name,
                target_table, target_field_code, severity, rule_expression,
                message_template
            ) VALUES (%s, %s, 'ADJUSTMENT_RATE', '調整率檢核',
                      'comparison', 'adjustment_rate', 'HIGH', '{}', '調整率不一致')
            """,
            (validation_rule_id, rule_version_id),
        )
    postgres_connection.commit()
    yield SimpleNamespace(
        user_id=user_id,
        case_id=case_id,
        review_id=review_id,
        rule_version_id=rule_version_id,
        validation_rule_id=validation_rule_id,
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute("DELETE FROM review.decisions WHERE review_id = %s", (review_id,))
        cursor.execute("DELETE FROM review.risk_summaries WHERE review_id = %s", (review_id,))
        cursor.execute("DELETE FROM review.findings WHERE review_id = %s", (review_id,))
        cursor.execute(
            "DELETE FROM valuation.validation_findings WHERE validation_run_id IN (SELECT validation_run_id FROM valuation.validation_runs WHERE review_id = %s)",
            (review_id,),
        )
        cursor.execute("UPDATE review.reviews SET latest_validation_run_id = NULL WHERE review_id = %s", (review_id,))
        cursor.execute("DELETE FROM valuation.validation_runs WHERE review_id = %s", (review_id,))
        cursor.execute("DELETE FROM review.reviews WHERE review_id = %s", (review_id,))
        cursor.execute("DELETE FROM valuation.validation_rules WHERE validation_rule_id = %s", (validation_rule_id,))
        cursor.execute("DELETE FROM valuation.rule_versions WHERE rule_version_id = %s", (rule_version_id,))
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
    postgres_connection.commit()


@pytest.fixture
def authorized_client(runnable_review):
    permissions = [
        SimpleNamespace(permission_code="review.execute"),
        SimpleNamespace(permission_code="review.decide"),
    ]
    role = SimpleNamespace(role_code="APPRAISER", is_active=True, permissions=permissions)
    user = SimpleNamespace(user_id=runnable_review.user_id, roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def run_payload(data):
    return {
        "rule_version_id": str(data.rule_version_id),
        "input_snapshot": {"document_versions": [1], "case_id": str(data.case_id)},
        "adjustment_checks": [
            {
                "validation_rule_id": str(data.validation_rule_id),
                "finding_code": "RATE-COMP-001",
                "reported_rate": "-12",
                "system_rate": "-5",
                "tolerance": "0",
                "reported_text": "報告記載調整率 -12%",
                "field_path": "comparables[0].adjustment_rate",
                "source_evidence": [
                    {"source_id": "report-p3", "page": 3, "excerpt": "調整率 -12%"}
                ],
                "legal_basis": [
                    {"source_id": "law-a10", "article": "第10條"}
                ],
            }
        ],
    }


def test_run_creates_machine_evidence_finding_and_risk_summary(
    authorized_client, runnable_review
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    )

    assert response.status_code == 202
    run = response.json()
    assert run["run_status"] == "COMPLETED"
    assert run["failed_count"] == 1
    assert run["input_snapshot"]["adjustment_checks"][0]["reported_rate"] == "-12"

    runs = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs"
    )
    assert runs.status_code == 200
    assert len(runs.json()) == 1

    fetched = authorized_client.get(f"/api/v1/review/runs/{run['validation_run_id']}")
    assert fetched.status_code == 200

    findings = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    )
    assert findings.status_code == 200
    finding = findings.json()[0]
    assert finding["source_evidence"][0]["source_id"] == "report-p3"
    assert finding["reported_adjustment_rate"] == "-12.000000"
    assert finding["system_adjustment_rate"] == "-5.000000"
    assert finding["comparison_result"]["difference"] == "-7.00"
    assert finding["ai_status"] == "AI_EXPLANATION_UNAVAILABLE"

    one_finding = authorized_client.get(
        f"/api/v1/review/findings/{finding['finding_id']}"
    )
    assert one_finding.status_code == 200

    risk = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/risk-summary"
    )
    assert risk.status_code == 200
    assert risk.json()["overall_risk_level"] == "HIGH"
    assert risk.json()["high_count"] == 1


def test_second_running_run_returns_conflict(
    authorized_client, runnable_review, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO valuation.validation_runs (
                case_id, review_id, run_no, run_status, input_snapshot,
                rule_version_id, ruleset_snapshot
            ) VALUES (%s, %s, 1, 'RUNNING', '{}', %s, '{"version": 1}')
            """,
            (
                runnable_review.case_id,
                runnable_review.review_id,
                runnable_review.rule_version_id,
            ),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_ALREADY_ACTIVE"
