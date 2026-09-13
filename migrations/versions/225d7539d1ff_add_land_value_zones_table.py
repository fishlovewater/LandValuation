"""Add land_value_zones table

Revision ID: 225d7539d1ff
Revises: 3ae7a853ea91
Create Date: 2026-09-12 21:28:45.935318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '225d7539d1ff'
down_revision: Union[str, Sequence[str], None] = '3ae7a853ea91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'land_value_zones',
        sa.Column('zone_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('city_code', sa.String(length=20), nullable=True),
        sa.Column('district_code', sa.String(length=20), nullable=True),
        sa.Column('price_zone_no', sa.String(length=30), nullable=False),
        sa.Column('area_sqm', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('geometry_geojson', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('zone_id'),
        schema='valuation'
    )
    op.create_index(
        'idx_land_value_zones_price_zone_no',
        'land_value_zones',
        ['price_zone_no'],
        unique=False,
        schema='valuation'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_land_value_zones_price_zone_no', table_name='land_value_zones', schema='valuation')
    op.drop_table('land_value_zones', schema='valuation')
