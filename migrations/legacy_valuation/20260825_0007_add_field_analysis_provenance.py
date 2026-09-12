"""Add AI field-analysis provenance to extracted candidates.

Revision ID: 20260825_0007
Revises: 20260825_0006
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260825_0007"
down_revision: Union[str, Sequence[str], None] = "20260825_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.extracted_fields
            ADD COLUMN analysis_provider varchar(20),
            ADD COLUMN model_id varchar(200),
            ADD COLUMN prompt_version varchar(100)
        """
    )
    op.execute(
        """
        UPDATE valuation.extracted_fields
        SET analysis_provider = 'RULE'
        WHERE analysis_provider IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE valuation.extracted_fields
            ALTER COLUMN analysis_provider SET DEFAULT 'RULE',
            ALTER COLUMN analysis_provider SET NOT NULL,
            ADD CONSTRAINT ck_extracted_fields_analysis_provider
                CHECK (analysis_provider IN ('RULE', 'BEDROCK')),
            ADD CONSTRAINT ck_extracted_fields_analysis_provenance CHECK (
                (analysis_provider = 'RULE'
                    AND model_id IS NULL
                    AND prompt_version IS NULL)
                OR
                (analysis_provider = 'BEDROCK'
                    AND nullif(btrim(model_id), '') IS NOT NULL
                    AND nullif(btrim(prompt_version), '') IS NOT NULL)
            )
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN valuation.extracted_fields.analysis_provider IS
            '候選欄位產生方式：固定規則或 Bedrock 語意辨識';
        COMMENT ON COLUMN valuation.extracted_fields.model_id IS
            'Bedrock 候選欄位使用的模型 ID；固定規則為 NULL';
        COMMENT ON COLUMN valuation.extracted_fields.prompt_version IS
            'Bedrock 候選欄位使用的 prompt 版本；固定規則為 NULL'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM valuation.extracted_fields
                WHERE analysis_provider = 'BEDROCK'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while BEDROCK candidate provenance exists';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE valuation.extracted_fields
            DROP CONSTRAINT ck_extracted_fields_analysis_provenance,
            DROP CONSTRAINT ck_extracted_fields_analysis_provider,
            DROP COLUMN prompt_version,
            DROP COLUMN model_id,
            DROP COLUMN analysis_provider
        """
    )
