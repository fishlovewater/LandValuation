EXPECTED_COLUMNS = {
    ("review", "reviews", "received_at"),
    ("review", "reviews", "due_at"),
    ("review", "reviews", "assigned_reviewer_id"),
    ("review", "reviews", "manual_priority"),
    ("review", "reviews", "current_risk_level"),
    ("review", "reviews", "latest_validation_run_id"),
    ("review", "reviews", "latest_submission_id"),
    ("valuation", "validation_runs", "review_id"),
    ("valuation", "validation_runs", "submission_id"),
    ("valuation", "validation_runs", "input_snapshot"),
    ("valuation", "validation_runs", "model_id"),
    ("valuation", "validation_runs", "prompt_version"),
    ("review", "findings", "source_evidence"),
    ("review", "findings", "comparison_result"),
    ("review", "findings", "recommended_action"),
    ("review", "findings", "ai_reasoning_summary"),
    ("review", "decisions", "request_id"),
}

TRUSTED_INPUT_COLUMNS = {
    ("valuation", "document_extractions", "extraction_id"),
    ("valuation", "document_extractions", "case_id"),
    ("valuation", "document_extractions", "document_id"),
    ("valuation", "document_extractions", "extraction_status"),
    ("valuation", "extracted_fields", "extracted_field_id"),
    ("valuation", "extracted_fields", "case_id"),
    ("valuation", "extracted_fields", "extraction_id"),
    ("valuation", "extracted_fields", "form_code"),
    ("valuation", "extracted_fields", "field_name"),
    ("valuation", "extracted_fields", "confirmed_value"),
    ("valuation", "extracted_fields", "field_status"),
    ("valuation", "extracted_fields", "source_page"),
    ("valuation", "extracted_fields", "source_text"),
    ("valuation", "rule_versions", "applicable_case_type"),
    ("valuation", "rule_versions", "applicable_district_code"),
    ("valuation", "rule_versions", "selection_priority"),
    ("valuation", "rule_versions", "source_document_id"),
}


def test_review_schema_contains_mvp_contract(postgres_connection):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema IN ('review', 'valuation')
            """
        )
        actual = set(cursor.fetchall())

    assert EXPECTED_COLUMNS <= actual


def test_trusted_input_schema_contract(postgres_connection):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'valuation'
            """
        )
        actual = set(cursor.fetchall())

    assert TRUSTED_INPUT_COLUMNS <= actual
    assert not any(
        schema == "valuation" and table == "extraction_runs"
        for schema, table, _column in actual
    )
    assert ("valuation", "extracted_fields", "normalized_value") not in actual
    assert ("valuation", "extracted_fields", "verification_status") not in actual


import uuid

import pytest


