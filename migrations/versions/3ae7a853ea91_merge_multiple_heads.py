"""Merge multiple heads

Revision ID: 3ae7a853ea91
Revises: 20260911_0021, 20260912_0020
Create Date: 2026-09-12 21:28:35.228618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ae7a853ea91'
down_revision: Union[str, Sequence[str], None] = ('20260911_0021', '20260912_0020')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
