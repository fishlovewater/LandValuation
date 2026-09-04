"""Enforce one Review workflow per valuation case.

Revision ID: 20260904_0014
Revises: 20260903_0013
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260904_0014"
down_revision: Union[str, Sequence[str], None] = "20260903_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hold a write-blocking lock across the legacy-data guard and constraint
    # creation so a concurrent Review cannot appear between those operations.
    op.execute("LOCK TABLE review.reviews IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT case_id
                FROM review.reviews
                GROUP BY case_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'cannot enforce one review per case while duplicate review rows exist';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE review.reviews "
        "ADD CONSTRAINT uq_reviews_case_id UNIQUE (case_id)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE review.reviews DROP CONSTRAINT uq_reviews_case_id"
    )
