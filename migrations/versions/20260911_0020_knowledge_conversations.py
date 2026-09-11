"""Activate persistent knowledge-assistant conversations.

Revision ID: 20260911_0020
Revises: 20260911_0019
Create Date: 2026-09-11

The original knowledge schema already contains knowledge.conversations,
knowledge.messages, and knowledge.message_sources.  This migration extends
those existing audit tables with the metadata needed by the current assistant
UI and stores the complete validated answer payload for history restoration.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260911_0020"
down_revision: Union[str, Sequence[str], None] = "20260911_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE valuation.assistant_messages
            ADD COLUMN IF NOT EXISTS response_payload jsonb NOT NULL DEFAULT '{}'::jsonb;

        ALTER TABLE knowledge.conversations
            ADD COLUMN IF NOT EXISTS provider varchar(30) NOT NULL DEFAULT 'evidence_only',
            ADD COLUMN IF NOT EXISTS model_id varchar(200);

        ALTER TABLE knowledge.messages
            ADD COLUMN IF NOT EXISTS response_payload jsonb NOT NULL DEFAULT '{}'::jsonb;

        ALTER TABLE knowledge.messages
            DROP CONSTRAINT IF EXISTS ck_knowledge_messages_response_payload;
        ALTER TABLE knowledge.messages
            ADD CONSTRAINT ck_knowledge_messages_response_payload
            CHECK (jsonb_typeof(response_payload) = 'object');

        CREATE INDEX IF NOT EXISTS idx_knowledge_conversations_user_updated
            ON knowledge.conversations(user_id, updated_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS knowledge.idx_knowledge_conversations_user_updated;
        ALTER TABLE knowledge.messages
            DROP CONSTRAINT IF EXISTS ck_knowledge_messages_response_payload;
        ALTER TABLE knowledge.messages
            DROP COLUMN IF EXISTS response_payload;
        ALTER TABLE knowledge.conversations
            DROP COLUMN IF EXISTS model_id,
            DROP COLUMN IF EXISTS provider;
        ALTER TABLE valuation.assistant_messages
            DROP COLUMN IF EXISTS response_payload;
        """
    )
