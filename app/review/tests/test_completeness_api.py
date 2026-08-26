from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


@pytest.fixture
def trusted_case(request, postgres_connection):
    options = getattr(request, "param", {})
    with_extraction = options.get("with_extraction", True)
    adjustment_status = options.get("adjustment_status", "VERIFIED")
    source_extraction_status = options.get("source_extraction_status", "COMPLETED")
    source_publication_status = options.get("source_publication_status", "PUBLISHED")
    ids = SimpleNamespace(
        user_id=uuid4(),
        case_id=uuid4(),
        review_id=uuid4(),
        original_document_id=uuid4(),
        source_document_id=uuid4(),
        rule_version_id=uuid4(),
        extraction_run_id=uuid4(),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'not-used', 'Completeness API Tester',
                      true, now(), now())
            """,
            (ids.user_id, f"completeness-{ids.user_id}", f"{ids.user_id}@example.test"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status
            ) VALUES (%s, %s, 'Trusted Completeness Case', 'LAND',
                      CURRENT_DATE, 'F', 'F01', 'DRAFT')
            """,
            (ids.case_id, f"COMPLETE-{str(ids.case_id)[:8]}"),
        )
        cursor.execute(
            """
            INSERT INTO review.reviews (
                review_id, case_id, review_status, started_by_user_id
            ) VALUES (%s, %s, 'PREPROCESSING', %s)
            """,
            (ids.review_id, ids.case_id, ids.user_id),
        )
        for document_id, document_type, filename, checksum in (
            (ids.original_document_id, "original", "original.pdf", "1" * 64),
            (uuid4(), "land-register", "land-register.pdf", "2" * 64),
            (uuid4(), "cadastral-map", "cadastral-map.pdf", "3" * 64),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.documents (
                    document_id, case_id, document_type, original_filename,
                    mime_type, bucket_name, object_key, checksum_sha256,
                    file_size_bytes, version_no, is_active
                ) VALUES (%s, %s, %s, %s, 'application/pdf', 'land-valuation',
                          %s, %s, 100, 1, true)
                """,
                (
                    document_id,
                    ids.case_id,
                    document_type,
                    filename,
                    f"cases/{ids.case_id}/{filename}",
                    checksum,
                ),
            )
        cursor.execute(
            """
            INSERT INTO valuation.parcels (
                case_id, district_code, section_name, land_no, area_sqm
            ) VALUES (%s, 'F01', '測試段', '1', 100.5)
            """,
            (ids.case_id,),
        )
        cursor.execute(
            """
            INSERT INTO valuation.form_instances (
                form_instance_id, case_id, form_code, version_no, form_status
            ) VALUES (%s, %s, 'F01', 1, 'READY')
            """,
            (uuid4(), ids.case_id),
        )
        cursor.execute(
            """
            INSERT INTO knowledge.documents (
                document_id, document_code, title, document_type,
                original_filename, mime_type, bucket_name, object_key,
                checksum_sha256, file_size_bytes, version_no, effective_from,
                extraction_status, publication_status, approved_by_user_id,
                approved_at
            ) VALUES (%s, %s, 'Trusted Source', 'REGULATION', 'source.pdf',
                      'application/pdf', 'land-valuation', %s, %s, 100, 1,
                      CURRENT_DATE, %s, %s, %s, %s)
            """,
            (
                ids.source_document_id,
                f"COMPLETE-SOURCE-{str(ids.source_document_id)[:8]}",
                f"knowledge/{ids.source_document_id}/source.pdf",
                "a" * 64,
                source_extraction_status,
                source_publication_status,
                ids.user_id if source_publication_status == "PUBLISHED" else None,
                datetime.now(UTC)
                if source_publication_status == "PUBLISHED"
                else None,
            ),
        )
        cursor.execute(
            """
            INSERT INTO valuation.rule_versions (
                rule_version_id, rule_set_code, version_no, version_name,
                effective_from, status, applicable_case_type,
                applicable_district_code, selection_priority, source_document_id
            ) VALUES (%s, %s, 1, 'Trusted Completeness Rules', CURRENT_DATE,
                      'PUBLISHED', 'LAND', 'F01', 10, %s)
            """,
            (
                ids.rule_version_id,
                f"COMPLETE-RULES-{str(ids.rule_version_id)[:8]}",
                ids.source_document_id,
            ),
        )
        for rule_code, field_code, expression in (
            (
                "ADJUSTMENT_RATE",
                "adjustment_rate",
                '{"system_rate":"-5","tolerance":"0"}',
            ),
            ("EXPERT_GRADE", "expert_grade", '{"system_grade":"A"}'),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.validation_rules (
                    validation_rule_id, rule_version_id, rule_code, rule_name,
                    target_table, target_field_code, severity, rule_expression,
                    message_template, is_active
                ) VALUES (%s, %s, %s, %s, 'comparison', %s, 'HIGH', %s, %s, true)
                """,
                (
                    uuid4(),
                    ids.rule_version_id,
                    rule_code,
                    rule_code,
                    field_code,
                    expression,
                    rule_code,
                ),
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
                    "調整率 -12%",
                    '"-12"',
                    adjustment_status,
                ),
                ("expert_grade", "TEXT", "級距 A", '"A"', "VERIFIED"),
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
        cursor.execute("DELETE FROM review.missing_items WHERE review_id = %s", (ids.review_id,))
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
            "DELETE FROM valuation.validation_rules WHERE rule_version_id = %s",
            (ids.rule_version_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.rule_versions WHERE rule_version_id = %s",
            (ids.rule_version_id,),
        )
        cursor.execute("DELETE FROM knowledge.documents WHERE document_id = %s", (ids.source_document_id,))
        cursor.execute("DELETE FROM valuation.form_instances WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.parcels WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.documents WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (ids.case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (ids.user_id,))
    postgres_connection.commit()


@pytest.fixture
def authorized_client(trusted_case):
    permission = SimpleNamespace(permission_code="review.execute")
    role = SimpleNamespace(
        role_code="APPRAISER", is_active=True, permissions=[permission]
    )
    user = SimpleNamespace(user_id=trusted_case.user_id, roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "trusted_case", [{"with_extraction": False}], indirect=True
)
def test_completeness_blocks_when_completed_extraction_is_missing(
    authorized_client, trusted_case
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "TRUSTED_INPUT_MISSING" in {
        item["item_code"] for item in response.json()["items"]
    }


@pytest.mark.parametrize(
    "trusted_case", [{"adjustment_status": "AUTO_EXTRACTED"}], indirect=True
)
def test_completeness_blocks_auto_extracted_high_impact_field(
    authorized_client, trusted_case
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "TRUSTED_INPUT_UNVERIFIED_ADJUSTMENT_RATE" in {
        item["item_code"] for item in response.json()["items"]
    }


@pytest.mark.parametrize(
    "trusted_case", [{"source_publication_status": "DRAFT"}], indirect=True
)
def test_completeness_blocks_draft_rule_source(
    authorized_client, trusted_case, postgres_connection
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "RULE_SOURCE_UNAVAILABLE" in {
        item["item_code"] for item in response.json()["items"]
    }
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
            (trusted_case.review_id,),
        )
        assert cursor.fetchone()[0] == 0


@pytest.mark.parametrize(
    "trusted_case", [{"source_extraction_status": "PENDING"}], indirect=True
)
def test_completeness_blocks_unextracted_published_rule_source(
    authorized_client, trusted_case, postgres_connection
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "RULE_SOURCE_UNAVAILABLE" in {
        item["item_code"] for item in response.json()["items"]
    }
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
            (trusted_case.review_id,),
        )
        assert cursor.fetchone()[0] == 0


@pytest.mark.parametrize(
    ("effective_from_sql", "effective_to_sql"),
    [
        ("CURRENT_DATE + 1", "NULL"),
        ("NULL", "CURRENT_DATE - 1"),
    ],
)
def test_completeness_blocks_rule_source_outside_case_effective_period(
    authorized_client,
    trusted_case,
    postgres_connection,
    effective_from_sql,
    effective_to_sql,
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE knowledge.documents
            SET effective_from = {effective_from_sql}, effective_to = {effective_to_sql}
            WHERE document_id = %s
            """,
            (trusted_case.source_document_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "RULE_SOURCE_UNAVAILABLE" in {
        item["item_code"] for item in response.json()["items"]
    }


@pytest.mark.parametrize("trusted_case", [{}], indirect=True)
def test_completeness_accepts_verified_high_impact_fields(
    authorized_client, trusted_case
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "READY_FOR_REVIEW"
    assert response.json()["items"] == []


def test_completeness_blocks_invalid_rule_configuration(
    authorized_client, trusted_case, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE valuation.validation_rules SET rule_expression = '[]' "
            "WHERE rule_version_id = %s AND rule_code = 'ADJUSTMENT_RATE'",
            (trusted_case.rule_version_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "RULE_CONFIGURATION_INVALID" in {
        item["item_code"] for item in response.json()["items"]
    }


def test_completeness_blocks_invalid_trusted_normalized_value(
    authorized_client, trusted_case, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET normalized_value = 'true'::jsonb
            WHERE extraction_run_id = %s AND field_code = 'adjustment_rate'
            """,
            (trusted_case.extraction_run_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "TRUSTED_INPUT_UNVERIFIED_ADJUSTMENT_RATE" in {
        item["item_code"] for item in response.json()["items"]
    }


def test_completeness_prioritizes_invalid_rule_contract_over_missing_field(
    authorized_client, trusted_case, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.validation_rules
            SET rule_code = 'UNSUPPORTED_RULE', target_field_code = 'missing_field'
            WHERE rule_version_id = %s AND rule_code = 'ADJUSTMENT_RATE'
            """,
            (trusted_case.rule_version_id,),
        )
    postgres_connection.commit()

    response = authorized_client.post(
        f"/api/v1/review/cases/{trusted_case.review_id}/completeness-check"
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "RULE_CONFIGURATION_INVALID" in {
        item["item_code"] for item in response.json()["items"]
    }
