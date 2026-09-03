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


def test_downgrade_refuses_real_f02_rf_report_page_data(
    admin_cursor, migration_roundtrip
):
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

    result = migration_roundtrip(
        "downgrade", "20260901_0009", expect_success=False
    )
    assert "cannot downgrade while complete-report form data exists" in (
        result.stdout + result.stderr
    )

    admin_cursor.execute(
        "DELETE FROM valuation.form_instances WHERE form_instance_id = %s", (form_id,)
    )
    admin_cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))
    admin_cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
    admin_cursor.connection.commit()
    migration_roundtrip("downgrade", "20260901_0009")
    migration_roundtrip("upgrade", "head")


def test_display_order_constraints_are_per_analysis(admin_cursor):
    _, case_id = _create_case_and_form(admin_cursor)
    parcel_id, benchmark_land_id = uuid4(), uuid4()
    admin_cursor.execute(
        """
        INSERT INTO valuation.parcels (
            parcel_id, case_id, district_code, section_name, land_no, area_sqm
        ) VALUES (%s, %s, 'BANQIAO', 'Test Section', %s, 100)
        """,
        (parcel_id, case_id, f"{uuid4().hex[:8]}"),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.benchmark_lands (
            benchmark_land_id, case_id, parcel_id, benchmark_land_no, price_zone_no
        ) VALUES (%s, %s, %s, %s, 'ZONE-1')
        """,
        (benchmark_land_id, case_id, parcel_id, f"B-{uuid4().hex[:8]}"),
    )

    first_analysis, second_analysis = uuid4(), uuid4()
    admin_cursor.execute(
        """
        INSERT INTO valuation.comparison_analyses (
            comparison_analysis_id, case_id, benchmark_land_id, valuation_base_date
        ) VALUES (%s, %s, %s, '2026-01-01'), (%s, %s, %s, '2026-01-01')
        """,
        (
            first_analysis,
            case_id,
            benchmark_land_id,
            second_analysis,
            case_id,
            benchmark_land_id,
        ),
    )

    transaction_ids = (uuid4(), uuid4(), uuid4())
    for transaction_id in transaction_ids:
        admin_cursor.execute(
            """
            INSERT INTO valuation.transaction_cases (
                transaction_id, case_id, transaction_no, transaction_date,
                transaction_total_price
            ) VALUES (%s, %s, %s, '2026-01-01', 100)
            """,
            (transaction_id, case_id, f"T-{uuid4().hex[:8]}"),
        )

    def insert_target(analysis_id, transaction_id):
        admin_cursor.execute(
            """
            INSERT INTO valuation.comparison_targets (
                comparison_target_id, case_id, comparison_analysis_id,
                transaction_id, normal_unit_price_snapshot,
                transaction_date_snapshot, display_order
            ) VALUES (%s, %s, %s, %s, '100', '2026-01-01', 1)
            """,
            (uuid4(), case_id, analysis_id, transaction_id),
        )

    insert_target(first_analysis, transaction_ids[0])
    admin_cursor.execute("SAVEPOINT duplicate_display_order")
    try:
        with pytest.raises(Exception):
            insert_target(first_analysis, transaction_ids[1])
    finally:
        admin_cursor.execute("ROLLBACK TO SAVEPOINT duplicate_display_order")
        admin_cursor.execute("RELEASE SAVEPOINT duplicate_display_order")

    insert_target(second_analysis, transaction_ids[2])
    admin_cursor.execute(
        "SELECT count(*) FROM valuation.comparison_targets "
        "WHERE (comparison_analysis_id, display_order) IN ((%s, 1), (%s, 1))",
        (first_analysis, second_analysis),
    )
    assert admin_cursor.fetchone()[0] == 2


def test_upgrade_backfills_existing_targets_by_stable_target_id(
    admin_cursor, migration_roundtrip
):
    migration_roundtrip("downgrade", "20260901_0009")

    user_id, case_id = _create_case_and_form(admin_cursor)
    parcel_id, benchmark_land_id, analysis_id = uuid4(), uuid4(), uuid4()
    admin_cursor.execute(
        """
        INSERT INTO valuation.parcels (
            parcel_id, case_id, district_code, section_name, land_no, area_sqm
        ) VALUES (%s, %s, 'BANQIAO', 'Test Section', %s, 100)
        """,
        (parcel_id, case_id, f"{uuid4().hex[:8]}"),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.benchmark_lands (
            benchmark_land_id, case_id, parcel_id, benchmark_land_no, price_zone_no
        ) VALUES (%s, %s, %s, %s, 'ZONE-1')
        """,
        (benchmark_land_id, case_id, parcel_id, f"B-{uuid4().hex[:8]}"),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.comparison_analyses (
            comparison_analysis_id, case_id, benchmark_land_id, valuation_base_date
        ) VALUES (%s, %s, %s, '2026-01-01')
        """,
        (analysis_id, case_id, benchmark_land_id),
    )
    target_ids = sorted((uuid4(), uuid4(), uuid4()), key=str)
    transaction_ids = (uuid4(), uuid4(), uuid4())
    for target_id, transaction_id in zip(reversed(target_ids), transaction_ids):
        admin_cursor.execute(
            """
            INSERT INTO valuation.transaction_cases (
                transaction_id, case_id, transaction_no, transaction_date,
                transaction_total_price
            ) VALUES (%s, %s, %s, '2026-01-01', 100)
            """,
            (transaction_id, case_id, f"T-{uuid4().hex[:8]}"),
        )
        admin_cursor.execute(
            "INSERT INTO valuation.comparison_targets (comparison_target_id, case_id, comparison_analysis_id, transaction_id, normal_unit_price_snapshot, transaction_date_snapshot) VALUES (%s, %s, %s, %s, %s, %s)",
            (target_id, case_id, analysis_id, transaction_id, "100", "2026-01-01"),
        )
    admin_cursor.connection.commit()
    migration_roundtrip("upgrade", "head")
    admin_cursor.execute(
        "SELECT comparison_target_id, display_order, normal_unit_price_snapshot FROM valuation.comparison_targets WHERE comparison_analysis_id = %s ORDER BY display_order",
        (analysis_id,),
    )
    assert admin_cursor.fetchall() == [(target_id, index, 100) for index, target_id in enumerate(target_ids, 1)]
    admin_cursor.execute(
        "DELETE FROM valuation.comparison_targets WHERE comparison_analysis_id = %s",
        (analysis_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.comparison_analyses WHERE comparison_analysis_id = %s",
        (analysis_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.transaction_cases WHERE case_id = %s",
        (case_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.benchmark_lands WHERE benchmark_land_id = %s",
        (benchmark_land_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.parcels WHERE parcel_id = %s", (parcel_id,)
    )
    admin_cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))
    admin_cursor.execute(
        "DELETE FROM auth.users WHERE user_id = %s", (user_id,)
    )
    admin_cursor.connection.commit()


def test_downgrade_blocks_f02_rf_validation_rule_before_schema_drop(
    admin_cursor, migration_roundtrip
):
    rule_id = uuid4()
    rule_version_id = uuid4()
    admin_cursor.execute(
        """
        INSERT INTO valuation.rule_versions (
            rule_version_id, rule_set_code, version_no, version_name,
            effective_from, status
        ) VALUES (%s, %s, 1, 'Migration test', CURRENT_DATE, 'DRAFT')
        """,
        (rule_version_id, f"MIG-0010-{uuid4().hex[:12]}"),
    )
    admin_cursor.execute(
        "INSERT INTO valuation.validation_rules (validation_rule_id, rule_version_id, rule_code, rule_name, target_form_code, target_table, severity, rule_expression, message_template, is_active) VALUES (%s, %s, %s, 'rule', 'F02-RF', 'forms', 'HIGH', 'true', 'blocked', true)",
        (rule_id, rule_version_id, f"MIG-{uuid4().hex[:12]}"),
    )
    admin_cursor.connection.commit()
    result = migration_roundtrip(
        "downgrade", "20260901_0009", expect_success=False
    )
    assert "cannot downgrade while complete-report workflow references exist" in (result.stdout + result.stderr)
    assert "form_content" in column_names(admin_cursor, "form_instances", "valuation")
    admin_cursor.execute("DELETE FROM valuation.validation_rules WHERE validation_rule_id = %s", (rule_id,))
    admin_cursor.execute(
        "DELETE FROM valuation.rule_versions WHERE rule_version_id = %s",
        (rule_version_id,),
    )
    admin_cursor.connection.commit()
