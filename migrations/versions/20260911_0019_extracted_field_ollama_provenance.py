"""Allow Ollama and XLSX rule provenance for extracted fields.

Revision ID: 20260911_0019
Revises: 20260911_0018
Create Date: 2026-09-11
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260911_0019"
down_revision: Union[str, Sequence[str], None] = "20260911_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_extracted_fields_analysis_provenance",
        "extracted_fields",
        schema="valuation",
        type_="check",
    )
    op.drop_constraint(
        "ck_extracted_fields_analysis_provider",
        "extracted_fields",
        schema="valuation",
        type_="check",
    )
    op.create_check_constraint(
        "ck_extracted_fields_analysis_provider",
        "extracted_fields",
        "analysis_provider IN ('RULE', 'XLSX_RULE', 'BEDROCK', 'CODEX', 'OLLAMA')",
        schema="valuation",
    )
    op.create_check_constraint(
        "ck_extracted_fields_analysis_provenance",
        "extracted_fields",
        """
        (analysis_provider = 'RULE' AND model_id IS NULL AND prompt_version IS NULL)
        OR (analysis_provider = 'XLSX_RULE'
            AND model_id IS NULL
            AND nullif(btrim(prompt_version), '') IS NOT NULL)
        OR (analysis_provider IN ('BEDROCK', 'CODEX', 'OLLAMA')
            AND nullif(btrim(model_id), '') IS NOT NULL
            AND nullif(btrim(prompt_version), '') IS NOT NULL)
        """,
        schema="valuation",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_extracted_fields_analysis_provenance",
        "extracted_fields",
        schema="valuation",
        type_="check",
    )
    op.drop_constraint(
        "ck_extracted_fields_analysis_provider",
        "extracted_fields",
        schema="valuation",
        type_="check",
    )
    op.create_check_constraint(
        "ck_extracted_fields_analysis_provider",
        "extracted_fields",
        "analysis_provider IN ('RULE', 'BEDROCK', 'CODEX')",
        schema="valuation",
    )
    op.create_check_constraint(
        "ck_extracted_fields_analysis_provenance",
        "extracted_fields",
        """
        (analysis_provider = 'RULE' AND model_id IS NULL AND prompt_version IS NULL)
        OR (analysis_provider IN ('BEDROCK', 'CODEX')
            AND nullif(btrim(model_id), '') IS NOT NULL
            AND nullif(btrim(prompt_version), '') IS NOT NULL)
        """,
        schema="valuation",
    )
