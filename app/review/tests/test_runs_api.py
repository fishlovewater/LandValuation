import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.core.exceptions import AppError
from app.main import app
from app.review.repository import ReviewRepository
from app.review.service import ReviewService
from app.review.trusted_inputs import PreparedRule, TrustedField, TrustedRunContext
from app.valuation.submissions.snapshot import SNAPSHOT_SCHEMA_VERSION


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
        form_instance_id=uuid4(),
        adjustment_field_id=uuid4(),
        expert_grade_field_id=uuid4(),
        unrelated_field_id=uuid4(),
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
            (ids.form_instance_id, ids.case_id),
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
        rule_names = {
            "ADJUSTMENT_RATE": "調整率一致性檢核",
            "EXPERT_GRADE": "級距一致性檢核",
        }
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
                    rule_names[rule_code],
                    target_field_code,
                    severity,
                    expression,
                    rule_names[rule_code],
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
                INSERT INTO valuation.document_extractions (
                    extraction_id, case_id, document_id, provider,
                    extraction_status, created_by_user_id,
                    started_at, completed_at
                ) VALUES (%s, %s, %s, 'LOCAL_PDF', 'COMPLETED', %s,
                          now() - interval '1 minute', now())
                """,
                (
                    ids.extraction_run_id,
                    ids.case_id,
                    ids.original_document_id,
                    ids.user_id,
                ),
            )
            for field_id, field_code, value_type, raw_text, normalized_value, status in (
                (
                    ids.adjustment_field_id,
                    "adjustment_rate",
                    "DECIMAL",
                    "報告記載調整率 -12%",
                    '"-12"',
                    adjustment_status,
                ),
                (
                    ids.expert_grade_field_id,
                    "expert_grade",
                    "TEXT",
                    "報告評定 A 級",
                    '"A"',
                    "VERIFIED",
                ),
                (
                    ids.unrelated_field_id,
                    "property_description",
                    "TEXT",
                    "土地描述",
                    '"郊區住宅用地"',
                    "VERIFIED",
                ),
            ):
                field_status = "APPLIED" if status == "VERIFIED" else "NEEDS_CONFIRMATION"
                confirmed_value = normalized_value if field_status == "APPLIED" else None
                verified = field_status == "APPLIED"
                confirmed_at = datetime.now(UTC) if verified else None
                cursor.execute(
                    """
                    INSERT INTO valuation.extracted_fields (
                        extracted_field_id, case_id, extraction_id, document_id,
                        form_code, field_name, extracted_value, confidence,
                        source_page, source_text, field_status, confirmed_value,
                        confirmed_by_user_id, confirmed_at, applied_form_instance_id,
                        applied_at
                    ) VALUES (%s, %s, %s, %s, 'F01', %s, %s::jsonb, 0.9500,
                              3, %s, %s, %s::jsonb, %s, %s, %s, %s)
                    """,
                    (
                        field_id,
                        ids.case_id,
                        ids.extraction_run_id,
                        ids.original_document_id,
                        field_code,
                        normalized_value,
                        raw_text,
                        field_status,
                        confirmed_value,
                        ids.user_id if verified else None,
                        confirmed_at,
                        ids.form_instance_id if verified else None,
                        confirmed_at,
                    ),
                )
    postgres_connection.commit()
    yield ids
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM review.correction_request_items WHERE correction_request_id IN (SELECT correction_request_id FROM review.correction_requests WHERE review_id = %s)",
            (ids.review_id,),
        )
        cursor.execute(
            "DELETE FROM review.correction_requests WHERE review_id = %s",
            (ids.review_id,),
        )
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
            "UPDATE review.reviews SET latest_validation_run_id = NULL, latest_submission_id = NULL WHERE review_id = %s",
            (ids.review_id,),
        )
        cursor.execute(
            "UPDATE valuation.validation_runs SET submission_id = NULL WHERE review_id = %s",
            (ids.review_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.review_submissions WHERE review_id = %s",
            (ids.review_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.validation_runs WHERE review_id = %s",
            (ids.review_id,),
        )
        cursor.execute("DELETE FROM review.reviews WHERE review_id = %s", (ids.review_id,))
        cursor.execute(
            "DELETE FROM valuation.extracted_fields WHERE extraction_id = %s",
            (ids.extraction_run_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.document_extractions WHERE extraction_id = %s",
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


def attach_submission_snapshot(connection, review, snapshot):
    submission_id = uuid4()
    source_validation_run_id = uuid4()
    request_id = uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO valuation.validation_runs (
                validation_run_id, case_id, review_id, run_status,
                input_snapshot, ruleset_snapshot
            ) VALUES (%s, %s, %s, 'COMPLETED', '{}'::jsonb,
                      '{"fixture": true}'::jsonb)
            """,
            (source_validation_run_id, review.case_id, review.review_id),
        )
        cursor.execute(
            """
            INSERT INTO valuation.review_submissions (
                submission_id, review_id, case_id, submission_no,
                submitted_by_user_id, submitted_at, source_validation_run_id,
                source_report_document_id, input_snapshot, input_fingerprint,
                request_id
            ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                submission_id,
                review.review_id,
                review.case_id,
                review.user_id,
                "2026-09-03T01:02:03+00:00",
                source_validation_run_id,
                review.original_document_id,
                json.dumps(snapshot, ensure_ascii=False),
                "b" * 64,
                request_id,
            ),
        )
        cursor.execute(
            "UPDATE review.reviews SET latest_submission_id = %s WHERE review_id = %s",
            (submission_id, review.review_id),
        )
    connection.commit()
    return submission_id


def valid_submission_snapshot(review):
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "case_version": 1,
        "submitted_by_user_id": str(review.user_id),
        "request_id": str(uuid4()),
        "applied_fields": [
            {
                "extracted_field_id": str(review.adjustment_field_id),
                "document_id": str(review.original_document_id),
                "form_code": "F01",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12",
                "source_page": 3,
                "source_text": "報告記載調整率 -12%",
                "confidence": "0.9500",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(review.user_id),
                "confirmed_at": "2026-09-03T00:00:00+00:00",
            },
            {
                "extracted_field_id": str(review.expert_grade_field_id),
                "document_id": str(review.original_document_id),
                "form_code": "F01",
                "field_name": "expert_grade",
                "confirmed_value": "A",
                "source_page": 4,
                "source_text": "報告評定 A 級",
                "confidence": "0.9500",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(review.user_id),
                "confirmed_at": "2026-09-03T00:00:00+00:00",
            },
        ],
        "calculations": {},
        "documents": [
            {
                "document_id": str(review.original_document_id),
                "document_type": "original",
                "original_filename": "run-source.pdf",
                "mime_type": "application/pdf",
                "version_no": 1,
                "document_group_id": str(uuid4()),
                "checksum_sha256": "e" * 64,
                "file_size_bytes": 100,
                "uploaded_at": "2026-09-03T00:00:00+00:00",
                "is_active": True,
            }
        ],
        "validation": {},
    }


def test_run_executes_every_server_selected_rule_and_preserves_server_evidence(
    authorized_client, runnable_review, postgres_connection
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json=run_payload()
    )

    assert response.status_code == 200
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
    legal_basis = finding["legal_basis"][0]
    assert legal_basis["rule_name"] == "調整率一致性檢核"
    assert legal_basis["rule_code"] == "ADJUSTMENT_RATE"
    assert legal_basis["rule_set_code"].startswith("RUN_RULES_")
    assert legal_basis["version_name"] == "Run Test Rules"
    assert legal_basis["version_no"] == 1

    risk = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/risk-summary"
    )
    assert risk.status_code == 200
    assert risk.json()["overall_risk_level"] == "HIGH"
    assert risk.json()["high_count"] == 1


def test_submitted_review_run_uses_immutable_snapshot_after_live_field_mutation(
    authorized_client, runnable_review, postgres_connection
):
    submission_id = attach_submission_snapshot(
        postgres_connection,
        runnable_review,
        valid_submission_snapshot(runnable_review),
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET confirmed_value = '"-99"'::jsonb,
                source_text = '報告記載調整率 -99%%'
            WHERE extracted_field_id = %s
            """,
            (runnable_review.adjustment_field_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 200
    run = response.json()
    assert run["submission_id"] == str(submission_id)
    adjustment_check = next(
        check
        for check in run["input_snapshot"]["checks"]
        if check["rule_code"] == "ADJUSTMENT_RATE"
    )
    assert adjustment_check["reported_value"] == "-12"
    findings = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    )
    assert findings.status_code == 200
    assert findings.json()[0]["reported_adjustment_rate"] == "-12.000000"


def test_submitted_review_run_rejects_malformed_snapshot(
    authorized_client, runnable_review, postgres_connection
):
    attach_submission_snapshot(postgres_connection, runnable_review, {})

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUBMISSION_SNAPSHOT_INVALID"
    assert run_count(postgres_connection, runnable_review.review_id) == 1


def test_run_snapshot_preserves_complete_trusted_audit_context(
    authorized_client, runnable_review
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 200
    snapshot = response.json()["input_snapshot"]
    assert {
        "case",
        "report_context",
        "document",
        "trusted_input_source",
        "field_snapshots",
        "rule_version",
        "rule_source",
        "validation_rules",
    } <= snapshot.keys()
    assert {
        "document_id",
        "version_no",
        "document_group_id",
    } <= snapshot["document"].keys()
    assert snapshot["trusted_input_source"] == {
        "field_status": "APPLIED",
        "value_column": "confirmed_value",
    }
    field = next(
        item
        for item in snapshot["field_snapshots"]
        if item["field_code"] == "adjustment_rate"
    )
    assert {
        "extracted_field_id",
        "field_code",
        "raw_value",
        "normalized_value",
        "value_type",
        "verification_status",
        "verified_by_user_id",
        "verified_at",
        "page",
        "bounding_box",
        "confidence",
        "is_official",
        "field_path",
        "excerpt",
    } <= field.keys()
    assert snapshot["rule_version"]["selection_priority"] == 10
    assert snapshot["rule_source"]["document_id"] == str(
        runnable_review.source_document_id
    )
    snapshot_field_ids = [
        item["extracted_field_id"] for item in snapshot["field_snapshots"]
    ]
    assert set(snapshot_field_ids) == {
        str(runnable_review.adjustment_field_id),
        str(runnable_review.expert_grade_field_id),
        str(runnable_review.unrelated_field_id),
    }
    assert len(snapshot_field_ids) == len(set(snapshot_field_ids))
    assert next(
        item
        for item in snapshot["field_snapshots"]
        if item["extracted_field_id"] == str(runnable_review.unrelated_field_id)
    )["field_code"] == "property_description"
    assert {
        item["validation_rule_id"] for item in snapshot["validation_rules"]
    } == {
        str(runnable_review.adjustment_rule_id),
        str(runnable_review.expert_rule_id),
    }
    assert snapshot["report_context"] == {
        "review_status": "REVIEW_REQUIRED",
        "missing_item_count": 0,
    }


def test_snapshot_deduplicates_shared_prepared_field_but_keeps_all_official_fields():
    adjustment_field = TrustedField(
        extracted_field_id="field-adjustment",
        form_code="F01",
        field_name="adjustment_rate",
        confirmed_value="-12",
        source_page=3,
        source_text="調整率 -12%",
        confidence="0.9900",
        field_status="APPLIED",
        confirmed_by_user_id="verifier-1",
        confirmed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )
    grade_field = TrustedField(
        extracted_field_id="field-grade",
        form_code="F01",
        field_name="expert_grade",
        confirmed_value="A",
        source_page=4,
        source_text="A 級",
        confidence="0.9900",
        field_status="APPLIED",
        confirmed_by_user_id="verifier-1",
        confirmed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )
    unrelated_field = TrustedField(
        extracted_field_id="field-description",
        form_code="F01",
        field_name="property_description",
        confirmed_value="郊區住宅用地",
        source_page=5,
        source_text="郊區住宅用地",
        confidence="0.9900",
        field_status="APPLIED",
        confirmed_by_user_id="verifier-1",
        confirmed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )
    rule_version_id = uuid4()
    adjustment_rule = {
        "rule_version_id": rule_version_id,
        "validation_rule_id": uuid4(),
        "rule_code": "ADJUSTMENT_RATE",
        "target_form_code": "F01",
        "target_table": "comparison",
        "target_field_code": "adjustment_rate",
        "severity": "HIGH",
    }
    duplicate_adjustment_rule = {
        **adjustment_rule,
        "validation_rule_id": uuid4(),
    }
    prepared_adjustment = PreparedRule(
        rule=adjustment_rule,
        field=adjustment_field,
        configuration={"system_rate": "-5", "tolerance": "0"},
        reported_rate=__import__("decimal").Decimal("-12"),
    )
    prepared_duplicate = PreparedRule(
        rule=duplicate_adjustment_rule,
        field=adjustment_field,
        configuration={"system_rate": "-5", "tolerance": "0"},
        reported_rate=__import__("decimal").Decimal("-12"),
    )
    context = TrustedRunContext(
        document={
            "document_id": uuid4(),
            "version_no": 1,
            "document_group_id": uuid4(),
            "checksum_sha256": "a" * 64,
        },
        extraction_run={
            "extraction_run_id": uuid4(),
            "run_no": 1,
            "extractor_name": "fixture",
            "extractor_version": "1.0",
        },
        fields={"adjustment_rate": adjustment_field, "expert_grade": grade_field},
        official_fields=(adjustment_field, grade_field, unrelated_field),
        rule_version={
            "rule_version_id": rule_version_id,
            "status": "PUBLISHED",
            "effective_from": None,
            "effective_to": None,
            "applicable_case_type": "LAND",
            "applicable_district_code": "F01",
            "selection_priority": 10,
        },
        validation_rules=(adjustment_rule, duplicate_adjustment_rule),
        rule_source={
            "document_id": uuid4(),
            "version_no": 1,
            "checksum_sha256": "b" * 64,
            "effective_from": None,
            "effective_to": None,
        },
        prepared_rules=(prepared_adjustment, prepared_duplicate),
    )

    snapshot = ReviewService._input_snapshot(
        SimpleNamespace(),
        {
            "case_id": str(uuid4()),
            "case_no": "SNAPSHOT",
            "case_title": "Snapshot case",
            "valuation_base_date": "2026-08-26",
            "district_code": "F01",
        },
        context,
    )

    assert [item["extracted_field_id"] for item in snapshot["field_snapshots"]] == [
        "field-adjustment",
        "field-grade",
        "field-description",
    ]
    assert [item["validation_rule_id"] for item in snapshot["validation_rules"]] == [
        str(adjustment_rule["validation_rule_id"]),
        str(duplicate_adjustment_rule["validation_rule_id"]),
    ]
    assert [item["extracted_field_id"] for item in snapshot["checks"]] == [
        "field-adjustment",
        "field-adjustment",
    ]


@pytest.mark.parametrize(
    ("effective_from_sql", "effective_to_sql", "expected_status"),
    [
        ("CURRENT_DATE + 1", "NULL", 409),
        ("NULL", "CURRENT_DATE - 1", 409),
        ("CURRENT_DATE", "CURRENT_DATE + 1", 200),
        ("CURRENT_DATE - 1", "CURRENT_DATE", 200),
        ("NULL", "CURRENT_DATE + 1", 200),
        ("CURRENT_DATE - 1", "NULL", 200),
    ],
)
def test_run_rule_source_effective_period_is_null_aware_and_inclusive(
    authorized_client,
    runnable_review,
    postgres_connection,
    effective_from_sql,
    effective_to_sql,
    expected_status,
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE knowledge.documents
            SET effective_from = {effective_from_sql}, effective_to = {effective_to_sql}
            WHERE document_id = %s
            """,
            (runnable_review.source_document_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == expected_status
    if expected_status == 409:
        assert response.json()["error"]["code"] == "RULE_SOURCE_UNAVAILABLE"
    else:
        assert response.json()["run_status"] == "COMPLETED"


def test_machine_finding_uses_field_code_not_field_path(
    authorized_client, runnable_review, postgres_connection
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )
    assert response.status_code == 200
    finding = response.json()["validation_run_id"]

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT vf.field_code, f.field_path
            FROM valuation.validation_findings vf
            JOIN review.findings f
              ON f.source_validation_finding_id = vf.finding_id
            WHERE vf.validation_run_id = %s
            """,
            (finding,),
        )
        field_code, field_path = cursor.fetchone()

    assert field_code == "adjustment_rate"
    assert field_path == "F01.adjustment_rate"


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
        ({"adjustment_status": "AUTO_EXTRACTED"}, "TRUSTED_INPUT_MISSING"),
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
            SET confirmed_value = '"0"'::jsonb, source_text = '調整率 0%%'
            WHERE extraction_id = %s AND field_name = 'adjustment_rate'
            """,
            (runnable_review.extraction_run_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 200
    adjustment_check = next(
        check
        for check in response.json()["input_snapshot"]["checks"]
        if check["rule_code"] == "ADJUSTMENT_RATE"
    )
    assert adjustment_check["reported_value"] == "0"


def test_run_snapshot_serializes_database_decimal_confidence_exactly(
    authorized_client, runnable_review, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET confidence = %s
            WHERE extracted_field_id = %s
            """,
            (Decimal("0.9876"), runnable_review.adjustment_field_id),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs", json={}
    )

    assert response.status_code == 200
    snapshot = response.json()["input_snapshot"]
    response_confidence = next(
        field["confidence"]
        for field in snapshot["field_snapshots"]
        if field["extracted_field_id"] == str(runnable_review.adjustment_field_id)
    )
    assert response_confidence == "0.9876"
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT input_snapshot
            FROM valuation.validation_runs
            WHERE validation_run_id = %s
            """,
            (response.json()["validation_run_id"],),
        )
        stored_snapshot = cursor.fetchone()[0]
    stored_confidence = next(
        field["confidence"]
        for field in stored_snapshot["field_snapshots"]
        if field["extracted_field_id"] == str(runnable_review.adjustment_field_id)
    )
    assert stored_confidence == "0.9876"


@pytest.mark.parametrize(
    ("field_code", "confirmed_value"),
    [
        ("adjustment_rate", True),
        ("adjustment_rate", ["-5"]),
        ("adjustment_rate", "NaN"),
        ("adjustment_rate", "Infinity"),
        ("adjustment_rate", "1E+999999"),
        ("expert_grade", ["A"]),
    ],
)
def test_run_rejects_invalid_trusted_normalized_value_before_mutation(
    authorized_client,
    runnable_review,
    postgres_connection,
    field_code,
    confirmed_value,
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET confirmed_value = %s::jsonb
            WHERE extraction_id = %s AND field_name = %s
            """,
            (
                json.dumps(confirmed_value),
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
            SET confirmed_value = '"B"'::jsonb
            WHERE extraction_id = %s AND field_name = 'expert_grade'
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
