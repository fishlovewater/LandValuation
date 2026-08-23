"""Create auth, valuation, review, history and knowledge schemas.

Revision ID: 20260823_0001
Revises:
Create Date: 2026-08-23
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlparse

revision: str = "20260823_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = (
    PROJECT_ROOT / "database" / "init" / "001_core_schema.sql",
    PROJECT_ROOT / "database" / "init" / "002_platform_schema.sql",
    PROJECT_ROOT / "database" / "init" / "003_knowledge_schema.sql",
)


def _schema_sql(path: Path) -> str:
    sql = path.read_text(encoding="utf-8")
    lines = [
        line
        for line in sql.splitlines()
        if line.strip().upper() not in {"BEGIN;", "COMMIT;"}
    ]
    return "\n".join(lines)


def upgrade() -> None:
    """Apply the existing reviewed PostgreSQL schema in file order."""
    connection = op.get_bind()
    for schema_file in SCHEMA_FILES:
        if not schema_file.is_file():
            raise RuntimeError(f"Missing schema file: {schema_file}")
        for statement in sqlparse.split(_schema_sql(schema_file)):
            if statement.strip():
                connection.exec_driver_sql(statement)


def downgrade() -> None:
    """Remove all application schemas created by the initial revision."""
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        DROP SCHEMA IF EXISTS knowledge CASCADE;
        DROP SCHEMA IF EXISTS history CASCADE;
        DROP SCHEMA IF EXISTS review CASCADE;
        DROP SCHEMA IF EXISTS auth CASCADE;
        DROP SCHEMA IF EXISTS valuation CASCADE;
        DROP FUNCTION IF EXISTS public.set_updated_at() CASCADE;
        """
    )
