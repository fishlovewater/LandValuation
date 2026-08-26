from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


@pytest.fixture
def review_case(postgres_connection):
    user_id, case_id, review_id = uuid4(), uuid4(), uuid4()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'not-used', 'Missing Item Tester', true, now(), now())
            """,
            (user_id, f"missing-{user_id}", f"{user_id}@example.test"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status
            ) VALUES (%s, %s, 'Missing Item Case', 'LAND', CURRENT_DATE,
                      'F', 'F01', 'DRAFT')
            """,
            (case_id, f"MISSING-{str(case_id)[:8]}"),
        )
        cursor.execute(
            """
            INSERT INTO review.reviews (
                review_id, case_id, review_status, started_by_user_id
            ) VALUES (%s, %s, 'PREPROCESSING', %s)
            """,
            (review_id, case_id, user_id),
        )
    postgres_connection.commit()
    yield SimpleNamespace(
        user_id=user_id,
        case_id=case_id,
        review_id=review_id,
        original_document_id=uuid4(),
        source_document_id=uuid4(),
        rule_version_id=uuid4(),
        validation_rule_id=uuid4(),
        extraction_run_id=uuid4(),
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute("DELETE FROM review.missing_items WHERE review_id = %s", (review_id,))
        cursor.execute("DELETE FROM review.reviews WHERE review_id = %s", (review_id,))
        cursor.execute(
            "DELETE FROM valuation.extracted_fields WHERE extraction_run_id IN (SELECT extraction_run_id FROM valuation.extraction_runs WHERE case_id = %s)",
            (case_id,),
        )
        cursor.execute("DELETE FROM valuation.extraction_runs WHERE case_id = %s", (case_id,))
        cursor.execute(
            "DELETE FROM valuation.validation_rules WHERE rule_version_id IN (SELECT rule_version_id FROM valuation.rule_versions WHERE rule_set_code LIKE %s)",
            (f"MISSING_{str(case_id)[:8]}%",),
        )
        cursor.execute(
            "DELETE FROM valuation.rule_versions WHERE rule_set_code LIKE %s",
            (f"MISSING_{str(case_id)[:8]}%",),
        )
        cursor.execute(
            "DELETE FROM knowledge.documents WHERE document_code LIKE %s",
            (f"MISSING-SOURCE-{str(case_id)[:8]}%",),
        )
        cursor.execute("DELETE FROM valuation.form_instances WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.parcels WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.documents WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
    postgres_connection.commit()


@pytest.fixture
def authorized_client(review_case):
    permission = SimpleNamespace(permission_code="review.execute")
    role = SimpleNamespace(role_code="APPRAISER", is_active=True, permissions=[permission])
    user = SimpleNamespace(user_id=review_case.user_id, roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_completeness_check_persists_and_lists_open_missing_items(
    authorized_client, review_case
):
    checked = authorized_client.post(
        f"/api/v1/review/cases/{review_case.review_id}/completeness-check"
    )

    assert checked.status_code == 200
    body = checked.json()
    assert body["ready"] is False
    assert body["review_status"] == "PENDING_MATERIALS"
    assert body["missing_item_count"] == 4
    assert {item["item_code"] for item in body["items"]} == {
        "DOC_ORIGINAL",
        "DOC_LAND_REGISTER",
        "DOC_CADASTRAL_MAP",
        "FIELD_PARCEL_AREA",
    }

    listed = authorized_client.get(
        f"/api/v1/review/cases/{review_case.review_id}/missing-items"
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 4
    assert all(item["status"] == "OPEN" for item in listed.json())


def test_supplement_request_marks_open_items_for_notification(
    authorized_client, review_case
):
    authorized_client.post(
        f"/api/v1/review/cases/{review_case.review_id}/completeness-check"
    )
    due_at = datetime.now(UTC) + timedelta(days=2)

    response = authorized_client.post(
        f"/api/v1/review/cases/{review_case.review_id}/supplement-request",
        json={"due_at": due_at.isoformat()},
    )

    assert response.status_code == 200
    assert len(response.json()) == 4
    assert all(
        item["notification_status"] == "PENDING" for item in response.json()
    )


def add_complete_trusted_inputs(connection, review_case):
    with connection.cursor() as cursor:
        for index, (document_type, document_id) in enumerate(
            (
                ("original", review_case.original_document_id),
                ("land-register", uuid4()),
                ("cadastral-map", uuid4()),
            ),
            start=1,
        ):
            cursor.execute(
                """INSERT INTO valuation.documents (
                    document_id, case_id, document_type, original_filename,
                    mime_type, bucket_name, object_key, checksum_sha256,
                    file_size_bytes, version_no, is_active
                ) VALUES (%s, %s, %s, %s, 'application/pdf', 'land-valuation',
                          %s, %s, 100, 1, true)""",
                (
                    document_id,
                    review_case.case_id,
                    document_type,
                    f"{document_type}.pdf",
                    f"cases/{review_case.case_id}/{document_type}.pdf",
                    str(index) * 64,
                ),
            )
        cursor.execute(
            """INSERT INTO valuation.parcels (
                case_id, district_code, section_name, land_no, area_sqm
            ) VALUES (%s, 'F01', 'Test Section', '1', 100.5)""",
            (review_case.case_id,),
        )
        cursor.execute(
            """INSERT INTO valuation.form_instances (
                form_instance_id, case_id, form_code, version_no, form_status
            ) VALUES (%s, %s, 'F01', 1, 'READY')""",
            (uuid4(), review_case.case_id),
        )
        cursor.execute(
            """INSERT INTO knowledge.documents (
                document_id, document_code, title, document_type,
                original_filename, mime_type, bucket_name, object_key,
                checksum_sha256, file_size_bytes, version_no, effective_from,
                extraction_status, publication_status, approved_by_user_id, approved_at
            ) VALUES (%s, %s, 'Missing Item Rule Source', 'REGULATION', 'source.pdf',
                      'application/pdf', 'land-valuation', %s, %s, 100, 1,
                      CURRENT_DATE, 'COMPLETED', 'PUBLISHED', %s, %s)""",
            (
                review_case.source_document_id,
                f"MISSING-SOURCE-{str(review_case.case_id)[:8]}",
                f"knowledge/{review_case.source_document_id}/source.pdf",
                "a" * 64,
                review_case.user_id,
                datetime.now(UTC),
            ),
        )
        cursor.execute(
            """INSERT INTO valuation.rule_versions (
                rule_version_id, rule_set_code, version_no, version_name,
                effective_from, status, applicable_case_type,
                applicable_district_code, selection_priority, source_document_id
            ) VALUES (%s, %s, 1, 'Missing Item Rules', CURRENT_DATE, 'PUBLISHED',
                      'LAND', 'F01', 10, %s)""",
            (
                review_case.rule_version_id,
                f"MISSING_{str(review_case.case_id)[:8]}",
                review_case.source_document_id,
            ),
        )
        cursor.execute(
            """INSERT INTO valuation.validation_rules (
                validation_rule_id, rule_version_id, rule_code, rule_name,
                target_form_code, target_table, target_field_code, severity,
                rule_expression, message_template, is_active
            ) VALUES (%s, %s, 'ADJUSTMENT_RATE', 'ADJUSTMENT_RATE', 'F01',
                      'comparison', 'adjustment_rate', 'HIGH',
                      '{"system_rate":"-5","tolerance":"0"}', 'Adjustment', true)""",
            (review_case.validation_rule_id, review_case.rule_version_id),
        )
        cursor.execute(
            """INSERT INTO valuation.extraction_runs (
                extraction_run_id, case_id, document_id, document_version, run_no,
                status, extractor_name, started_at, completed_at
            ) VALUES (%s, %s, %s, 1, 1, 'COMPLETED', 'fixture',
                      now() - interval '1 minute', now())""",
            (
                review_case.extraction_run_id,
                review_case.case_id,
                review_case.original_document_id,
            ),
        )
        for field_code, field_path, value_type, raw_text, normalized_value in (
            ("adjustment_rate", "comparables[0].adjustment_rate", "DECIMAL", "Adjustment rate -12%", '"-12"'),
            ("expert_grade", "comparables[0].grade", "TEXT", "Expert grade B", '"B"'),
        ):
            cursor.execute(
                """INSERT INTO valuation.extracted_fields (
                    extracted_field_id, extraction_run_id, field_code, field_path,
                    value_type, raw_text, normalized_value, page_number,
                    verification_status, verified_by_user_id, verified_at, is_official
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 3,
                          'VERIFIED', %s, %s, true)""",
                (
                    uuid4(),
                    review_case.extraction_run_id,
                    field_code,
                    field_path,
                    value_type,
                    raw_text,
                    normalized_value,
                    review_case.user_id,
                    datetime.now(UTC),
                ),
            )
    connection.commit()


def test_recheck_resolves_open_items_without_deleting_history(
    authorized_client, review_case, postgres_connection
):
    authorized_client.post(
        f"/api/v1/review/cases/{review_case.review_id}/completeness-check"
    )
    add_complete_trusted_inputs(postgres_connection, review_case)

    checked = authorized_client.post(
        f"/api/v1/review/cases/{review_case.review_id}/completeness-check"
    )

    assert checked.status_code == 200
    assert checked.json()["ready"] is True
    assert checked.json()["review_status"] == "READY_FOR_REVIEW"
    assert checked.json()["missing_item_count"] == 0
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM review.missing_items WHERE review_id = %s AND status = 'RESOLVED'",
            (review_case.review_id,),
        )
        assert cursor.fetchone()[0] == 4
