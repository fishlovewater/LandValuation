"""Allow XLSX document extraction provider.

Revision ID: 20260828_0015
Revises: 20260827_0014
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260828_0015"
down_revision: Union[str, Sequence[str], None] = "20260827_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.document_extractions
            DROP CONSTRAINT ck_document_extractions_provider,
            ADD CONSTRAINT ck_document_extractions_provider
                CHECK (provider IN ('LOCAL_PDF', 'LOCAL_OCR', 'LOCAL_XLSX', 'TEXTRACT'))
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
                WHERE provider = 'LOCAL_XLSX'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while LOCAL_XLSX extraction records exist';
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
                CHECK (provider IN ('LOCAL_PDF', 'LOCAL_OCR', 'TEXTRACT'))
        """
    )
