"""Add user foreign keys, competition roles and audit correlation.

Revision ID: 20260823_0003
Revises: 20260823_0002
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260823_0003"
down_revision: Union[str, Sequence[str], None] = "20260823_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_FOREIGN_KEYS = (
    ("valuation", "cases", "fk_cases_created_by_user", "created_by_user_id"),
    ("valuation", "cases", "fk_cases_updated_by_user", "updated_by_user_id"),
    ("valuation", "change_logs", "fk_valuation_change_logs_user", "changed_by_user_id"),
    ("valuation", "documents", "fk_documents_uploaded_by_user", "uploaded_by_user_id"),
    ("valuation", "form_instances", "fk_form_instances_created_by_user", "created_by_user_id"),
    ("valuation", "form_instances", "fk_form_instances_updated_by_user", "updated_by_user_id"),
    ("valuation", "validation_findings", "fk_validation_findings_decided_by_user", "decided_by_user_id"),
    ("valuation", "validation_runs", "fk_validation_runs_triggered_by_user", "triggered_by_user_id"),
)


def upgrade() -> None:
    for schema, table, constraint, column in USER_FOREIGN_KEYS:
        op.execute(
            f"""
            ALTER TABLE {schema}.{table}
            ADD CONSTRAINT {constraint}
            FOREIGN KEY ({column}) REFERENCES auth.users(user_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT NOT VALID
            """
        )
        op.execute(f"ALTER TABLE {schema}.{table} VALIDATE CONSTRAINT {constraint}")

    op.execute(
        """
        INSERT INTO auth.roles (role_code, role_name, description)
        VALUES
            ('REVIEWER', '審查人員', '執行智慧審查、查看疑點並作成審查決定'),
            ('INSPECTOR', '稽查人員', '查看案件、審查結果與完整稽核履歷'),
            ('APPRAISER', '估價人員', '建立案件、編輯估價資料並管理案件文件')
        ON CONFLICT (role_code) DO UPDATE
        SET role_name = EXCLUDED.role_name,
            description = EXCLUDED.description,
            is_active = true,
            updated_at = now()
        """
    )

    op.execute(
        """
        INSERT INTO auth.permissions
            (permission_code, permission_name, resource, action, description)
        VALUES
            ('case.read', '查看案件', 'case', 'read', '查看案件與宗地資料'),
            ('case.create', '建立案件', 'case', 'create', '建立新估價案件'),
            ('case.update', '編輯案件', 'case', 'update', '編輯案件與宗地資料'),
            ('valuation.read', '查看估價', 'valuation', 'read', '查看估價表與計算結果'),
            ('valuation.update', '編輯估價', 'valuation', 'update', '編輯估價表與計算資料'),
            ('review.read', '查看審查', 'review', 'read', '查看審查結果與風險摘要'),
            ('review.execute', '執行審查', 'review', 'execute', '執行智慧審查與複查'),
            ('review.decide', '作成審查決定', 'review', 'decide', '接受、駁回或要求更正審查疑點'),
            ('document.upload', '上傳文件', 'document', 'upload', '上傳案件或估價文件'),
            ('document.download', '下載文件', 'document', 'download', '下載授權文件'),
            ('knowledge.read', '查看法規知識', 'knowledge', 'read', '查看法規、手冊與引用來源'),
            ('audit.read', '查看稽核履歷', 'audit', 'read', '查看案件事件、修改與調閱紀錄')
        ON CONFLICT (permission_code) DO UPDATE
        SET permission_name = EXCLUDED.permission_name,
            description = EXCLUDED.description
        """
    )

    op.execute(
        """
        WITH grants(role_code, permission_code) AS (
            VALUES
                ('APPRAISER', 'case.read'),
                ('APPRAISER', 'case.create'),
                ('APPRAISER', 'case.update'),
                ('APPRAISER', 'valuation.read'),
                ('APPRAISER', 'valuation.update'),
                ('APPRAISER', 'document.upload'),
                ('APPRAISER', 'document.download'),
                ('APPRAISER', 'knowledge.read'),
                ('REVIEWER', 'case.read'),
                ('REVIEWER', 'valuation.read'),
                ('REVIEWER', 'review.read'),
                ('REVIEWER', 'review.execute'),
                ('REVIEWER', 'review.decide'),
                ('REVIEWER', 'document.download'),
                ('REVIEWER', 'knowledge.read'),
                ('INSPECTOR', 'case.read'),
                ('INSPECTOR', 'valuation.read'),
                ('INSPECTOR', 'review.read'),
                ('INSPECTOR', 'document.download'),
                ('INSPECTOR', 'knowledge.read'),
                ('INSPECTOR', 'audit.read')
        )
        INSERT INTO auth.role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM grants g
        JOIN auth.roles r ON r.role_code = g.role_code
        JOIN auth.permissions p ON p.permission_code = g.permission_code
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )

    op.execute("ALTER TABLE valuation.change_logs ADD COLUMN operation_id uuid")
    op.execute("ALTER TABLE history.change_logs ADD COLUMN operation_id uuid")
    op.execute(
        "CREATE INDEX idx_valuation_change_logs_operation ON valuation.change_logs(operation_id) WHERE operation_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_history_change_logs_operation ON history.change_logs(operation_id) WHERE operation_id IS NOT NULL"
    )
    op.execute(
        """
        COMMENT ON TABLE valuation.change_logs IS
        '估價業務欄位級修改紀錄；供估價表差異與修改前後值追蹤'
        """
    )
    op.execute(
        """
        COMMENT ON TABLE history.change_logs IS
        '跨模組系統稽核紀錄；供案件、審查、文件、權限與知識資料變更追蹤'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN valuation.change_logs.operation_id IS
        '同一次業務操作的關聯 UUID；可與 history.change_logs.operation_id 對應'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN history.change_logs.operation_id IS
        '同一次系統操作的關聯 UUID；可與 valuation.change_logs.operation_id 對應'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS history.idx_history_change_logs_operation")
    op.execute("DROP INDEX IF EXISTS valuation.idx_valuation_change_logs_operation")
    op.execute("ALTER TABLE history.change_logs DROP COLUMN operation_id")
    op.execute("ALTER TABLE valuation.change_logs DROP COLUMN operation_id")

    op.execute(
        """
        DELETE FROM auth.role_permissions rp
        USING auth.roles r, auth.permissions p
        WHERE rp.role_id = r.role_id
          AND rp.permission_id = p.permission_id
          AND r.role_code IN ('REVIEWER', 'INSPECTOR', 'APPRAISER')
          AND p.permission_code IN (
              'case.read', 'case.create', 'case.update',
              'valuation.read', 'valuation.update',
              'review.read', 'review.execute', 'review.decide',
              'document.upload', 'document.download',
              'knowledge.read', 'audit.read'
          )
        """
    )
    op.execute(
        """
        DELETE FROM auth.roles r
        WHERE r.role_code IN ('REVIEWER', 'INSPECTOR', 'APPRAISER')
          AND NOT EXISTS (SELECT 1 FROM auth.user_roles ur WHERE ur.role_id = r.role_id)
        """
    )
    op.execute(
        """
        DELETE FROM auth.permissions p
        WHERE p.permission_code IN (
            'case.read', 'case.create', 'case.update',
            'valuation.read', 'valuation.update',
            'review.read', 'review.execute', 'review.decide',
            'document.upload', 'document.download',
            'knowledge.read', 'audit.read'
        )
          AND NOT EXISTS (
              SELECT 1 FROM auth.role_permissions rp
              WHERE rp.permission_id = p.permission_id
          )
        """
    )

    for schema, table, constraint, _column in reversed(USER_FOREIGN_KEYS):
        op.execute(f"ALTER TABLE {schema}.{table} DROP CONSTRAINT {constraint}")
