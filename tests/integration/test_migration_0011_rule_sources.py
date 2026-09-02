import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from tests.integration.schema_assertions import column_names, table_exists, unique_columns


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260901_0011_valuation_rule_pack_sources.py"
)


def _run_alembic(command: str, revision: str, *, expect_success: bool = True):
    env = os.environ.copy()
    if env.get("MIGRATION_DATABASE_URL"):
        env["DATABASE_URL"] = env["MIGRATION_DATABASE_URL"]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is expect_success, result.stdout + result.stderr
    return result


def _constraint_definition(cursor, schema: str, table: str, name: str) -> str:
    cursor.execute(
        """
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint AS c
        JOIN pg_class AS r ON r.oid = c.conrelid
        JOIN pg_namespace AS n ON n.oid = r.relnamespace
        WHERE n.nspname = %s AND r.relname = %s AND c.conname = %s
        """,
        (schema, table, name),
    )
    row = cursor.fetchone()
    assert row is not None, f"missing constraint {schema}.{table}.{name}"
    return row[0]


def _partial_unique_index(cursor, schema: str, name: str) -> tuple[bool, str, list[str]]:
    cursor.execute(
        """
        SELECT index_row.indisunique,
               pg_get_expr(index_row.indpred, index_row.indrelid),
               array_agg(attribute.attname ORDER BY key.ordinality)
        FROM pg_index AS index_row
        JOIN pg_class AS index_relation ON index_relation.oid = index_row.indexrelid
        JOIN pg_class AS table_relation ON table_relation.oid = index_row.indrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_relation.relnamespace
        CROSS JOIN LATERAL unnest(index_row.indkey) WITH ORDINALITY
            AS key(attribute_number, ordinality)
        JOIN pg_attribute AS attribute
            ON attribute.attrelid = table_relation.oid
           AND attribute.attnum = key.attribute_number
        WHERE namespace.nspname = %s AND index_relation.relname = %s
        GROUP BY index_row.indexrelid, index_row.indisunique,
                 index_row.indpred, index_row.indrelid
        """,
        (schema, name),
    )
    row = cursor.fetchone()
    assert row is not None, f"missing index {schema}.{name}"
    return bool(row[0]), str(row[1]), list(row[2])


def test_partial_unique_index_returns_catalog_tuple() -> None:
    class Cursor:
        def execute(self, *_args) -> None:
            pass

        def fetchone(self) -> tuple[bool, str, list[str]]:
            return True, "is_primary", ["rule_version_id"]

    assert _partial_unique_index(
        Cursor(), "valuation", "uq_rule_version_sources_primary"
    ) == (True, "is_primary", ["rule_version_id"])


def _create_rule_version(cursor) -> object:
    rule_version_id = uuid4()
    cursor.execute(
        """
        INSERT INTO valuation.rule_versions (
            rule_version_id, rule_set_code, version_no, version_name,
            effective_from, status
        ) VALUES (%s, %s, %s, %s, CURRENT_DATE, 'DRAFT')
        """,
        (rule_version_id, f"MIG-0011-{uuid4().hex[:10]}", 1, "Migration test"),
    )
    return rule_version_id


def _create_knowledge_document(
    cursor, *, document_type: str = "STANDARD", storage_etag: str | None = None
) -> object:
    document_id = uuid4()
    cursor.execute(
        """
        INSERT INTO knowledge.documents (
            document_id, document_code, title, document_type,
            original_filename, object_key, checksum_sha256, storage_etag
        ) VALUES (%s, %s, 'Migration source', %s, 'source.pdf', %s, %s, %s)
        """,
        (
            document_id,
            f"MIG-0011-DOC-{uuid4().hex[:10]}",
            document_type,
            f"knowledge/{document_id}/source.pdf",
            "a" * 64,
            storage_etag,
        ),
    )
    return document_id


