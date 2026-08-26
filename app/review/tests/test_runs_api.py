import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.core.exceptions import AppError
from app.main import app
from app.review.repository import ReviewRepository


@pytest.fixture
def runnable_review(request, postgres_connection):
    options = getattr(request, "param", {})
    with_extraction = options.get("with_extraction", True)
    adjustment_status = options.get("adjustment_status", "VERIFIED")
    source_publication_status = options.get("source_publication_status", "PUBLISHED")
    source_extraction_status = options.get("source_extraction_status", "COMPLETED")
    tied_rule_versions = options.get("tied_rule_versions", False)
    unsupported_rule = options.get("unsupported_rule", False)
    ids = SimpleNamespace(
        user_id=uuid4(),
        case_id=uuid4(),
        review_id=uuid4(),
        original_document_id=uuid4(),
        source_document_id=uuid4(),
        rule_version_id=uuid4(),
        tied_rule_version_id=uuid4(),
        adjustment_rule_id=uuid4(),
        validation_rule_id=None,
        expert_rule_id=uuid4(),
        unsupported_rule_id=uuid4(),
        extraction_run_id=uuid4(),
    )
    ids.validation_rule_id = ids.adjustment_rule_id
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'not-used', 'Run Tester', true, now(), now())
            """,
            (ids.user_id, f"run-{ids.user_id}", f"{ids.user_id}@example.test"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status
            ) VALUES (%s, %s, 'Run API Case', 'LAND', CURRENT_DATE,
                      'F', 'F01', 'DRAFT')
            """,
            (ids.case_id, f"RUN-{str(ids.case_id)[:8]}"),
        )
        cursor.execute(
            """
            INSERT INTO review.reviews (
                review_id, case_id, review_status, started_by_user_id
            ) VALUES (%s, %s, 'READY_FOR_REVIEW', %s)
            """,
            (ids.review_id, ids.case_id, ids.user_id),
        )
        cursor.execute(
            """
            INSERT INTO valuation.documents (
                document_id, case_id, document_type, original_filename,
                mime_type, bucket_name, object_key, checksum_sha256,
                file_size_bytes, version_no, is_active
            ) VALUES (%s, %s, 'original', 'run-source.pdf',
                      'application/pdf', 'land-valuation', %s, %s,
                      100, 1, true)
            """,
            (
                ids.original_document_id,
                ids.case_id,
                f"cases/{ids.case_id}/run-source.pdf",
                "e" * 64,
            ),
        )
        cursor.execute(
            """
            INSERT INTO valuation.form_instances (
                form_instance_id, case_id, form_code, version_no, form_status
            ) VALUES (%s, %s, 'F01', 1, 'READY')
            """,
            (uuid4(), ids.case_id),
        )
        approved = source_publication_status == "PUBLISHED"
        cursor.execute(
            """
            INSERT INTO knowledge.documents (
                document_id, document_code, title, document_type,
                original_filename, mime_type, bucket_name, object_key,
                checksum_sha256, file_size_bytes, version_no, effective_from,
                extraction_status, publication_status, approved_by_user_id,
                approved_at
            ) VALUES (%s, %s, 'Run Source', 'REGULATION', 'run-source.pdf',
                      'application/pdf', 'land-valuation', %s, %s, 100, 1,
                      CURRENT_DATE, %s, %s, %s, %s)
            """,
            (
                ids.source_document_id,
                f"RUN-SOURCE-{str(ids.source_document_id)[:8]}",
                f"knowledge/{ids.source_document_id}/run-source.pdf",
                "a" * 64,
                source_extraction_status,
                source_publication_status,
                ids.user_id if approved else None,
                datetime.now(UTC) if approved else None,
            ),
        )
        rule_versions = [
            (ids.rule_version_id, f"RUN_RULES_{str(ids.rule_version_id)[:8]}")
        ]
        if tied_rule_versions:
            rule_versions.append(
                (ids.tied_rule_version_id, f"RUN_TIED_{str(ids.tied_rule_version_id)[:8]}")
            )
        for rule_version_id, rule_set_code in rule_versions:
            cursor.execute(
                """
                INSERT INTO valuation.rule_versions (
                    rule_version_id, rule_set_code, version_no, version_name,
                    effective_from, status, applicable_case_type,
                    applicable_district_code, selection_priority, source_document_id
                ) VALUES (%s, %s, 1, 'Run Test Rules', CURRENT_DATE,
                          'PUBLISHED', 'LAND', 'F01', 10, %s)
                """,
                (rule_version_id, rule_set_code, ids.source_document_id),
            )
        for rule_id, rule_code, target_field_code, severity, expression in (
            (
                ids.adjustment_rule_id,
                "ADJUSTMENT_RATE",
                "adjustment_rate",
                "HIGH",
                '{"system_rate":"-5","tolerance":"0"}',
            ),
            (
                ids.expert_rule_id,
                "EXPERT_GRADE",
                "expert_grade",
                "MEDIUM",
                '{"system_grade":"A"}',
            ),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.validation_rules (
                    validation_rule_id, rule_version_id, rule_code, rule_name,
                    target_table, target_field_code, severity, rule_expression,
                    message_template, is_active
                ) VALUES (%s, %s, %s, %s, 'comparison', %s, %s, %s, %s, true)
                """,
                (
                    rule_id,
                    ids.rule_version_id,
                    rule_code,
                    rule_code,
                    target_field_code,
                    severity,
                    expression,
                    rule_code,
                ),
            )
        if unsupported_rule:
            cursor.execute(
                """
                INSERT INTO valuation.validation_rules (
                    validation_rule_id, rule_version_id, rule_code, rule_name,
                    target_table, target_field_code, severity, rule_expression,
                    message_template, is_active
                ) VALUES (%s, %s, 'UNSUPPORTED_RULE', 'Unsupported Rule',
                          'comparison', 'adjustment_rate', 'HIGH', '{}',
                          'Unsupported', true)
                """,
                (ids.unsupported_rule_id, ids.rule_version_id),
            )
        if with_extraction:
            cursor.execute(
                """
                INSERT INTO valuation.extraction_runs (
                    extraction_run_id, case_id, document_id, document_version,
                    run_no, status, extractor_name, started_at, completed_at
                ) VALUES (%s, %s, %s, 1, 1, 'COMPLETED', 'fixture',
                          now() - interval '1 minute', now())
                """,
                (ids.extraction_run_id, ids.case_id, ids.original_document_id),
            )
            for field_code, value_type, raw_text, normalized_value, status in (
                (
                    "adjustment_rate",
                    "DECIMAL",
                    "報告記載調整率 -12%",
                    '"-12"',
                    adjustment_status,
                ),
                ("expert_grade", "TEXT", "報告評定 A 級", '"A"', "VERIFIED"),
            ):
                verified = status == "VERIFIED"
                cursor.execute(
                    """
                    INSERT INTO valuation.extracted_fields (
                        extracted_field_id, extraction_run_id, field_code, field_path,
                        value_type, raw_text, normalized_value, page_number,
                        verification_status, verified_by_user_id, verified_at,
                        is_official
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 3, %s, %s, %s, true)
                    """,
                    (
                        uuid4(),
                        ids.extraction_run_id,
                        field_code,
                        f"report.{field_code}",
                        value_type,
                        raw_text,
                        normalized_value,
                        status,
                        ids.user_id if verified else None,
                        datetime.now(UTC) if verified else None,
                    ),
                )
    postgres_connection.commit()
    yield ids
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM review.decisions WHERE review_id = %s", (ids.review_id,)
        )
        cursor.execute(
            "DELETE FROM review.risk_summaries WHERE review_id = %s", (ids.review_id,)
        )
        cursor.execute("DELETE FROM review.findings WHERE review_id = %s", (ids.review_id,))
        cursor.execute(
            """
            DELETE FROM valuation.validation_findings
            WHERE validation_run_id IN (
                SELECT validation_run_id FROM valuation.validation_runs WHERE review_id = %s
            )
            """,
            (ids.review_id,),
        )
        cursor.execute(
            "UPDATE review.reviews SET latest_validation_run_id = NULL WHERE review_id = %s",
            (ids.review_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.validation_runs WHERE review_id = %s", (ids.review_id,)
        )
        cursor.execute("DELETE FROM review.reviews WHERE review_id = %s", (ids.review_id,))
        cursor.execute(
            "DELETE FROM valuation.extracted_fields WHERE extraction_run_id = %s",
            (ids.extraction_run_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.extraction_runs WHERE extraction_run_id = %s",
            (ids.extraction_run_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.validation_rules WHERE rule_version_id IN (%s, %s)",
            (ids.rule_version_id, ids.tied_rule_version_id),
        )
        cursor.execute(
            "DELETE FROM valuation.rule_versions WHERE rule_version_id IN (%s, %s)",
            (ids.rule_version_id, ids.tied_rule_version_id),
        )
        cursor.execute(
            "DELETE FROM knowledge.documents WHERE document_id = %s",
            (ids.source_document_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.form_instances WHERE case_id = %s", (ids.case_id,)
        )
        cursor.execute(
            "DELETE FROM valuation.documents WHERE case_id = %s", (ids.case_id,)
        )
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (ids.user_id,))
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


def run_payload(_data=None):
    return {}


def run_count(connection, review_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
            (review_id,),
        )
        return cursor.fetchone()[0]


def test_run_executes_every_server_selected_rule_and_preserves_server_evidence(
    authorized_client, runnable_review, postgres_connection
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json=run_payload()
    )

    assert response.status_code == 202
    run = response.json()
    assert run["run_status"] == "COMPLETED"
    assert run["failed_count"] == 1
    assert run["passed_count"] == 1
    assert run["rule_version_id"] == str(runnable_review.rule_version_id)
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ruleset_snapshot FROM valuation.validation_runs
            WHERE validation_run_id = %s
            """,
            (run["validation_run_id"],),
        )
        ruleset_snapshot = cursor.fetchone()[0]
    assert set(ruleset_snapshot["validation_rule_ids"]) == {
        str(runnable_review.adjustment_rule_id),
        str(runnable_review.expert_rule_id),
    }
    assert {check["reported_value"] for check in run["input_snapshot"]["checks"]} == {
        "-12",
        "A",
    }

    findings = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    )
    assert findings.status_code == 200
    finding = findings.json()[0]
    assert finding["source_evidence"][0]["document_id"] == str(
        runnable_review.original_document_id
    )
    assert finding["reported_adjustment_rate"] == "-12.000000"
    assert finding["system_adjustment_rate"] == "-5.000000"
    assert finding["legal_basis"][0]["document_id"] == str(
        runnable_review.source_document_id
    )

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
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_ALREADY_ACTIVE"


