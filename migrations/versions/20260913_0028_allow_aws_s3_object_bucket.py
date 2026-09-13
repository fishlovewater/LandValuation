"""Allow the configured AWS Demo object bucket in document metadata.

Revision ID: 20260913_0028
Revises: 20260913_0027
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260913_0028"
down_revision: Union[str, Sequence[str], None] = "20260913_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LOCAL_BUCKET = "land-valuation"
_AWS_DEMO_BUCKET = "land-valuation-textract-spacey"


def _replace_bucket_constraint(table_name: str, constraint_name: str) -> None:
    op.execute(
        f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}"
    )
    op.execute(
        f"""
        ALTER TABLE {table_name}
        ADD CONSTRAINT {constraint_name}
        CHECK (bucket_name IN ('{_LOCAL_BUCKET}', '{_AWS_DEMO_BUCKET}'))
        """
    )


def upgrade() -> None:
    # The AWS S3 bucket is an object-store location, not an object key.  Keep
    # the key safety checks unchanged while accepting both the local MinIO
    # bucket and the configured AWS Demo bucket.
    _replace_bucket_constraint("valuation.documents", "ck_documents_bucket")
    _replace_bucket_constraint("knowledge.documents", "ck_knowledge_bucket")


def downgrade() -> None:
    for table_name in ("valuation.documents", "knowledge.documents"):
        constraint_name = f"ck_{table_name.split('.')[1]}_bucket"
        op.execute(
            f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}"
        )
        op.execute(
            f"""
            ALTER TABLE {table_name}
            ADD CONSTRAINT {constraint_name}
            CHECK (bucket_name = '{_LOCAL_BUCKET}')
            """
        )
