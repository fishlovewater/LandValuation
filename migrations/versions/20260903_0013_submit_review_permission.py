"""Seed the appraiser submit-for-review permission.

Revision ID: 20260903_0013
Revises: 20260901_0012
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260903_0013"
down_revision: Union[str, Sequence[str], None] = "20260901_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The submit command resolves qualified workflow tables as the runtime
    # role. Keep access limited to the reads/writes in this transaction.
    op.execute("GRANT USAGE ON SCHEMA review, history TO land_valuation_app")
    op.execute("REVOKE DELETE ON review.reviews FROM land_valuation_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON review.reviews TO land_valuation_app"
    )
    op.execute(
        "REVOKE SELECT, UPDATE, DELETE ON history.case_events "
        "FROM land_valuation_app"
    )
    op.execute("GRANT INSERT ON history.case_events TO land_valuation_app")
    op.execute(
        "GRANT SELECT (occurred_at) ON history.case_events "
        "TO land_valuation_app"
    )
    op.execute(
        "REVOKE UPDATE, DELETE ON valuation.review_submissions "
        "FROM land_valuation_app"
    )
    op.execute(
        "GRANT SELECT, INSERT ON valuation.review_submissions "
        "TO land_valuation_app"
    )
    op.execute(
        """
        INSERT INTO auth.permissions
            (permission_code, permission_name, resource, action, description)
        VALUES
            ('valuation.submit_review', '送審估價', 'valuation', 'submit_review',
             '提交完整估價報告供審查')
        ON CONFLICT (permission_code) DO UPDATE
        SET permission_name = EXCLUDED.permission_name,
            description = EXCLUDED.description
        """
    )
    op.execute(
        """
        WITH grants(role_code, permission_code) AS (
            VALUES ('APPRAISER', 'valuation.submit_review')
        )
        INSERT INTO auth.role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM grants AS g
        JOIN auth.roles AS r ON r.role_code = g.role_code
        JOIN auth.permissions AS p ON p.permission_code = g.permission_code
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM auth.role_permissions AS rp
        USING auth.roles AS r, auth.permissions AS p
        WHERE rp.role_id = r.role_id
          AND rp.permission_id = p.permission_id
          AND r.role_code = 'APPRAISER'
          AND p.permission_code = 'valuation.submit_review'
        """
    )
    # Restore the materialized default table grants that predated this
    # revision, then remove only the schema usage introduced above.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON review.reviews, "
        "history.case_events, valuation.review_submissions TO land_valuation_app"
    )
    op.execute("REVOKE USAGE ON SCHEMA review, history FROM land_valuation_app")
    op.execute(
        """
        DELETE FROM auth.permissions AS p
        WHERE p.permission_code = 'valuation.submit_review'
          AND NOT EXISTS (
              SELECT 1
              FROM auth.role_permissions AS rp
              WHERE rp.permission_id = p.permission_id
          )
        """
    )
