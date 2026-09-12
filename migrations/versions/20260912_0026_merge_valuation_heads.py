"""Merge valuation location/AWS extraction history with current application history.

Revision ID: 20260912_0026
Revises: 20260912_0020, 20260912_0025
"""
from typing import Sequence, Union

revision: str = "20260912_0026"
down_revision: Union[str, Sequence[str], None] = ("20260912_0020", "20260912_0025")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
