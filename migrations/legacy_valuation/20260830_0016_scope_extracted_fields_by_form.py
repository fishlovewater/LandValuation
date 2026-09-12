"""Scope extracted-field uniqueness to its target form.

Revision ID: 20260830_0016
Revises: 20260828_0015
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260830_0016"
down_revision: Union[str, Sequence[str], None] = "20260828_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.extracted_fields
            DROP CONSTRAINT uq_extracted_fields_extraction_field,
            ADD CONSTRAINT uq_extracted_fields_extraction_form_field
                UNIQUE (extraction_id, form_code, field_name)
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
                GROUP BY extraction_id, field_name
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot restore global field uniqueness while different forms share field names';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE valuation.extracted_fields
            DROP CONSTRAINT uq_extracted_fields_extraction_form_field,
            ADD CONSTRAINT uq_extracted_fields_extraction_field
                UNIQUE (extraction_id, field_name)
        """
    )
