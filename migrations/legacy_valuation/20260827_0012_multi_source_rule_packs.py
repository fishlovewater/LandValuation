"""Allow one rule version to reference multiple source documents.

Revision ID: 20260827_0012
Revises: 20260827_0011
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260827_0012"
down_revision: Union[str, Sequence[str], None] = "20260827_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE valuation.rule_version_sources (
            rule_version_source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            rule_version_id uuid NOT NULL,
            source_document_id uuid NOT NULL,
            source_role varchar(40) NOT NULL,
            source_order integer NOT NULL,
            is_primary boolean NOT NULL DEFAULT false,
            is_required boolean NOT NULL DEFAULT true,
            page_reference varchar(500),
            notes text,
            created_by_user_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_rule_version_sources_rule_version
                FOREIGN KEY (rule_version_id)
                REFERENCES valuation.rule_versions(rule_version_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_rule_version_sources_document
                FOREIGN KEY (source_document_id)
                REFERENCES knowledge.documents(document_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT fk_rule_version_sources_created_by
                FOREIGN KEY (created_by_user_id)
                REFERENCES auth.users(user_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CONSTRAINT uq_rule_version_sources_document
                UNIQUE (rule_version_id, source_document_id),
            CONSTRAINT uq_rule_version_sources_order
                UNIQUE (rule_version_id, source_order),
            CONSTRAINT ck_rule_version_sources_role CHECK (
                source_role IN (
                    'PRIMARY',
                    'LEGAL_BASIS',
                    'NATIONAL_MANUAL',
                    'LOCAL_MANUAL',
                    'FACTOR_STANDARD',
                    'FORM_TEMPLATE',
                    'CASE_EXAMPLE',
                    'OTHER'
                )
            ),
            CONSTRAINT ck_rule_version_sources_order CHECK (source_order > 0)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_rule_version_sources_primary "
        "ON valuation.rule_version_sources (rule_version_id) WHERE is_primary"
    )
    op.execute(
        "CREATE INDEX idx_rule_version_sources_rule_order "
        "ON valuation.rule_version_sources (rule_version_id, source_order)"
    )
    op.execute(
        "CREATE INDEX idx_rule_version_sources_document "
        "ON valuation.rule_version_sources (source_document_id)"
    )
    op.execute(
        """
        INSERT INTO valuation.rule_version_sources (
            rule_version_id,
            source_document_id,
            source_role,
            source_order,
            is_primary,
            is_required,
            created_by_user_id
        )
        SELECT
            rv.rule_version_id,
            rv.source_document_id,
            'PRIMARY',
            1,
            true,
            true,
            kd.created_by_user_id
        FROM valuation.rule_versions AS rv
        JOIN knowledge.documents AS kd
          ON kd.document_id = rv.source_document_id
        WHERE rv.source_document_id IS NOT NULL
        ON CONFLICT (rule_version_id, source_document_id) DO NOTHING
        """
    )
    op.execute(
        "COMMENT ON TABLE valuation.rule_version_sources IS "
        "'Traceable ordered source documents used by one valuation rule version'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.rule_version_sources.page_reference IS "
        "'User-confirmed page, chapter, article, or section reference; never inferred by the system'"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM valuation.rule_version_sources
                WHERE NOT is_primary OR source_order <> 1
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while multi-source rule packs exist';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP TABLE valuation.rule_version_sources")
