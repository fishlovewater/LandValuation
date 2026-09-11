"""Add account-access management permission and decision notes.

Revision ID: 20260911_0021
Revises: 20260911_0020
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260911_0021"
down_revision: Union[str, Sequence[str], None] = "20260911_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_access_requests",
        sa.Column("decision_note", sa.Text(), nullable=True),
        schema="auth",
    )
    op.execute(
        """
        INSERT INTO auth.roles (role_id, role_code, role_name, description, is_active)
        VALUES (gen_random_uuid(), 'SYSTEM_ADMIN', '系統管理者', '管理平台帳號與系統權限', true)
        ON CONFLICT (role_code) DO NOTHING;

        INSERT INTO auth.permissions
            (permission_id, permission_code, permission_name, resource, action, description)
        VALUES
            (gen_random_uuid(), 'auth.manage', '管理帳號申請', 'auth', 'manage',
             '檢視、核准或拒絕工作帳號申請')
        ON CONFLICT (permission_code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO auth.role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM auth.roles AS r
        JOIN auth.permissions AS p ON p.permission_code = 'auth.manage'
        WHERE r.role_code = 'SYSTEM_ADMIN'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM auth.role_permissions AS rp
        USING auth.permissions AS p
        WHERE rp.permission_id = p.permission_id
          AND p.permission_code = 'auth.manage'
        """
    )
    op.execute("DELETE FROM auth.permissions WHERE permission_code = 'auth.manage'")
    op.execute(
        """
        DELETE FROM auth.roles AS r
        WHERE r.role_code = 'SYSTEM_ADMIN'
          AND NOT EXISTS (
              SELECT 1 FROM auth.user_roles AS ur WHERE ur.role_id = r.role_id
          )
        """
    )
    op.drop_column("account_access_requests", "decision_note", schema="auth")
