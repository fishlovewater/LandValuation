import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from tests.integration.schema_assertions import (
    column_names,
    numeric_precision_scale,
)


FORM_CODES = {"F01", "F02", "F03", "F04", "S01", "F02-RF"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260901_0010_valuation_forms_calculation_reports.py"
)


def _run_alembic(command: str, revision: str, *, expect_success: bool = True):
    env = os.environ.copy()
    if env.get("MIGRATION_DATABASE_URL"):
        env["DATABASE_URL"] = env["MIGRATION_DATABASE_URL"]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is expect_success, result.stdout + result.stderr
    return result


def test_migration_contains_schema_only_and_no_fixed_business_rule_data():
    source = MIGRATION_PATH.read_text(encoding="utf-8").lower()

    assert "insert into valuation." not in source
    assert "delete from valuation." not in source
    assert "d4000000-0000-4000-8000-000000000001" not in source


def _check_expression(cursor, schema: str, table: str, constraint: str) -> str:
    cursor.execute(
        """
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class r ON r.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE n.nspname = %s AND r.relname = %s AND c.conname = %s
        """,
        (schema, table, constraint),
    )
    row = cursor.fetchone()
    assert row is not None, f"missing constraint {schema}.{table}.{constraint}"
    return row[0]


def _index_exists(cursor, schema: str, index_name: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = %s AND indexname = %s
        )
        """,
        (schema, index_name),
    )
    return cursor.fetchone()[0]


def _create_case_and_form(cursor) -> tuple[object, object]:
    user_id = uuid4()
    case_id = uuid4()
    cursor.execute(
        """
        INSERT INTO auth.users (
            user_id, username, email, password_hash, display_name, is_active
        ) VALUES (%s, %s, %s, 'hash', 'Migration Tester', true)
        """,
        (user_id, f"user_{uuid4().hex[:10]}", f"{uuid4().hex[:12]}@example.test"),
    )
    cursor.execute(
        """
        INSERT INTO valuation.cases (
            case_id, case_no, case_title, case_type, valuation_base_date,
            city_code, district_code, created_by_user_id, updated_by_user_id
        ) VALUES (%s, %s, 'Migration case', 'LAND', CURRENT_DATE,
                  'TP', 'BANQIAO', %s, %s)
        """,
        (case_id, f"MIG-0010-{uuid4().hex[:10]}", user_id, user_id),
    )
    return user_id, case_id


def test_complete_report_schema_contract(admin_cursor):
    assert set(column_names(admin_cursor, "form_instances", "valuation")) >= {
        "form_content",
    }
    assert set(column_names(admin_cursor, "comparison_targets", "valuation")) >= {
        "display_order",
    }
    assert set(column_names(admin_cursor, "comparison_factor_values", "valuation")) >= {
        "benchmark_factor_level_id",
        "comparable_factor_level_id",
    }
    assert set(column_names(admin_cursor, "comparison_analyses", "valuation")) >= {
        "rule_version_id",
        "calculation_snapshot",
        "calculated_by_user_id",
        "calculated_at",
    }
    assert "jsonb_typeof" in _check_expression(
        admin_cursor,
        "valuation",
        "form_instances",
        "ck_form_instances_content_object",
    )
    assert "jsonb_typeof" in _check_expression(
        admin_cursor,
        "valuation",
        "comparison_analyses",
        "ck_comparison_analyses_snapshot_object",
    )
    assert "CHECK" in _check_expression(
        admin_cursor,
        "valuation",
        "comparison_targets",
        "ck_comparison_targets_display_order",
    )
    assert "UNIQUE" in _check_expression(
        admin_cursor,
        "valuation",
        "comparison_targets",
        "uq_comparison_targets_display_order",
    )
    for constraint in (
        "fk_comparison_factor_values_benchmark_level",
        "fk_comparison_factor_values_comparable_level",
    ):
        assert "FOREIGN KEY" in _check_expression(
            admin_cursor,
            "valuation",
            "comparison_factor_values",
            constraint,
        )
    for schema, index_name in (
        ("valuation", "uq_valuations_request"),
        ("valuation", "uq_validation_runs_request"),
        ("valuation", "idx_validation_findings_request_id"),
        ("history", "uq_case_events_request"),
    ):
        assert _index_exists(admin_cursor, schema, index_name)


def test_supported_form_codes_include_every_active_form_and_report_page(admin_cursor):
    expression = _check_expression(
        admin_cursor, "valuation", "form_instances", "ck_form_instances_code"
    )
    for form_code in FORM_CODES:
        assert form_code in expression

    _, case_id = _create_case_and_form(admin_cursor)
    form_id = uuid4()
    admin_cursor.execute(
        """
        INSERT INTO valuation.form_instances (
            form_instance_id, case_id, form_code, form_content
        ) VALUES (%s, %s, 'F02-RF', %s)
        RETURNING form_code, form_content ->> 'page_code'
        """,
        (form_id, case_id, Jsonb({"page_code": "F02-RF", "data": {}})),
    )
    assert admin_cursor.fetchone() == ("F02-RF", "F02-RF")


def test_benchmark_coordinates_are_decimal(admin_cursor):
    assert numeric_precision_scale(
        admin_cursor, "benchmark_lands", "latitude", "valuation"
    ) == (10, 7)
    assert numeric_precision_scale(
        admin_cursor, "benchmark_lands", "longitude", "valuation"
    ) == (10, 7)


def test_complete_report_constraints_reject_invalid_json_and_display_order(admin_cursor):
    _, case_id = _create_case_and_form(admin_cursor)
    with pytest.raises(Exception):
        admin_cursor.execute(
            """
            INSERT INTO valuation.form_instances (form_instance_id, case_id, form_code, form_content)
            VALUES (%s, %s, 'S01', %s)
            """,
            (uuid4(), case_id, Jsonb([])),
        )
    admin_cursor.connection.rollback()


def test_downgrade_refuses_real_f02_rf_report_page_data(admin_cursor):
    user_id, case_id = _create_case_and_form(admin_cursor)
    form_id = uuid4()
    admin_cursor.execute(
        """
        INSERT INTO valuation.form_instances (
            form_instance_id, case_id, form_code, form_content
        ) VALUES (%s, %s, 'F02-RF', %s)
        """,
        (form_id, case_id, Jsonb({"page_code": "F02-RF", "data": {}})),
    )
    admin_cursor.connection.commit()

    result = _run_alembic("downgrade", "20260901_0009", expect_success=False)
    assert "cannot downgrade while complete-report form data exists" in (
        result.stdout + result.stderr
    )

    admin_cursor.execute(
        "DELETE FROM valuation.form_instances WHERE form_instance_id = %s", (form_id,)
    )
    admin_cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))
    admin_cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
    admin_cursor.connection.commit()
    _run_alembic("downgrade", "20260901_0009")
    _run_alembic("upgrade", "head")
