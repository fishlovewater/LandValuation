"""Register the Assistant entry permission without assigning it to a role.

Revision ID: 20260908_0015
Revises: 20260904_0014
Create Date: 2026-09-08
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260908_0015"
down_revision: Union[str, Sequence[str], None] = "20260904_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO auth.permissions
            (permission_id, permission_code, permission_name, resource, action, description)
        VALUES
            (gen_random_uuid(), 'assistant.use', '使用 AI 助理', 'assistant', 'use',
             '進入 AI 助理；其他能力仍需各自權限')
        ON CONFLICT (permission_code) DO NOTHING
        """
    )

def downgrade() -> None:
    op.execute(
        """
        DELETE FROM auth.permissions AS p
        WHERE p.permission_code = 'assistant.use'
          AND NOT EXISTS (
              SELECT 1 FROM auth.role_permissions AS rp
              WHERE rp.permission_id = p.permission_id
          )
        """
    )