@pytest.mark.parametrize(
    "forged",
    [
        {"rule_version_id": str(uuid4())},
        {"validation_rule_id": str(uuid4())},
        {"reported_rate": "-5"},
        {"reported_text": "偽造原文"},
        {"reported_grade": "偽造級距"},
        {"finding_code": "FORGED-FINDING"},
        {"field_path": "forged.path"},
        {"page_number": 3},
        {"document_id": str(uuid4())},
        {"document_version": 1},
        {"source_evidence": []},
        {"legal_basis": []},
        {"adjustment_checks": []},
        {"expert_checks": []},
    ],
)
def test_run_rejects_caller_owned_authoritative_fields(
    authorized_client, runnable_review, forged
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json=forged
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "runnable_review, expected_code",
    [
        ({"with_extraction": False}, "TRUSTED_INPUT_MISSING"),
        ({"adjustment_status": "AUTO_EXTRACTED"}, "TRUSTED_INPUT_UNVERIFIED"),
        ({"source_publication_status": "DRAFT"}, "RULE_SOURCE_UNAVAILABLE"),
        ({"source_extraction_status": "PENDING"}, "RULE_SOURCE_UNAVAILABLE"),
        ({"tied_rule_versions": True}, "RULE_SELECTION_CONFLICT"),
        ({"unsupported_rule": True}, "RULE_CONFIGURATION_INVALID"),
    ],
    indirect=["runnable_review"],
)
def test_run_preflight_fails_closed_without_creating_a_run(
    authorized_client, runnable_review, postgres_connection, expected_code
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == expected_code
    assert run_count(postgres_connection, runnable_review.review_id) == 0
    review = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()
    assert review["review_status"] == "READY_FOR_REVIEW"


def test_run_snapshot_preserves_zero_server_extracted_value(
    authorized_client, runnable_review, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET normalized_value = '"0"'::jsonb, raw_text = '調整率 0%%'
            WHERE extraction_run_id = %s AND field_code = 'adjustment_rate'
            """,
            (runnable_review.extraction_run_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 202
    adjustment_check = next(
        check
        for check in response.json()["input_snapshot"]["checks"]
        if check["rule_code"] == "ADJUSTMENT_RATE"
    )
    assert adjustment_check["reported_value"] == "0"


@pytest.mark.parametrize(
    ("field_code", "value_type", "normalized_value"),
    [
        ("adjustment_rate", "DECIMAL", None),
        ("adjustment_rate", "DECIMAL", True),
        ("adjustment_rate", "DECIMAL", ["-5"]),
        ("adjustment_rate", "DECIMAL", "NaN"),
        ("adjustment_rate", "DECIMAL", "Infinity"),
        ("adjustment_rate", "DECIMAL", "1E+999999"),
        ("adjustment_rate", "TEXT", "-5"),
        ("expert_grade", "TEXT", ["A"]),
    ],
)
def test_run_rejects_invalid_trusted_normalized_value_before_mutation(
    authorized_client,
    runnable_review,
    postgres_connection,
    field_code,
    value_type,
    normalized_value,
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET value_type = %s, normalized_value = %s::jsonb
            WHERE extraction_run_id = %s AND field_code = %s
            """,
            (
                value_type,
                json.dumps(normalized_value),
                runnable_review.extraction_run_id,
                field_code,
            ),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRUSTED_INPUT_UNVERIFIED"
    assert run_count(postgres_connection, runnable_review.review_id) == 0
    assert authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()["review_status"] == "READY_FOR_REVIEW"


@pytest.mark.parametrize(
    "rule_id, column, value",
    [
        ("expert_rule_id", "target_field_code", None),
        ("expert_rule_id", "target_field_code", "adjustment_rate"),
        ("adjustment_rule_id", "rule_expression", "{}"),
        ("adjustment_rule_id", "rule_expression", "[]"),
        ("adjustment_rule_id", "rule_expression", '{"system_rate":"NaN","tolerance":"0"}'),
        ("adjustment_rule_id", "rule_expression", '{"system_rate":"1E+999999","tolerance":"0"}'),
        ("adjustment_rule_id", "rule_expression", '{"system_rate":"-5","tolerance":"1E+999999"}'),
        ("adjustment_rule_id", "rule_expression", '{"system_rate":"-5","tolerance":"-0.01"}'),
        ("expert_rule_id", "rule_expression", '{"system_grade":null}'),
    ],
)
def test_run_rejects_invalid_rule_configuration_before_mutation(
    authorized_client, runnable_review, postgres_connection, rule_id, column, value
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE valuation.validation_rules SET {column} = %s WHERE validation_rule_id = %s",
            (value, getattr(runnable_review, rule_id)),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RULE_CONFIGURATION_INVALID"
    assert run_count(postgres_connection, runnable_review.review_id) == 0
    assert authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()["review_status"] == "READY_FOR_REVIEW"


def test_rule_configuration_precedes_missing_field_validation(
    authorized_client, runnable_review, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.validation_rules
            SET rule_code = 'UNSUPPORTED_RULE', target_field_code = 'missing_field'
            WHERE validation_rule_id = %s
            """,
            (runnable_review.adjustment_rule_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RULE_CONFIGURATION_INVALID"
    assert run_count(postgres_connection, runnable_review.review_id) == 0
    assert authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()["review_status"] == "READY_FOR_REVIEW"


def test_second_finding_persistence_failure_rolls_back_the_entire_run(
    authorized_client, runnable_review, postgres_connection, monkeypatch
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET normalized_value = '"B"'::jsonb
            WHERE extraction_run_id = %s AND field_code = 'expert_grade'
            """,
            (runnable_review.extraction_run_id,),
        )
    postgres_connection.commit()

    original_create_finding = ReviewRepository.create_finding
    calls = 0

    async def fail_second_finding(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppError("TEST_PERSISTENCE_FAILURE", "測試用持久化失敗", 500)
        return await original_create_finding(self, *args, **kwargs)

    monkeypatch.setattr(ReviewRepository, "create_finding", fail_second_finding)

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "TEST_PERSISTENCE_FAILURE"
    with postgres_connection.cursor() as cursor:
        for table in (
            "valuation.validation_runs",
            "review.findings",
            "review.risk_summaries",
        ):
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE review_id = %s",
                (runnable_review.review_id,),
            )
            assert cursor.fetchone()[0] == 0
    assert authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()["review_status"] == "READY_FOR_REVIEW"
