"""Add immutable input snapshots for external review runs.

Revision ID: 20260912_0024
Revises: 20260912_0023
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260912_0024"
down_revision: Union[str, Sequence[str], None] = "20260912_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS review.external_input_snapshots (
            external_input_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            review_id uuid NOT NULL,
            case_id uuid NOT NULL,
            snapshot_no integer NOT NULL,
            snapshot_schema_version varchar(60) NOT NULL,
            input_snapshot jsonb NOT NULL,
            input_fingerprint varchar(64) NOT NULL,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_external_input_snapshots_review_no
                UNIQUE (review_id, snapshot_no),
            CONSTRAINT fk_external_input_snapshots_review
                FOREIGN KEY (review_id)
                REFERENCES review.reviews(review_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_external_input_snapshots_case
                FOREIGN KEY (case_id)
                REFERENCES valuation.cases(case_id),
            CONSTRAINT fk_external_input_snapshots_creator
                FOREIGN KEY (created_by_user_id)
                REFERENCES auth.users(user_id)
        );

        CREATE INDEX IF NOT EXISTS ix_external_input_snapshots_review
            ON review.external_input_snapshots(review_id, snapshot_no DESC);
        CREATE INDEX IF NOT EXISTS ix_external_input_snapshots_case
            ON review.external_input_snapshots(case_id, created_at DESC);

        GRANT USAGE ON SCHEMA review TO land_valuation_app;
        GRANT SELECT, INSERT ON review.external_input_snapshots TO land_valuation_app;
        REVOKE UPDATE, DELETE ON review.external_input_snapshots FROM land_valuation_app;

        ALTER TABLE valuation.validation_runs
            ADD COLUMN IF NOT EXISTS external_input_snapshot_id uuid;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_validation_runs_external_input_snapshot'
                  AND conrelid = 'valuation.validation_runs'::regclass
            ) THEN
                ALTER TABLE valuation.validation_runs
                    ADD CONSTRAINT fk_validation_runs_external_input_snapshot
                    FOREIGN KEY (external_input_snapshot_id)
                    REFERENCES review.external_input_snapshots(external_input_snapshot_id);
            END IF;
        END
        $$;

        CREATE INDEX IF NOT EXISTS ix_validation_runs_external_input_snapshot
            ON valuation.validation_runs(external_input_snapshot_id)
            WHERE external_input_snapshot_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS valuation.ix_validation_runs_external_input_snapshot;
        ALTER TABLE valuation.validation_runs
            DROP CONSTRAINT IF EXISTS fk_validation_runs_external_input_snapshot,
            DROP COLUMN IF EXISTS external_input_snapshot_id;

        DROP INDEX IF EXISTS review.ix_external_input_snapshots_case;
        DROP INDEX IF EXISTS review.ix_external_input_snapshots_review;
        DROP TABLE IF EXISTS review.external_input_snapshots;
        """
    )
