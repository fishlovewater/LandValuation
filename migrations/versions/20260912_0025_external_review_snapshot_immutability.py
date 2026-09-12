"""Enforce external review input snapshot immutability at the database layer.

Revision ID: 20260912_0025
Revises: 20260912_0024
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260912_0025"
down_revision: Union[str, Sequence[str], None] = "20260912_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION review.prevent_external_input_snapshot_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF pg_has_role(current_user, 'land_valuation_app', 'MEMBER') THEN
                RAISE EXCEPTION 'external review input snapshots are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END
        $$;

        DROP TRIGGER IF EXISTS trg_external_input_snapshots_immutable
            ON review.external_input_snapshots;

        CREATE TRIGGER trg_external_input_snapshots_immutable
        BEFORE UPDATE OR DELETE ON review.external_input_snapshots
        FOR EACH ROW
        EXECUTE FUNCTION review.prevent_external_input_snapshot_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_external_input_snapshots_immutable
            ON review.external_input_snapshots;
        DROP FUNCTION IF EXISTS review.prevent_external_input_snapshot_mutation();
        """
    )
