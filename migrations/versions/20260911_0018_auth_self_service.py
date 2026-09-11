"""Add account-access requests and password-reset tokens.

Revision ID: 20260911_0018
Revises: 20260911_0017
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260911_0018"
down_revision: Union[str, Sequence[str], None] = "20260911_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_access_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("requested_role", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "requested_role IN ('APPRAISER', 'REVIEWER', 'INSPECTOR')",
            name="ck_account_access_requests_role",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_account_access_requests_status",
        ),
        sa.ForeignKeyConstraint(
            ["handled_by_user_id"],
            ["auth.users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("request_id"),
        schema="auth",
    )
    op.create_index(
        "uq_account_access_requests_pending_email",
        "account_access_requests",
        ["email"],
        unique=True,
        schema="auth",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "uq_account_access_requests_pending_username",
        "account_access_requests",
        ["username"],
        unique=True,
        schema="auth",
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_hash"),
        schema="auth",
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        unique=False,
        schema="auth",
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens", schema="auth")
    op.drop_table("password_reset_tokens", schema="auth")
    op.drop_index("uq_account_access_requests_pending_username", table_name="account_access_requests", schema="auth")
    op.drop_index("uq_account_access_requests_pending_email", table_name="account_access_requests", schema="auth")
    op.drop_table("account_access_requests", schema="auth")
