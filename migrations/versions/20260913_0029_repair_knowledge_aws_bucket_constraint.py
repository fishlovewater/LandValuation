"""Repair the knowledge bucket constraint after enabling AWS S3.

Revision ID: 20260913_0029
Revises: 20260913_0028
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260913_0029"
down_revision: Union[str, Sequence[str], None] = "20260913_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0028 initially addressed the valuation table correctly but used the
    # valuation constraint name on knowledge.documents.  Remove both possible
    # names so upgraded and freshly-created databases converge on one rule.
    op.execute(
        "ALTER TABLE knowledge.documents DROP CONSTRAINT IF EXISTS ck_documents_bucket"
    )
    op.execute(
        "ALTER TABLE knowledge.documents DROP CONSTRAINT IF EXISTS ck_knowledge_bucket"
    )
    op.execute(
        """
        ALTER TABLE knowledge.documents
        ADD CONSTRAINT ck_knowledge_bucket
        CHECK (bucket_name IN ('land-valuation', 'land-valuation-textract-spacey'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge.documents DROP CONSTRAINT IF EXISTS ck_knowledge_bucket"
    )
    op.execute(
        """
        ALTER TABLE knowledge.documents
        ADD CONSTRAINT ck_knowledge_bucket CHECK (bucket_name = 'land-valuation')
        """
    )
