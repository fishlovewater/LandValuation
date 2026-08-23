"""Use one land-valuation bucket with cases and knowledge prefixes.

Revision ID: 20260823_0002
Revises: 20260823_0001
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260823_0002"
down_revision: Union[str, Sequence[str], None] = "20260823_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE valuation.documents DROP CONSTRAINT ck_documents_bucket")
    op.execute("ALTER TABLE valuation.documents DROP CONSTRAINT ck_documents_object_key")
    op.execute(
        """
        UPDATE valuation.documents
        SET object_key = 'cases/' || ltrim(object_key, '/'),
            bucket_name = 'land-valuation'
        WHERE bucket_name = 'cases'
          AND object_key !~ '^cases/'
        """
    )
    op.execute(
        "UPDATE valuation.documents SET bucket_name = 'land-valuation' WHERE bucket_name = 'cases'"
    )
    op.execute(
        "ALTER TABLE valuation.documents ALTER COLUMN bucket_name SET DEFAULT 'land-valuation'"
    )
    op.execute(
        """
        ALTER TABLE valuation.documents
        ADD CONSTRAINT ck_documents_bucket CHECK (bucket_name = 'land-valuation'),
        ADD CONSTRAINT ck_documents_object_key CHECK (
            object_key ~ '^cases/'
            AND object_key !~ '^(https?://|/)'
            AND position('..' in object_key) = 0
        )
        """
    )

    op.execute("ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_bucket")
    op.execute("ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_object_key")
    op.execute(
        """
        UPDATE knowledge.documents
        SET object_key = 'knowledge/' || ltrim(object_key, '/'),
            bucket_name = 'land-valuation'
        WHERE bucket_name = 'knowledge'
          AND object_key !~ '^knowledge/'
        """
    )
    op.execute(
        "UPDATE knowledge.documents SET bucket_name = 'land-valuation' WHERE bucket_name = 'knowledge'"
    )
    op.execute(
        "ALTER TABLE knowledge.documents ALTER COLUMN bucket_name SET DEFAULT 'land-valuation'"
    )
    op.execute(
        """
        ALTER TABLE knowledge.documents
        ADD CONSTRAINT ck_knowledge_bucket CHECK (bucket_name = 'land-valuation'),
        ADD CONSTRAINT ck_knowledge_object_key CHECK (
            object_key ~ '^knowledge/'
            AND object_key !~ '^(https?://|/)'
            AND position('..' in object_key) = 0
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_bucket")
    op.execute("ALTER TABLE knowledge.documents DROP CONSTRAINT ck_knowledge_object_key")
    op.execute(
        """
        UPDATE knowledge.documents
        SET object_key = regexp_replace(object_key, '^knowledge/', ''),
            bucket_name = 'knowledge'
        WHERE bucket_name = 'land-valuation'
        """
    )
    op.execute("ALTER TABLE knowledge.documents ALTER COLUMN bucket_name SET DEFAULT 'knowledge'")
    op.execute(
        """
        ALTER TABLE knowledge.documents
        ADD CONSTRAINT ck_knowledge_bucket CHECK (bucket_name = 'knowledge'),
        ADD CONSTRAINT ck_knowledge_object_key CHECK (
            object_key !~ '^(https?://|/)' AND position('..' in object_key) = 0
        )
        """
    )

    op.execute("ALTER TABLE valuation.documents DROP CONSTRAINT ck_documents_bucket")
    op.execute("ALTER TABLE valuation.documents DROP CONSTRAINT ck_documents_object_key")
    op.execute(
        """
        UPDATE valuation.documents
        SET object_key = regexp_replace(object_key, '^cases/', ''),
            bucket_name = 'cases'
        WHERE bucket_name = 'land-valuation'
        """
    )
    op.execute("ALTER TABLE valuation.documents ALTER COLUMN bucket_name SET DEFAULT 'cases'")
    op.execute(
        """
        ALTER TABLE valuation.documents
        ADD CONSTRAINT ck_documents_bucket CHECK (bucket_name = 'cases'),
        ADD CONSTRAINT ck_documents_object_key CHECK (
            object_key !~ '^(https?://|/)' AND position('..' in object_key) = 0
        )
        """
    )
