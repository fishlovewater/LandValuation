"""Allow every review workflow status to fit in review.reviews.

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
        "ALTER TABLE review.reviews "
        "ALTER COLUMN review_status TYPE varchar(30)"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM review.reviews
                WHERE length(review_status) > 20
            ) THEN
                RAISE EXCEPTION
                    'review_status values longer than 20 characters prevent downgrade';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE review.reviews "
        "ALTER COLUMN review_status TYPE varchar(20)"
    )
