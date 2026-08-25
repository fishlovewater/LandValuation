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
