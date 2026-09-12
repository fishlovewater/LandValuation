"""Add traceable Day 4 validation and Day 5 event fields.

Revision ID: 20260826_0009
Revises: 20260826_0008
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0009"
down_revision: Union[str, Sequence[str], None] = "20260826_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RULE_VERSION_ID = "d4000000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute("ALTER TABLE valuation.valuations ADD COLUMN request_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX uq_valuations_request ON valuation.valuations(case_id, form_instance_id, valuation_type, request_id) WHERE request_id IS NOT NULL"
    )
    op.execute("ALTER TABLE valuation.validation_runs ADD COLUMN request_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX uq_validation_runs_request ON valuation.validation_runs(case_id, form_instance_id, request_id) WHERE request_id IS NOT NULL"
    )
    op.execute("ALTER TABLE valuation.validation_findings ADD COLUMN request_id uuid")
    op.execute(
        "ALTER TABLE valuation.validation_findings ADD COLUMN created_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute(
        "CREATE INDEX idx_validation_findings_request_id ON valuation.validation_findings(request_id) WHERE request_id IS NOT NULL"
    )
    op.execute("ALTER TABLE history.case_events ADD COLUMN request_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX uq_case_events_request ON history.case_events(case_id, event_type, request_id) WHERE request_id IS NOT NULL"
    )

    op.execute(
        f"""
        INSERT INTO valuation.rule_versions (
            rule_version_id,
            rule_set_code,
            version_no,
            version_name,
            effective_from,
            status,
            source_reference,
            notes
        ) VALUES (
            '{RULE_VERSION_ID}',
            'F03_MVP_VALIDATION',
            1,
            'F03 MVP 製作前檢核 v1',
            DATE '2026-08-26',
            'PUBLISHED',
            '估價書輔助製作系統_後端建置指南 Day 4',
            '固定規則型檢核；不包含第二子系統的智慧審查或風險判斷'
        )
        ON CONFLICT (rule_set_code, version_no) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO valuation.validation_rules (
            validation_rule_id,
            rule_version_id,
            rule_code,
            rule_name,
            target_form_code,
            target_table,
            target_field_code,
            severity,
            rule_expression,
            message_template,
            is_active
        ) VALUES
            ('d4000000-0000-4000-8000-000000000101', '{RULE_VERSION_ID}',
             'F03_REQUIRED_FIELDS', 'F03 必填欄位', 'F03',
             'benchmark_valuations', NULL, 'MISSING_DATA',
             'benchmark_land_id and valuation_base_date are present',
             'F03 缺少必要欄位', true),
            ('d4000000-0000-4000-8000-000000000102', '{RULE_VERSION_ID}',
             'F03_REQUIRED_DOCUMENTS', 'F03 必要文件', 'F03',
             'documents', NULL, 'MISSING_DATA',
             'active land-register and cadastral-map documents exist',
             'F03 缺少必要文件', true),
            ('d4000000-0000-4000-8000-000000000103', '{RULE_VERSION_ID}',
             'F03_WEIGHT_SUM', 'F03 權重範圍與加總', 'F03',
             'benchmark_valuations', 'comparison_weight,income_weight', 'HIGH',
             'weights are between 0 and 1 and sum to 1',
             '比較法與收益法權重必須介於 0 到 1 且合計為 1', true),
            ('d4000000-0000-4000-8000-000000000104', '{RULE_VERSION_ID}',
             'F03_METHOD_INPUTS', 'F03 計算方法輸入', 'F03',
             'benchmark_valuations', 'comparison_price,income_price', 'MISSING_DATA',
             'a price exists for every method with weight greater than zero',
             '權重大於 0 的估價方法必須提供價格', true),
            ('d4000000-0000-4000-8000-000000000105', '{RULE_VERSION_ID}',
             'F03_PRICE_RANGE', 'F03 價格範圍', 'F03',
             'benchmark_valuations', 'comparison_price,income_price,benchmark_land_price', 'HIGH',
             'all supplied prices are non-negative',
             'F03 價格不可小於 0', true),
            ('d4000000-0000-4000-8000-000000000106', '{RULE_VERSION_ID}',
             'F03_CASE_CONSISTENCY', '案件與 F03 一致性', 'F03',
             'benchmark_valuations', 'case_id,form_instance_id,valuation_base_date', 'HIGH',
             'case, form, benchmark land and valuation date are consistent',
             '案件、表單、比準地或估價日期不一致', true),
            ('d4000000-0000-4000-8000-000000000107', '{RULE_VERSION_ID}',
             'F03_CALCULATION_MATCH', 'F03 計算結果一致性', 'F03',
             'valuations', 'unit_price,calculation_snapshot', 'HIGH',
             'latest calculation matches current inputs and formula version',
             '最新計算結果與目前 F03 輸入不一致，請重新計算', true),
            ('d4000000-0000-4000-8000-000000000108', '{RULE_VERSION_ID}',
             'F03_MINIO_OBJECTS', 'F03 文件物件完整性', 'F03',
             'documents', 'object_key', 'HIGH',
             'every active required document metadata row has a MinIO object',
             '必要文件 metadata 對應的 MinIO 物件不存在', true)
        ON CONFLICT (rule_version_id, rule_code) DO NOTHING
        """
    )

    op.execute(
        "COMMENT ON COLUMN valuation.valuations.request_id IS '觸發本次可重現計算的 API request ID'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.validation_runs.request_id IS '觸發本次製作前檢核的 API request ID'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.validation_findings.request_id IS '與檢核執行相同的 API request ID'"
    )
    op.execute(
        "COMMENT ON COLUMN history.case_events.request_id IS '產生此主要案件事件的 API request ID'"
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM valuation.validation_runs
                WHERE rule_version_id = '{RULE_VERSION_ID}'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while Day 4 validation results exist';
            END IF;
        END
        $$
        """
    )
    op.execute(
        f"DELETE FROM valuation.validation_rules WHERE rule_version_id = '{RULE_VERSION_ID}'"
    )
    op.execute(
        f"DELETE FROM valuation.rule_versions WHERE rule_version_id = '{RULE_VERSION_ID}'"
    )
    op.execute("DROP INDEX IF EXISTS history.uq_case_events_request")
    op.execute("ALTER TABLE history.case_events DROP COLUMN request_id")
    op.execute("DROP INDEX IF EXISTS valuation.idx_validation_findings_request_id")
    op.execute("ALTER TABLE valuation.validation_findings DROP COLUMN created_at")
    op.execute("ALTER TABLE valuation.validation_findings DROP COLUMN request_id")
    op.execute("DROP INDEX IF EXISTS valuation.uq_validation_runs_request")
    op.execute("ALTER TABLE valuation.validation_runs DROP COLUMN request_id")
    op.execute("DROP INDEX IF EXISTS valuation.uq_valuations_request")
    op.execute("ALTER TABLE valuation.valuations DROP COLUMN request_id")
