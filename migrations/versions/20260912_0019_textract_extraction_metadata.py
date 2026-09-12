"""Store structured document extraction metadata.

Revision ID: 20260912_0019
Revises: 20260911_0018
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260912_0019"
down_revision: Union[str, Sequence[str], None] = "20260911_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "document_extractions",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="valuation",
    )

def downgrade() -> None:
    op.drop_column("document_extractions", "metadata", schema="valuation")
