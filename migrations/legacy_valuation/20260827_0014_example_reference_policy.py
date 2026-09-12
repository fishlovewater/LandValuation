"""Classify learning examples separately from formal rule sources.

Revision ID: 20260827_0014
Revises: 20260827_0013
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260827_0014"
down_revision: Union[str, Sequence[str], None] = "20260827_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge.documents "
        "DROP CONSTRAINT ck_knowledge_document_type"
    )
    op.execute(
        "ALTER TABLE knowledge.documents ADD CONSTRAINT "
        "ck_knowledge_document_type CHECK (document_type IN ("
        "'REGULATION','STANDARD','MANUAL','EXAMPLE_REFERENCE','OTHER'))"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM valuation.rule_version_sources AS rvs
                JOIN valuation.rule_versions AS rv
                  ON rv.rule_version_id = rvs.rule_version_id
                JOIN knowledge.documents AS kd
                  ON kd.document_id = rvs.source_document_id
                WHERE kd.original_filename = '評價基準明細表範例.pdf'
                  AND rv.status = 'PUBLISHED'
            ) THEN
                RAISE EXCEPTION
                    'Cannot reclassify a learning example linked to a published rule';
            END IF;
        END $$
        """
    )
    op.execute(
        """
        UPDATE knowledge.documents
        SET document_type = 'EXAMPLE_REFERENCE',
            metadata = COALESCE(metadata, '{}'::jsonb) ||
                jsonb_build_object(
                    'source_usage', 'EXAMPLE_REFERENCE',
                    'formal_rule_eligible', false
                ),
            publication_status = 'DRAFT',
            approved_by_user_id = NULL,
            approved_at = NULL,
            updated_at = now()
        WHERE original_filename = '評價基準明細表範例.pdf'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE knowledge.documents
        SET document_type = 'STANDARD',
            metadata = (COALESCE(metadata, '{}'::jsonb)
                - 'source_usage' - 'formal_rule_eligible'),
            updated_at = now()
        WHERE document_type = 'EXAMPLE_REFERENCE'
          AND original_filename = '評價基準明細表範例.pdf'
        """
    )
    op.execute(
        "ALTER TABLE knowledge.documents "
        "DROP CONSTRAINT ck_knowledge_document_type"
    )
    op.execute(
        "ALTER TABLE knowledge.documents ADD CONSTRAINT "
        "ck_knowledge_document_type CHECK (document_type IN ("
        "'REGULATION','STANDARD','MANUAL','OTHER'))"
    )
