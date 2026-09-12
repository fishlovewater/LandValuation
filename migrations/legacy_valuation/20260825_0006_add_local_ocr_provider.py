"""Allow local OCR document extraction provider.

Revision ID: 20260825_0006
Revises: 20260825_0005
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260825_0006"
down_revision: Union[str, Sequence[str], None] = "20260825_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.document_extractions
            DROP CONSTRAINT ck_document_extractions_provider,
            ADD CONSTRAINT ck_document_extractions_provider
                CHECK (provider IN ('LOCAL_PDF', 'LOCAL_OCR', 'TEXTRACT'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM valuation.document_extractions
                WHERE provider = 'LOCAL_OCR'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while LOCAL_OCR extraction records exist';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE valuation.document_extractions
            DROP CONSTRAINT ck_document_extractions_provider,
            ADD CONSTRAINT ck_document_extractions_provider
                CHECK (provider IN ('LOCAL_PDF', 'TEXTRACT'))
        """
    )
