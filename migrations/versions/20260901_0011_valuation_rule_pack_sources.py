"""Add versioned New Taipei valuation rule-pack sources.

Revision ID: 20260901_0011
Revises: 20260901_0010
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260901_0011"
down_revision: Union[str, Sequence[str], None] = "20260901_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge.documents ADD COLUMN storage_etag varchar(255)")
    op.execute(
        "COMMENT ON COLUMN knowledge.documents.storage_etag IS "
        "'MinIO ETag for object verification; SHA-256 remains authoritative'"
    )

    op.execute("ALTER TABLE valuation.rule_versions ADD COLUMN jurisdiction_code varchar(50)")
    op.execute("ALTER TABLE valuation.rule_versions ADD COLUMN district_scope jsonb")
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD COLUMN land_use_types jsonb "
        "NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE valuation.rule_versions ADD COLUMN formula_code varchar(100)")
    op.execute("ALTER TABLE valuation.rule_versions ADD COLUMN rounding_code varchar(100)")
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD COLUMN import_status varchar(30) "
        "NOT NULL DEFAULT 'LEGACY'"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD COLUMN import_summary jsonb "
        "NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("ALTER TABLE valuation.rule_versions ADD COLUMN verified_by_user_id uuid")
    op.execute("ALTER TABLE valuation.rule_versions ADD COLUMN verified_at timestamptz")
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT "
        "fk_rule_versions_verified_by_user FOREIGN KEY (verified_by_user_id) "
        "REFERENCES auth.users(user_id) ON UPDATE RESTRICT ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT ck_rule_versions_jurisdiction "
        "CHECK (jurisdiction_code IS NULL OR jurisdiction_code = 'NEW_TAIPEI_CITY')"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT ck_rule_versions_district_scope "
        "CHECK (district_scope IS NULL OR jsonb_typeof(district_scope) = 'object')"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT ck_rule_versions_land_use_types "
        "CHECK (jsonb_typeof(land_use_types) = 'array' AND land_use_types <@ "
        "'[\"RESIDENTIAL\",\"COMMERCIAL\",\"INDUSTRIAL\",\"AGRICULTURAL\",\"OTHER\"]'::jsonb)"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT ck_rule_versions_import_status "
        "CHECK (import_status IN ('LEGACY','SOURCE_UPLOADED','IMPORTED','VERIFIED'))"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT ck_rule_versions_import_summary "
        "CHECK (jsonb_typeof(import_summary) = 'object')"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT ck_rule_versions_verification "
        "CHECK ((verified_by_user_id IS NULL AND verified_at IS NULL) OR "
        "(verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL))"
    )
    op.execute(
        "CREATE INDEX idx_rule_versions_applicability ON valuation.rule_versions "
        "(jurisdiction_code, status, effective_from) WHERE jurisdiction_code IS NOT NULL"
    )

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
            source_reference varchar(1000),
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
                    'PRIMARY', 'LEGAL_BASIS', 'NATIONAL_MANUAL', 'LOCAL_MANUAL',
                    'FACTOR_STANDARD', 'FORM_TEMPLATE', 'CASE_EXAMPLE', 'OTHER'
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
        "COMMENT ON TABLE valuation.rule_version_sources IS "
        "'Traceable ordered source documents used by one valuation rule version'"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.rule_version_sources.page_reference IS "
        "'User-confirmed page, chapter, article, or section reference; never inferred by the system'"
    )

    op.execute(
        "ALTER TABLE valuation.rule_versions "
        "ADD COLUMN effective_date_status varchar(20) NOT NULL DEFAULT 'CONFIRMED'"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ALTER COLUMN effective_from DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT "
        "ck_rule_versions_effective_date_status CHECK ("
        "effective_date_status IN ('CONFIRMED','UNKNOWN'))"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ADD CONSTRAINT "
        "ck_rule_versions_effective_date_state CHECK ("
        "jurisdiction_code IS NULL OR "
        "(effective_date_status = 'CONFIRMED' AND effective_from IS NOT NULL) OR "
        "(effective_date_status = 'UNKNOWN' AND effective_from IS NULL AND status = 'DRAFT'))"
    )
    op.execute(
        "COMMENT ON COLUMN valuation.rule_versions.effective_date_status IS "
        "'UNKNOWN is allowed only for unpublished drafts; publication requires a confirmed date'"
    )

    op.execute("ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_document_type")
    op.execute(
        "ALTER TABLE knowledge.documents ADD CONSTRAINT "
        "ck_knowledge_document_type CHECK (document_type IN ("
        "'REGULATION','STANDARD','MANUAL','EXAMPLE_REFERENCE','OTHER'))"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM valuation.rule_version_sources) THEN
                RAISE EXCEPTION 'cannot downgrade while rule-source migration data exists';
            END IF;
            IF EXISTS (
                SELECT 1 FROM valuation.rule_versions
                WHERE jurisdiction_code IS NOT NULL
                   OR district_scope IS NOT NULL
                   OR land_use_types <> '[]'::jsonb
                   OR formula_code IS NOT NULL
                   OR rounding_code IS NOT NULL
                   OR import_status <> 'LEGACY'
                   OR import_summary <> '{}'::jsonb
                   OR verified_by_user_id IS NOT NULL
                   OR verified_at IS NOT NULL
                   OR effective_date_status <> 'CONFIRMED'
                   OR effective_from IS NULL
            ) THEN
                RAISE EXCEPTION 'cannot downgrade while rule-source migration data exists';
            END IF;
            IF EXISTS (
                SELECT 1 FROM knowledge.documents
                WHERE storage_etag IS NOT NULL
                   OR document_type = 'EXAMPLE_REFERENCE'
            ) THEN
                RAISE EXCEPTION 'cannot downgrade while rule-source migration data exists';
            END IF;
        END
        $$
        """
    )

    op.execute("ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_document_type")
    op.execute(
        "ALTER TABLE knowledge.documents ADD CONSTRAINT "
        "ck_knowledge_document_type CHECK (document_type IN ("
        "'REGULATION','STANDARD','MANUAL','OTHER'))"
    )

    op.execute("DROP INDEX valuation.idx_rule_version_sources_document")
    op.execute("DROP INDEX valuation.idx_rule_version_sources_rule_order")
    op.execute("DROP INDEX valuation.uq_rule_version_sources_primary")
    op.execute("DROP TABLE valuation.rule_version_sources")

    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_effective_date_state")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_effective_date_status")
    op.execute("ALTER TABLE valuation.rule_versions ALTER COLUMN effective_from SET NOT NULL")
    op.execute("ALTER TABLE valuation.rule_versions DROP COLUMN effective_date_status")
    op.execute("DROP INDEX valuation.idx_rule_versions_applicability")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_verification")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_import_summary")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_import_status")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_land_use_types")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_district_scope")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT ck_rule_versions_jurisdiction")
    op.execute("ALTER TABLE valuation.rule_versions DROP CONSTRAINT fk_rule_versions_verified_by_user")
    op.execute(
        "ALTER TABLE valuation.rule_versions DROP COLUMN verified_at, "
        "DROP COLUMN verified_by_user_id, DROP COLUMN import_summary, "
        "DROP COLUMN import_status, DROP COLUMN rounding_code, DROP COLUMN formula_code, "
        "DROP COLUMN land_use_types, DROP COLUMN district_scope, DROP COLUMN jurisdiction_code"
    )
    op.execute("ALTER TABLE knowledge.documents DROP COLUMN storage_etag")
