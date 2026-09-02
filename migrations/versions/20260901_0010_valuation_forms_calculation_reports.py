"""Add valuation forms, calculation traceability, and complete-report schema.

Revision ID: 20260901_0010
Revises: 20260901_0009
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260901_0010"
down_revision: Union[str, Sequence[str], None] = "20260901_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FORM_CODES = "'F01', 'F02', 'F03', 'F04', 'S01', 'F02-RF'"
PRE_0010_EXTRACTED_FIELD_CODES = "'F01', 'F02', 'F02-RF', 'F03', 'F04'"


def upgrade() -> None:
    op.execute("ALTER TABLE valuation.valuations ADD COLUMN request_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX uq_valuations_request ON valuation.valuations "
        "(case_id, form_instance_id, valuation_type, request_id) "
        "WHERE request_id IS NOT NULL"
    )
    op.execute("ALTER TABLE valuation.validation_runs ADD COLUMN request_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX uq_validation_runs_request ON valuation.validation_runs "
        "(case_id, form_instance_id, request_id) WHERE request_id IS NOT NULL"
    )
    op.execute("ALTER TABLE valuation.validation_findings ADD COLUMN request_id uuid")
    op.execute(
        "ALTER TABLE valuation.validation_findings "
        "ADD COLUMN created_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute(
        "CREATE INDEX idx_validation_findings_request_id "
        "ON valuation.validation_findings(request_id) WHERE request_id IS NOT NULL"
    )
    op.execute("ALTER TABLE history.case_events ADD COLUMN request_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX uq_case_events_request ON history.case_events "
        "(case_id, event_type, request_id) WHERE request_id IS NOT NULL"
    )

    op.execute(
        "COMMENT ON COLUMN valuation.valuations.request_id IS "
        "'觸發本次可重現計算的 API request ID'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.validation_runs.request_id IS "
        "'觸發本次製作前檢核的 API request ID'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.validation_findings.request_id IS "
        "'與檢核執行相同的 API request ID'"
    )
    op.execute(
        "COMMENT ON COLUMN history.case_events.request_id IS "
        "'產生此主要案件事件的 API request ID'"
    )

    op.execute(
        "ALTER TABLE valuation.form_instances "
        "ADD COLUMN form_content jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE valuation.form_instances "
        "ADD CONSTRAINT ck_form_instances_content_object "
        "CHECK (jsonb_typeof(form_content) = 'object')"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.form_instances.form_content IS "
        "'S01、F02-RF、F02 等表單的版本化完整 JSON 內容；正式計算仍使用結構化權威資料表'"
    )
    op.execute("ALTER TABLE valuation.form_instances DROP CONSTRAINT ck_form_instances_code")
    op.execute(
        "ALTER TABLE valuation.form_instances "
        f"ADD CONSTRAINT ck_form_instances_code CHECK (form_code IN ({FORM_CODES}))"
    )
    op.execute(
        "ALTER TABLE valuation.validation_rules "
        "DROP CONSTRAINT ck_validation_rules_form_code"
    )
    op.execute(
        "ALTER TABLE valuation.validation_rules "
        f"ADD CONSTRAINT ck_validation_rules_form_code "
        f"CHECK (target_form_code IS NULL OR target_form_code IN ({FORM_CODES}))"
    )
    op.execute(
        "ALTER TABLE valuation.extracted_fields "
        "DROP CONSTRAINT ck_extracted_fields_form_code"
    )
    op.execute(
        "ALTER TABLE valuation.extracted_fields "
        f"ADD CONSTRAINT ck_extracted_fields_form_code CHECK (form_code IN ({FORM_CODES}))"
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM valuation.comparison_targets) THEN
                RAISE EXCEPTION
                    'comparison_targets contains rows; assign an explicit display order before upgrade';
            END IF;
        END
        $$
        """
    )
    op.execute("ALTER TABLE valuation.comparison_targets ADD COLUMN display_order integer NOT NULL")
    op.execute(
        "ALTER TABLE valuation.comparison_targets "
        "ADD CONSTRAINT ck_comparison_targets_display_order CHECK (display_order > 0)"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_targets "
        "ADD CONSTRAINT uq_comparison_targets_display_order "
        "UNIQUE (comparison_analysis_id, display_order)"
    )

    op.execute(
        "ALTER TABLE valuation.comparison_factor_values "
        "ADD COLUMN benchmark_factor_level_id uuid"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_factor_values "
        "ADD COLUMN comparable_factor_level_id uuid"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_factor_values "
        "ADD CONSTRAINT fk_comparison_factor_values_benchmark_level "
        "FOREIGN KEY (benchmark_factor_level_id) "
        "REFERENCES valuation.factor_levels(factor_level_id) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_factor_values "
        "ADD CONSTRAINT fk_comparison_factor_values_comparable_level "
        "FOREIGN KEY (comparable_factor_level_id) "
        "REFERENCES valuation.factor_levels(factor_level_id) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT"
    )
    op.execute(
        "CREATE INDEX idx_comparison_factor_values_benchmark_level "
        "ON valuation.comparison_factor_values(benchmark_factor_level_id) "
        "WHERE benchmark_factor_level_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_comparison_factor_values_comparable_level "
        "ON valuation.comparison_factor_values(comparable_factor_level_id) "
        "WHERE comparable_factor_level_id IS NOT NULL"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.comparison_factor_values.factor_level_id IS "
        "'0010 前的相容欄位；新完整查估書不得使用此欄推測比準地或比較標的級距'"
    )

    op.execute("ALTER TABLE valuation.comparison_analyses ADD COLUMN rule_version_id uuid")
    op.execute(
        "ALTER TABLE valuation.comparison_analyses "
        "ADD COLUMN calculation_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_analyses ADD COLUMN calculated_by_user_id uuid"
    )
    op.execute("ALTER TABLE valuation.comparison_analyses ADD COLUMN calculated_at timestamptz")
    op.execute(
        "ALTER TABLE valuation.comparison_analyses "
        "ADD CONSTRAINT fk_comparison_analyses_rule_version "
        "FOREIGN KEY (rule_version_id) REFERENCES valuation.rule_versions(rule_version_id) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_analyses "
        "ADD CONSTRAINT fk_comparison_analyses_calculated_by "
        "FOREIGN KEY (calculated_by_user_id) REFERENCES auth.users(user_id) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_analyses "
        "ADD CONSTRAINT ck_comparison_analyses_snapshot_object "
        "CHECK (jsonb_typeof(calculation_snapshot) = 'object')"
    )
    op.execute(
        "ALTER TABLE valuation.comparison_analyses "
        "ADD CONSTRAINT ck_comparison_analyses_calculation_trace CHECK ("
        "(calculated_at IS NULL AND calculated_by_user_id IS NULL "
        "AND calculation_snapshot = '{}'::jsonb) "
        "OR (calculated_at IS NOT NULL AND calculated_by_user_id IS NOT NULL "
        "AND rule_version_id IS NOT NULL AND calculation_snapshot <> '{}'::jsonb))"
    )

    op.execute("ALTER TABLE valuation.assistant_sessions DROP CONSTRAINT ck_assistant_sessions_form")
    op.execute(
        "ALTER TABLE valuation.assistant_sessions "
        "ALTER COLUMN selected_form_type TYPE varchar(50)"
    )
    op.execute(
        "ALTER TABLE valuation.assistant_sessions "
        "ADD CONSTRAINT ck_assistant_sessions_form "
        "CHECK (selected_form_type IN ('F03', 'REPORT_COMPARISON_COMMERCIAL'))"
    )

    op.execute(
        "ALTER TABLE valuation.benchmark_lands "
        "ADD COLUMN latitude numeric(10, 7)"
    )
    op.execute(
        "ALTER TABLE valuation.benchmark_lands "
        "ADD COLUMN longitude numeric(10, 7)"
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM valuation.valuations WHERE request_id IS NOT NULL)
               OR EXISTS (SELECT 1 FROM valuation.validation_runs WHERE request_id IS NOT NULL)
               OR EXISTS (SELECT 1 FROM valuation.validation_findings WHERE request_id IS NOT NULL)
               OR EXISTS (SELECT 1 FROM history.case_events WHERE request_id IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade while request-correlated valuation data exists';
            END IF;
            IF EXISTS (
                SELECT 1 FROM valuation.form_instances
                WHERE form_code IN ('S01', 'F02-RF')
                   OR form_content <> '{{}}'::jsonb
            ) THEN
                RAISE EXCEPTION 'cannot downgrade while complete-report form data exists';
            END IF;
            IF EXISTS (SELECT 1 FROM valuation.comparison_targets) THEN
                RAISE EXCEPTION 'cannot downgrade while ordered comparison targets exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM valuation.comparison_factor_values
                WHERE benchmark_factor_level_id IS NOT NULL
                   OR comparable_factor_level_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'cannot downgrade while explicit factor levels exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM valuation.comparison_analyses
                WHERE rule_version_id IS NOT NULL
                   OR calculation_snapshot <> '{{}}'::jsonb
                   OR calculated_by_user_id IS NOT NULL
                   OR calculated_at IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'cannot downgrade while comparison calculation evidence exists';
            END IF;
            IF EXISTS (SELECT 1 FROM valuation.extracted_fields WHERE form_code = 'S01')
               OR EXISTS (SELECT 1 FROM valuation.validation_rules WHERE target_form_code = 'S01')
               OR EXISTS (
                    SELECT 1 FROM valuation.assistant_sessions
                    WHERE selected_form_type = 'REPORT_COMPARISON_COMMERCIAL'
               ) THEN
                RAISE EXCEPTION 'cannot downgrade while complete-report workflow references exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM valuation.benchmark_lands
                WHERE latitude IS NOT NULL OR longitude IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'cannot downgrade while benchmark coordinates exist';
            END IF;
        END
        $$
        """
    )

    op.execute("ALTER TABLE valuation.benchmark_lands DROP COLUMN longitude")
    op.execute("ALTER TABLE valuation.benchmark_lands DROP COLUMN latitude")

    op.execute("ALTER TABLE valuation.assistant_sessions DROP CONSTRAINT ck_assistant_sessions_form")
    op.execute(
        "ALTER TABLE valuation.assistant_sessions "
        "ALTER COLUMN selected_form_type TYPE varchar(10)"
    )
    op.execute(
        "ALTER TABLE valuation.assistant_sessions "
        "ADD CONSTRAINT ck_assistant_sessions_form CHECK (selected_form_type = 'F03')"
    )

    op.execute("ALTER TABLE valuation.comparison_analyses DROP CONSTRAINT ck_comparison_analyses_calculation_trace")
    op.execute("ALTER TABLE valuation.comparison_analyses DROP CONSTRAINT ck_comparison_analyses_snapshot_object")
    op.execute("ALTER TABLE valuation.comparison_analyses DROP CONSTRAINT fk_comparison_analyses_calculated_by")
    op.execute("ALTER TABLE valuation.comparison_analyses DROP CONSTRAINT fk_comparison_analyses_rule_version")
    op.execute(
        "ALTER TABLE valuation.comparison_analyses "
        "DROP COLUMN calculated_at, DROP COLUMN calculated_by_user_id, "
        "DROP COLUMN calculation_snapshot, DROP COLUMN rule_version_id"
    )

    op.execute("DROP INDEX valuation.idx_comparison_factor_values_comparable_level")
    op.execute("DROP INDEX valuation.idx_comparison_factor_values_benchmark_level")
    op.execute("ALTER TABLE valuation.comparison_factor_values DROP CONSTRAINT fk_comparison_factor_values_comparable_level")
    op.execute("ALTER TABLE valuation.comparison_factor_values DROP CONSTRAINT fk_comparison_factor_values_benchmark_level")
    op.execute(
        "ALTER TABLE valuation.comparison_factor_values "
        "DROP COLUMN comparable_factor_level_id, DROP COLUMN benchmark_factor_level_id"
    )

    op.execute("ALTER TABLE valuation.comparison_targets DROP CONSTRAINT uq_comparison_targets_display_order")
    op.execute("ALTER TABLE valuation.comparison_targets DROP CONSTRAINT ck_comparison_targets_display_order")
    op.execute("ALTER TABLE valuation.comparison_targets DROP COLUMN display_order")

    op.execute("ALTER TABLE valuation.extracted_fields DROP CONSTRAINT ck_extracted_fields_form_code")
    # 0009 already permits F02-RF extraction candidates.  Do not regress that
    # canonical-extraction contract while removing only the new S01 support.
    op.execute(
        "ALTER TABLE valuation.extracted_fields "
        f"ADD CONSTRAINT ck_extracted_fields_form_code "
        f"CHECK (form_code IN ({PRE_0010_EXTRACTED_FIELD_CODES}))"
    )
    op.execute("ALTER TABLE valuation.validation_rules DROP CONSTRAINT ck_validation_rules_form_code")
    op.execute(
        "ALTER TABLE valuation.validation_rules "
        "ADD CONSTRAINT ck_validation_rules_form_code "
        "CHECK (target_form_code IS NULL OR target_form_code IN ('F01', 'F02', 'F03', 'F04'))"
    )
    op.execute("ALTER TABLE valuation.form_instances DROP CONSTRAINT ck_form_instances_code")
    op.execute(
        "ALTER TABLE valuation.form_instances "
        "ADD CONSTRAINT ck_form_instances_code CHECK (form_code IN ('F01', 'F02', 'F03', 'F04'))"
    )
    op.execute("ALTER TABLE valuation.form_instances DROP CONSTRAINT ck_form_instances_content_object")
    op.execute("ALTER TABLE valuation.form_instances DROP COLUMN form_content")

    op.execute("DROP INDEX history.uq_case_events_request")
    op.execute("ALTER TABLE history.case_events DROP COLUMN request_id")
    op.execute("DROP INDEX valuation.idx_validation_findings_request_id")
    op.execute("ALTER TABLE valuation.validation_findings DROP COLUMN created_at")
    op.execute("ALTER TABLE valuation.validation_findings DROP COLUMN request_id")
    op.execute("DROP INDEX valuation.uq_validation_runs_request")
    op.execute("ALTER TABLE valuation.validation_runs DROP COLUMN request_id")
    op.execute("DROP INDEX valuation.uq_valuations_request")
    op.execute("ALTER TABLE valuation.valuations DROP COLUMN request_id")
