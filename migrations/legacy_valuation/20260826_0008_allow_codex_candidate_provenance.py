"""Allow validated Codex imports as extracted candidate provenance.

Revision ID: 20260826_0008
Revises: 20260825_0007
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0008"
down_revision: Union[str, Sequence[str], None] = "20260825_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.extracted_fields
            DROP CONSTRAINT ck_extracted_fields_analysis_provenance,
            DROP CONSTRAINT ck_extracted_fields_analysis_provider,
            ADD CONSTRAINT ck_extracted_fields_analysis_provider
                CHECK (analysis_provider IN ('RULE', 'BEDROCK', 'CODEX')),
            ADD CONSTRAINT ck_extracted_fields_analysis_provenance CHECK (
                (analysis_provider = 'RULE'
                    AND model_id IS NULL
                    AND prompt_version IS NULL)
                OR
                (analysis_provider IN ('BEDROCK', 'CODEX')
                    AND nullif(btrim(model_id), '') IS NOT NULL
                    AND nullif(btrim(prompt_version), '') IS NOT NULL)
            )
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN valuation.extracted_fields.analysis_provider IS
            '候選欄位產生方式：固定規則、Bedrock 語意辨識或經驗證的 Codex 匯入'
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
                WHERE analysis_provider = 'CODEX'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while CODEX candidate provenance exists';
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
            '候選欄位產生方式：固定規則或 Bedrock 語意辨識'
        """
    )