def test_rule_source_contract_uses_database_catalogs(admin_cursor):
    assert table_exists(admin_cursor, "rule_version_sources", "valuation")
    assert set(column_names(admin_cursor, "rule_versions", "valuation")) >= {
        "jurisdiction_code",
        "district_scope",
        "land_use_types",
        "formula_code",
        "rounding_code",
        "import_status",
        "import_summary",
        "verified_by_user_id",
        "verified_at",
        "effective_date_status",
    }

    admin_cursor.execute(
        """
        SELECT data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'valuation' AND table_name = 'rule_versions'
          AND column_name IN ('district_scope', 'land_use_types', 'import_summary')
        ORDER BY column_name
        """
    )
    assert admin_cursor.fetchall() == [
        ("jsonb", "jsonb"),
        ("jsonb", "jsonb"),
        ("jsonb", "jsonb"),
    ]

    for name, fragment in (
        ("ck_rule_versions_jurisdiction", "NEW_TAIPEI_CITY"),
        ("ck_rule_versions_district_scope", "jsonb_typeof"),
        ("ck_rule_versions_land_use_types", "jsonb_typeof"),
        ("ck_rule_versions_import_summary", "jsonb_typeof"),
        ("ck_rule_versions_verification", "verified_by_user_id"),
        ("ck_rule_versions_effective_date_state", "effective_date_status"),
    ):
        assert fragment in _constraint_definition(
            admin_cursor, "valuation", "rule_versions", name
        )

    assert "UNIQUE" in _constraint_definition(
        admin_cursor,
        "valuation",
        "rule_version_sources",
        "uq_rule_version_sources_order",
    )
    assert {
        ("rule_version_id", "source_document_id"),
        ("rule_version_id", "source_order"),
    } <= unique_columns(admin_cursor, "rule_version_sources", "valuation")
    is_unique, predicate, index_columns = _partial_unique_index(
        admin_cursor, "valuation", "uq_rule_version_sources_primary"
    )
    assert is_unique is True
    assert index_columns == ["rule_version_id"]
    assert predicate.replace("(", "").replace(")", "").strip() == "is_primary"
    assert "EXAMPLE_REFERENCE" in _constraint_definition(
        admin_cursor, "knowledge", "documents", "ck_knowledge_document_type"
    )
    document_id = uuid4()
    admin_cursor.execute("SAVEPOINT example_reference_document")
    try:
        admin_cursor.execute(
            """
            INSERT INTO knowledge.documents (
                document_id, document_code, title, document_type,
                original_filename, object_key, checksum_sha256
            ) VALUES (%s, %s, 'Example reference', 'EXAMPLE_REFERENCE',
                      'example.pdf', %s, %s)
            RETURNING document_type
            """,
            (
                document_id,
                f"MIG-0011-{uuid4().hex[:10]}",
                f"knowledge/{document_id}/example.pdf",
                "a" * 64,
            ),
        )
        assert admin_cursor.fetchone() == ("EXAMPLE_REFERENCE",)
    finally:
        admin_cursor.execute("ROLLBACK TO SAVEPOINT example_reference_document")
        admin_cursor.execute("RELEASE SAVEPOINT example_reference_document")


def test_rule_source_constraints_reject_invalid_json_and_duplicate_primary(admin_cursor):
    rule_version_id = _create_rule_version(admin_cursor)
    admin_cursor.execute("SAVEPOINT invalid_json")
    try:
        with pytest.raises(Exception):
            admin_cursor.execute(
                """
                UPDATE valuation.rule_versions
                SET district_scope = %s
                WHERE rule_version_id = %s
                """,
                (Jsonb([]), rule_version_id),
            )
        admin_cursor.execute("ROLLBACK TO SAVEPOINT invalid_json")
    finally:
        admin_cursor.execute("RELEASE SAVEPOINT invalid_json")

    admin_cursor.execute("SAVEPOINT invalid_verification_pair")
    try:
        with pytest.raises(Exception):
            admin_cursor.execute(
                """
                UPDATE valuation.rule_versions
                SET verified_at = CURRENT_TIMESTAMP
                WHERE rule_version_id = %s
                """,
                (rule_version_id,),
            )
        admin_cursor.execute("ROLLBACK TO SAVEPOINT invalid_verification_pair")
    finally:
        admin_cursor.execute("RELEASE SAVEPOINT invalid_verification_pair")

    admin_cursor.execute("SET session_replication_role = replica")
    try:
        admin_cursor.execute(
            """
            INSERT INTO valuation.rule_version_sources (
                rule_version_source_id, rule_version_id, source_document_id,
                source_role, source_order, is_primary
            ) VALUES (%s, %s, %s, 'PRIMARY', 1, true)
            """,
            (uuid4(), rule_version_id, uuid4()),
        )
        admin_cursor.execute("SAVEPOINT duplicate_primary")
        with pytest.raises(Exception):
            admin_cursor.execute(
                """
                INSERT INTO valuation.rule_version_sources (
                    rule_version_source_id, rule_version_id, source_document_id,
                    source_role, source_order, is_primary
                ) VALUES (%s, %s, %s, 'LEGAL_BASIS', 2, true)
                """,
                (uuid4(), rule_version_id, uuid4()),
            )
        admin_cursor.execute("ROLLBACK TO SAVEPOINT duplicate_primary")
        admin_cursor.execute("RELEASE SAVEPOINT duplicate_primary")
        admin_cursor.execute("SAVEPOINT duplicate_source_order")
        with pytest.raises(Exception):
            admin_cursor.execute(
                """
                INSERT INTO valuation.rule_version_sources (
                    rule_version_source_id, rule_version_id, source_document_id,
                    source_role, source_order, is_primary
                ) VALUES (%s, %s, %s, 'LEGAL_BASIS', 1, false)
                """,
                (uuid4(), rule_version_id, uuid4()),
            )
        admin_cursor.execute("ROLLBACK TO SAVEPOINT duplicate_source_order")
        admin_cursor.execute("RELEASE SAVEPOINT duplicate_source_order")
    finally:
        admin_cursor.execute("SET session_replication_role = origin")


