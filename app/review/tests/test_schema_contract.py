EXPECTED_COLUMNS = {
    ("review", "reviews", "received_at"),
    ("review", "reviews", "due_at"),
    ("review", "reviews", "assigned_reviewer_id"),
    ("review", "reviews", "manual_priority"),
    ("review", "reviews", "current_risk_level"),
    ("review", "reviews", "latest_validation_run_id"),
    ("valuation", "validation_runs", "review_id"),
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
    ("valuation", "extraction_runs", "extraction_run_id"),
    ("valuation", "extraction_runs", "document_version"),
    ("valuation", "extraction_runs", "status"),
    ("valuation", "extracted_fields", "extracted_field_id"),
    ("valuation", "extracted_fields", "normalized_value"),
    ("valuation", "extracted_fields", "verification_status"),
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
