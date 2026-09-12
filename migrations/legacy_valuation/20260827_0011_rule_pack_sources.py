"""Add versioned New Taipei rule-pack source metadata.

Revision ID: 20260827_0011
Revises: 75dcc9441ca7
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260827_0011"
down_revision: Union[str, Sequence[str], None] = "75dcc9441ca7"
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


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM valuation.rule_versions
                WHERE jurisdiction_code IS NOT NULL OR import_status <> 'LEGACY'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while imported rule packs exist';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP INDEX IF EXISTS valuation.idx_rule_versions_applicability")
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