@pytest.mark.parametrize(
    "fixture_kind",
    [
        "source_link",
        "rule_metadata",
        "storage_etag",
        "example_reference",
        "unknown_effective_date",
    ],
)
def test_downgrade_refuses_each_0011_data_shape_then_succeeds_after_cleanup(
    admin_cursor, fixture_kind: str
):
    rule_version_id = None
    document_id = None
    source_link_id = None

    if fixture_kind == "source_link":
        rule_version_id = _create_rule_version(admin_cursor)
        document_id = _create_knowledge_document(admin_cursor)
        source_link_id = uuid4()
        admin_cursor.execute(
            """
            INSERT INTO valuation.rule_version_sources (
                rule_version_source_id, rule_version_id, source_document_id,
                source_role, source_order, is_primary
            ) VALUES (%s, %s, %s, 'PRIMARY', 1, true)
            """,
            (source_link_id, rule_version_id, document_id),
        )
    elif fixture_kind == "rule_metadata":
        rule_version_id = _create_rule_version(admin_cursor)
        admin_cursor.execute(
            "UPDATE valuation.rule_versions SET formula_code = 'F03' "
            "WHERE rule_version_id = %s",
            (rule_version_id,),
        )
    elif fixture_kind == "storage_etag":
        document_id = _create_knowledge_document(admin_cursor, storage_etag="etag-0011")
    elif fixture_kind == "example_reference":
        document_id = _create_knowledge_document(
            admin_cursor, document_type="EXAMPLE_REFERENCE"
        )
    elif fixture_kind == "unknown_effective_date":
        rule_version_id = _create_rule_version(admin_cursor)
        admin_cursor.execute(
            """
            UPDATE valuation.rule_versions
            SET jurisdiction_code = 'NEW_TAIPEI_CITY',
                effective_date_status = 'UNKNOWN',
                effective_from = NULL
            WHERE rule_version_id = %s
            """,
            (rule_version_id,),
        )
    else:
        raise AssertionError(f"unhandled fixture kind: {fixture_kind}")

    admin_cursor.connection.commit()
    result = _run_alembic("downgrade", "20260901_0010", expect_success=False)
    assert "cannot downgrade while rule-source migration data exists" in (
        result.stdout + result.stderr
    ).lower()

    if source_link_id is not None:
        admin_cursor.execute(
            "DELETE FROM valuation.rule_version_sources "
            "WHERE rule_version_source_id = %s",
            (source_link_id,),
        )
    if rule_version_id is not None:
        admin_cursor.execute(
            "DELETE FROM valuation.rule_versions WHERE rule_version_id = %s",
            (rule_version_id,),
        )
    if document_id is not None:
        admin_cursor.execute(
            "DELETE FROM knowledge.documents WHERE document_id = %s",
            (document_id,),
        )
    admin_cursor.connection.commit()
    _run_alembic("downgrade", "20260901_0010")
    _run_alembic("upgrade", "head")


def test_migration_is_schema_only_without_fixed_business_data():
    source = MIGRATION_PATH.read_text(encoding="utf-8").lower()

    assert "insert into valuation." not in source
    assert "update valuation." not in source
    assert "update knowledge.documents" not in source
    assert "delete from valuation." not in source
    assert "評價基準明細表範例.pdf" not in source


def test_downgrade_locks_all_0011_data_tables_before_guard_queries():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    lock_start = source.index(
        "LOCK TABLE valuation.rule_version_sources, valuation.rule_versions,"
    )
    assert "knowledge.documents IN SHARE ROW EXCLUSIVE MODE" in source
    assert lock_start < source.index("DO $$", source.index("def downgrade"))