@pytest.mark.parametrize(
    ("schema", "table", "column"),
    [
        ("review", "correction_requests", "based_on_validation_run_id"),
        ("review", "correction_requests", "response_document_id"),
        ("review", "correction_requests", "resubmitted_by_user_id"),
        ("review", "correction_request_items", "recheck_outcome"),
        ("review", "urgency_settings", "urgent_days"),
    ],
)
def test_correction_schema_columns_exist(postgres_connection, schema, table, column):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s AND column_name=%s
            """,
            (schema, table, column),
        )
        assert cursor.fetchone() == (1,)


def _seed_review_with_run(cursor):
    """Insert a minimal case/review/run/document graph and return their ids."""
    case_id = uuid.uuid4()
    review_id = uuid.uuid4()
    run_id = uuid.uuid4()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    cursor.execute(
        """
        INSERT INTO auth.users (user_id, username, email, password_hash,
                                display_name, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, 'unused', '結構測試使用者', true, now(), now())
        """,
        (user_id, f"schema-{user_id}", f"{user_id}@example.test"),
    )
    cursor.execute(
        """
        INSERT INTO valuation.cases
            (case_id, case_no, case_title, case_type, valuation_base_date,
             city_code, district_code)
        VALUES (%s, %s, '測試案件', 'LAND', current_date, '01', '001')
        """,
        (case_id, f"CASE-{uuid.uuid4().hex[:8]}"),
    )
    cursor.execute(
        """
        INSERT INTO review.reviews (review_id, case_id, review_type, review_status)
        VALUES (%s, %s, 'SMART_REVIEW', 'REVIEW_REQUIRED')
        """,
        (review_id, case_id),
    )
    cursor.execute(
        """
        INSERT INTO valuation.validation_runs
            (validation_run_id, case_id, run_status, review_id, ruleset_snapshot)
        VALUES (%s, %s, 'COMPLETED', %s, '{"rules": []}'::jsonb)
        """,
        (run_id, case_id, review_id),
    )
    cursor.execute(
        """
        INSERT INTO valuation.documents
            (document_id, case_id, document_type, original_filename, mime_type,
             bucket_name, object_key, checksum_sha256, file_size_bytes, version_no,
             is_active, document_group_id)
        VALUES (%s, %s, 'APPRAISAL_REPORT', 'r.pdf', 'application/pdf',
                'land-valuation', %s, %s, 1, 1, true, %s)
        """,
        (
            document_id,
            case_id,
            f"cases/{case_id}/{uuid.uuid4()}.pdf",
            uuid.uuid4().hex + uuid.uuid4().hex,
            uuid.uuid4(),
        ),
    )
    return review_id, run_id, document_id, user_id


def _insert_request(cursor, review_id, run_id, document_id, user_id, status, request_no):
    request_id = uuid.uuid4()
    sent_at = "now()" if status != "DRAFT" else "NULL"
    cursor.execute(
        f"""
        INSERT INTO review.correction_requests
            (correction_request_id, review_id, request_no, based_on_validation_run_id,
             status, due_at, message, base_document_id, base_document_version,
             created_by_user_id, sent_by_user_id, sent_at)
        VALUES (%s, %s, %s, %s, %s, now() + interval '3 days', 'msg', %s, 1, %s,
                {'%s' if status != 'DRAFT' else 'NULL'},
                {sent_at})
        """,
        (
            (request_id, review_id, request_no, run_id, status, document_id, user_id, user_id)
            if status != "DRAFT"
            else (request_id, review_id, request_no, run_id, status, document_id, user_id)
        ),
    )
    return request_id


def test_only_one_active_correction_request_per_review(postgres_connection):
    postgres_connection.autocommit = False
    try:
        with postgres_connection.cursor() as cursor:
            review_id, run_id, document_id, user_id = _seed_review_with_run(cursor)
            _insert_request(cursor, review_id, run_id, document_id, user_id, "DRAFT", 1)
            with pytest.raises(psycopg_errors_unique()):
                _insert_request(
                    cursor, review_id, run_id, document_id, user_id, "SENT", 2
                )
    finally:
        postgres_connection.rollback()


def test_many_rechecked_requests_are_allowed(postgres_connection):
    postgres_connection.autocommit = False
    try:
        with postgres_connection.cursor() as cursor:
            review_id, run_id, document_id, user_id = _seed_review_with_run(cursor)
            for request_no in (1, 2, 3):
                _insert_recheck_history(
                    cursor, review_id, run_id, document_id, user_id, request_no
                )
    finally:
        postgres_connection.rollback()


def _insert_recheck_history(cursor, review_id, run_id, document_id, user_id, request_no):
    request_id = uuid.uuid4()
    cursor.execute(
        """
        INSERT INTO review.correction_requests
            (correction_request_id, review_id, request_no, based_on_validation_run_id,
             status, due_at, message, base_document_id, base_document_version,
             response_document_id, response_document_version,
             created_by_user_id, sent_by_user_id, sent_at,
             resubmitted_by_user_id, resubmitted_at,
             rechecked_by_user_id, rechecked_at)
        VALUES (%s, %s, %s, %s, 'RECHECKED', now() + interval '3 days', 'msg', %s, 1,
                %s, 2, %s, %s, now(), %s, now(), %s, now())
        """,
        (
            request_id, review_id, request_no, run_id, document_id, document_id,
            user_id, user_id, user_id, user_id,
        ),
    )
    return request_id


def psycopg_errors_unique():
    from psycopg import errors

    return errors.UniqueViolation


def test_review_status_column_accepts_all_workflow_statuses(postgres_connection):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'review'
              AND table_name = 'reviews'
              AND column_name = 'review_status'
            """
        )
        maximum_length = cursor.fetchone()[0]

    assert maximum_length is None or maximum_length >= len("RETURNED_FOR_REVISION")
