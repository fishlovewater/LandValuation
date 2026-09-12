"""Persist valuation case confirmation and last workspace stage.

Revision ID: 20260912_0023
Revises: 20260912_0022
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260912_0023"
down_revision: Union[str, Sequence[str], None] = "20260912_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.cases
            ADD COLUMN IF NOT EXISTS basic_info_confirmed_at timestamptz,
            ADD COLUMN IF NOT EXISTS basic_info_confirmed_by_user_id uuid,
            ADD COLUMN IF NOT EXISTS last_workspace_stage varchar(30) NOT NULL DEFAULT 'case';

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_valuation_cases_basic_info_confirmed_by'
            ) THEN
                ALTER TABLE valuation.cases
                    ADD CONSTRAINT fk_valuation_cases_basic_info_confirmed_by
                    FOREIGN KEY (basic_info_confirmed_by_user_id)
                    REFERENCES auth.users(user_id);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.cases
            DROP CONSTRAINT IF EXISTS fk_valuation_cases_basic_info_confirmed_by,
            DROP COLUMN IF EXISTS last_workspace_stage,
            DROP COLUMN IF EXISTS basic_info_confirmed_by_user_id,
            DROP COLUMN IF EXISTS basic_info_confirmed_at;
        """
    )