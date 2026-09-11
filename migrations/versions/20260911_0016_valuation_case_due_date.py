"""Add an optional appraisal-work deadline to valuation cases.

Revision ID: 20260911_0016
Revises: 20260908_0015
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260911_0016"
down_revision: Union[str, Sequence[str], None] = "20260908_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("valuation_due_date", sa.Date(), nullable=True),
        schema="valuation",
    )
    op.create_index(
        "ix_valuation_cases_due_date",
        "cases",
        ["valuation_due_date"],
        unique=False,
        schema="valuation",
    )


def downgrade() -> None:
    op.drop_index("ix_valuation_cases_due_date", table_name="cases", schema="valuation")
    op.drop_column("cases", "valuation_due_date", schema="valuation")