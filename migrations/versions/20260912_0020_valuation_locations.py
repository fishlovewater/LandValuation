"""Add location-scoped valuation workflow records.

Revision ID: 20260912_0020
Revises: 20260912_0019
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260912_0020"
down_revision: Union[str, Sequence[str], None] = "20260912_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "valuation_locations",
        sa.Column("location_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=300)),
        sa.Column("is_benchmark_location", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["case_id"], ["valuation.cases.case_id"]),
        sa.UniqueConstraint("case_id", "display_order", name="uq_valuation_locations_case_order"),
        schema="valuation",
    )
    for table in ("documents", "extracted_fields", "parcels", "form_instances"):
        op.add_column(table, sa.Column("location_id", postgresql.UUID(as_uuid=True)), schema="valuation")
        op.create_foreign_key(f"fk_{table}_location", table, "valuation_locations", ["location_id"], ["location_id"], source_schema="valuation", referent_schema="valuation")
        op.create_index(f"ix_{table}_location_id", table, ["location_id"], schema="valuation")
    op.execute("""
        INSERT INTO valuation.valuation_locations (location_id, case_id, display_order, label)
        SELECT gen_random_uuid(), c.case_id, 1, '地點 1'
        FROM valuation.cases c
    """)
    for table in ("documents", "extracted_fields", "parcels", "form_instances"):
        op.execute(f"""
            UPDATE valuation.{table} x SET location_id = l.location_id
            FROM valuation.valuation_locations l
            WHERE l.case_id = x.case_id AND l.display_order = 1
        """)


def downgrade() -> None:
    for table in ("form_instances", "parcels", "extracted_fields", "documents"):
        op.drop_index(f"ix_{table}_location_id", table_name=table, schema="valuation")
        op.drop_constraint(f"fk_{table}_location", table, schema="valuation", type_="foreignkey")
        op.drop_column(table, "location_id", schema="valuation")
    op.drop_table("valuation_locations", schema="valuation")