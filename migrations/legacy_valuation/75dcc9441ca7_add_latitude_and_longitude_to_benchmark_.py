"""Add latitude and longitude to benchmark lands

Revision ID: 75dcc9441ca7
Revises: 20260826_0010
Create Date: 2026-08-26 20:26:23.239631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75dcc9441ca7'
down_revision: Union[str, Sequence[str], None] = '20260826_0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('benchmark_lands', sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True), schema='valuation')
    op.add_column('benchmark_lands', sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True), schema='valuation')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('benchmark_lands', 'longitude', schema='valuation')
    op.drop_column('benchmark_lands', 'latitude', schema='valuation')
