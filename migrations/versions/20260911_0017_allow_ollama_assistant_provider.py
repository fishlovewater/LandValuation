"""Allow Ollama-backed AI Assistant sessions.

Revision ID: 20260911_0017
Revises: 20260911_0016
Create Date: 2026-09-11
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260911_0017"
down_revision: Union[str, Sequence[str], None] = "20260911_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_assistant_sessions_provider",
        "assistant_sessions",
        schema="valuation",
        type_="check",
    )
    op.create_check_constraint(
        "ck_assistant_sessions_provider",
        "assistant_sessions",
        "provider IN ('MOCK', 'BEDROCK', 'OLLAMA')",
        schema="valuation",
    )


def downgrade() -> None:
    # Preserve downgrade viability when development sessions were created with
    # Ollama.  The legacy schema cannot represent that provider value.
    op.execute(
        """
        UPDATE valuation.assistant_sessions
        SET provider = 'MOCK', model_id = 'mock-f03-v1'
        WHERE provider = 'OLLAMA'
        """
    )
    op.drop_constraint(
        "ck_assistant_sessions_provider",
        "assistant_sessions",
        schema="valuation",
        type_="check",
    )
    op.create_check_constraint(
        "ck_assistant_sessions_provider",
        "assistant_sessions",
        "provider IN ('MOCK', 'BEDROCK')",
        schema="valuation",
    )
