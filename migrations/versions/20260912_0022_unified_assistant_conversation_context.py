"""Bind assistant conversations to optional workspace context.

Revision ID: 20260912_0022
Revises: 20260911_0021
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260912_0022"
down_revision: Union[str, Sequence[str], None] = "20260911_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE knowledge.conversations
            ADD COLUMN IF NOT EXISTS case_id uuid,
            ADD COLUMN IF NOT EXISTS review_id uuid,
            ADD COLUMN IF NOT EXISTS finding_id uuid,
            ADD COLUMN IF NOT EXISTS workspace varchar(30);

        CREATE INDEX IF NOT EXISTS idx_knowledge_conversations_user_case_updated
            ON knowledge.conversations(user_id, case_id, updated_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS knowledge.idx_knowledge_conversations_user_case_updated;
        ALTER TABLE knowledge.conversations
            DROP COLUMN IF EXISTS workspace,
            DROP COLUMN IF EXISTS finding_id,
            DROP COLUMN IF EXISTS review_id,
            DROP COLUMN IF EXISTS case_id;
        """
    )
