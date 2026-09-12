"""Support unknown draft effective dates and existing knowledge links.

Revision ID: 20260827_0013
Revises: 20260827_0012
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260827_0013"
down_revision: Union[str, Sequence[str], None] = "20260827_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE valuation.rule_version_sources "
        "ADD COLUMN source_reference varchar(1000)"
    )
    op.execute(
        """
        UPDATE valuation.rule_version_sources AS rvs
        SET source_reference = rv.source_reference
        FROM valuation.rule_versions AS rv
        WHERE rv.rule_version_id = rvs.rule_version_id
          AND rvs.is_primary
        """
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


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM valuation.rule_versions
                WHERE effective_from IS NULL OR effective_date_status = 'UNKNOWN'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while rule packs have unknown effective dates';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions DROP CONSTRAINT "
        "ck_rule_versions_effective_date_state"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions DROP CONSTRAINT "
        "ck_rule_versions_effective_date_status"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions ALTER COLUMN effective_from SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE valuation.rule_versions DROP COLUMN effective_date_status"
    )
    op.execute(
        "ALTER TABLE valuation.rule_version_sources DROP COLUMN source_reference"
    )
