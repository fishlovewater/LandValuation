import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg.types.json import Jsonb

from tests.integration.schema_assertions import column_names, table_exists, unique_columns


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260901_0012_valuation_review_submission_handoff.py"
)
RUNTIME_ROLE_SQL_PATH = (
    PROJECT_ROOT / "tests" / "integration" / "sql" / "001_runtime_role.sql"
)
INTEGRATION_COMPOSE_PATH = PROJECT_ROOT / "docker-compose.integration.yml"
PRIMARY_COMPOSE_PATH = PROJECT_ROOT / "docker-compose.yml"
PRIMARY_ROLE_INIT_SQL_PATH = (
    PROJECT_ROOT / "database" / "role-init" / "001_land_valuation_app.sql"
)


@dataclass
class _SubmissionFixtureGraph:
    user_id: UUID
    case_id: UUID
    review_id: UUID
    validation_run_id: UUID
    document_id: UUID
    submission_ids: set[UUID] = field(default_factory=set)


def _delete_submission_fixture_graph(cursor, graph: _SubmissionFixtureGraph) -> None:
    submission_ids = tuple(graph.submission_ids)
    if submission_ids:
        cursor.execute(
            """
            UPDATE review.reviews
            SET latest_submission_id = NULL
            WHERE review_id = %s AND latest_submission_id = ANY(%s)
            """,
            (graph.review_id, list(submission_ids)),
        )
        cursor.execute(
            """
            UPDATE valuation.validation_runs
            SET submission_id = NULL
            WHERE validation_run_id = %s AND submission_id = ANY(%s)
            """,
            (graph.validation_run_id, list(submission_ids)),
        )
        cursor.execute(
            "UPDATE valuation.review_submissions "
            "SET supersedes_submission_id = NULL "
            "WHERE submission_id = ANY(%s)",
            (list(submission_ids),),
        )
        cursor.execute(
            "DELETE FROM valuation.review_submissions "
            "WHERE submission_id = ANY(%s)",
            (list(submission_ids),),
        )

    cursor.execute(
        "DELETE FROM valuation.validation_runs WHERE validation_run_id = %s",
        (graph.validation_run_id,),
    )
    cursor.execute(
        "DELETE FROM review.reviews WHERE review_id = %s", (graph.review_id,)
    )
    cursor.execute(
        "DELETE FROM valuation.documents WHERE document_id = %s",
        (graph.document_id,),
    )
    cursor.execute(
        "DELETE FROM valuation.cases WHERE case_id = %s", (graph.case_id,)
    )
    cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (graph.user_id,))


@pytest.fixture
def submission_fixture_graphs(admin_cursor):
    graphs: list[_SubmissionFixtureGraph] = []
    try:
        yield graphs
    finally:
        admin_cursor.connection.rollback()
        try:
            for graph in graphs:
                _delete_submission_fixture_graph(admin_cursor, graph)
            admin_cursor.connection.commit()
        except Exception:
            admin_cursor.connection.rollback()
            raise


def _repository_alembic_head() -> str:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None, "repository must have exactly one Alembic head"
    return head


class TestMigrationRoundtripIsolation:
    def test_01_downgrade_can_exit_before_reupgrade(self, migration_roundtrip):
        migration_roundtrip("downgrade", "20260901_0009")
        return

    def test_02_successor_starts_at_alembic_head(self, admin_cursor):
        admin_cursor.execute("SELECT version_num FROM alembic_version")
        assert admin_cursor.fetchone() == (_repository_alembic_head(),)

        required_columns = {
            ("valuation", "valuations"): {"request_id"},
            ("valuation", "validation_runs"): {"request_id", "submission_id"},
            ("valuation", "validation_findings"): {"request_id"},
            ("history", "case_events"): {"request_id"},
            ("valuation", "form_instances"): {"form_content"},
            ("valuation", "comparison_targets"): {"display_order"},
            ("valuation", "comparison_factor_values"): {
                "benchmark_factor_level_id",
                "comparable_factor_level_id",
            },
            ("valuation", "comparison_analyses"): {
                "rule_version_id",
                "calculation_snapshot",
                "calculated_by_user_id",
                "calculated_at",
            },
            ("valuation", "benchmark_lands"): {"latitude", "longitude"},
            ("knowledge", "documents"): {"storage_etag"},
            ("valuation", "rule_versions"): {
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
            },
            ("review", "reviews"): {"latest_submission_id"},
        }
        for (schema, table), columns in required_columns.items():
            assert columns <= set(column_names(admin_cursor, table, schema))

        assert table_exists(admin_cursor, "rule_version_sources", "valuation")
        assert table_exists(admin_cursor, "review_submissions", "valuation")


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


def _seed_submission_graph(
    cursor,
    *,
    cleanup: list[_SubmissionFixtureGraph] | None = None,
) -> dict[str, object]:
    user_id = uuid4()
    case_id = uuid4()
    review_id = uuid4()
    validation_run_id = uuid4()
    document_id = uuid4()
    submission_id = uuid4()

    cursor.execute(
        """
        INSERT INTO auth.users (
            user_id, username, email, password_hash, display_name,
            is_active, created_at, updated_at
        ) VALUES (%s, %s, %s, 'unused', 'Submission schema test', true, now(), now())
        """,
        (user_id, f"submission-{user_id}", f"{user_id}@example.test"),
    )
    cursor.execute(
        """
        INSERT INTO valuation.cases (
            case_id, case_no, case_title, case_type, valuation_base_date,
            city_code, district_code
        ) VALUES (%s, %s, 'Submission schema test', 'LAND', current_date, '01', '001')
        """,
        (case_id, f"CASE-{uuid4().hex[:12]}"),
    )
    cursor.execute(
        """
        INSERT INTO review.reviews (review_id, case_id, review_type, review_status)
        VALUES (%s, %s, 'SMART_REVIEW', 'REVIEW_REQUIRED')
        """,
        (review_id, case_id),
    )
    cursor.execute(
        """
        INSERT INTO valuation.validation_runs (
            validation_run_id, case_id, run_status, review_id, ruleset_snapshot
        ) VALUES (%s, %s, 'COMPLETED', %s, '{"rules": []}'::jsonb)
        """,
        (validation_run_id, case_id, review_id),
    )
    cursor.execute(
        """
        INSERT INTO valuation.documents (
            document_id, case_id, document_type, original_filename, mime_type,
            bucket_name, object_key, checksum_sha256, file_size_bytes, version_no,
            is_active, document_group_id
        ) VALUES (
            %s, %s, 'APPRAISAL_REPORT', 'report.pdf', 'application/pdf',
            'land-valuation', %s, %s, 1, 1, true, %s
        )
        """,
        (
            document_id,
            case_id,
            f"cases/{case_id}/{document_id}.pdf",
            uuid4().hex + uuid4().hex,
            uuid4(),
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.review_submissions (
            submission_id, review_id, case_id, submission_no,
            submitted_by_user_id, source_validation_run_id,
            source_report_document_id, input_snapshot, input_fingerprint,
            request_id
        ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, %s)
        """,
        (
            submission_id,
            review_id,
            case_id,
            user_id,
            validation_run_id,
            document_id,
            Jsonb({"schema_version": 1}),
            "a" * 64,
            uuid4(),
        ),
    )
    if cleanup is not None:
        cleanup.append(
            _SubmissionFixtureGraph(
                user_id=user_id,
                case_id=case_id,
                review_id=review_id,
                validation_run_id=validation_run_id,
                document_id=document_id,
                submission_ids={submission_id},
            )
        )
    return {
        "user_id": user_id,
        "case_id": case_id,
        "review_id": review_id,
        "validation_run_id": validation_run_id,
        "document_id": document_id,
        "submission_id": submission_id,
    }


def _insert_submission(cursor, ids: dict[str, object], **overrides: object) -> None:
    values = {
        "submission_id": uuid4(),
        "review_id": ids["review_id"],
        "case_id": ids["case_id"],
        "submission_no": 2,
        "submitted_by_user_id": ids["user_id"],
        "source_validation_run_id": ids["validation_run_id"],
        "source_report_document_id": ids["document_id"],
        "input_snapshot": Jsonb({"schema_version": 1}),
        "input_fingerprint": "b" * 64,
        "supersedes_submission_id": None,
        "request_id": uuid4(),
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join("%s" for _ in values)
    cursor.execute(
        f"INSERT INTO valuation.review_submissions ({columns}) "
        f"VALUES ({placeholders})",
        tuple(values.values()),
    )


def test_submission_schema(db_cursor):
    assert set(column_names(db_cursor, "review_submissions", "valuation")) == {
        "submission_id",
        "review_id",
        "case_id",
        "submission_no",
        "submitted_by_user_id",
        "submitted_at",
        "source_validation_run_id",
        "source_report_document_id",
        "input_snapshot",
        "input_fingerprint",
        "supersedes_submission_id",
        "request_id",
    }
    assert unique_columns(db_cursor, "review_submissions", "valuation") >= {
        ("review_id", "submission_no"),
        ("case_id", "request_id"),
        ("review_id", "submission_id"),
    }

    db_cursor.execute(
        """
        SELECT column_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'valuation' AND table_name = 'review_submissions'
        """
    )
    nullability = dict(db_cursor.fetchall())
    assert nullability["supersedes_submission_id"] == "YES"
    assert set(nullability) - {"supersedes_submission_id"} == {
        column for column, nullable in nullability.items() if nullable == "NO"
    }

    db_cursor.execute(
        """
        SELECT data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'valuation'
          AND table_name = 'review_submissions'
          AND column_name = 'input_fingerprint'
        """
    )
    assert db_cursor.fetchone() == ("character", 64)


def test_submission_foreign_keys_and_handoff_columns(admin_cursor):
    supersedes = _constraint_definition(
        admin_cursor,
        "valuation",
        "review_submissions",
        "fk_review_submissions_supersedes",
    )
    assert (
        "FOREIGN KEY (review_id, supersedes_submission_id) "
        "REFERENCES valuation.review_submissions(review_id, submission_id)"
    ) in supersedes

    assert "REFERENCES review.reviews(review_id)" in _constraint_definition(
        admin_cursor,
        "valuation",
        "review_submissions",
        "fk_review_submissions_review",
    )
    assert "REFERENCES valuation.cases(case_id)" in _constraint_definition(
        admin_cursor,
        "valuation",
        "review_submissions",
        "fk_review_submissions_case",
    )
    assert "REFERENCES auth.users(user_id)" in _constraint_definition(
        admin_cursor,
        "valuation",
        "review_submissions",
        "fk_review_submissions_submitted_by",
    )
    assert "REFERENCES valuation.validation_runs(validation_run_id)" in (
        _constraint_definition(
            admin_cursor,
            "valuation",
            "review_submissions",
            "fk_review_submissions_source_validation_run",
        )
    )
    assert "REFERENCES valuation.documents(document_id)" in _constraint_definition(
        admin_cursor,
        "valuation",
        "review_submissions",
        "fk_review_submissions_source_report_document",
    )

    assert "latest_submission_id" in column_names(admin_cursor, "reviews", "review")
    assert "submission_id" in column_names(
        admin_cursor, "validation_runs", "valuation"
    )
    assert "REFERENCES valuation.review_submissions(submission_id)" in (
        _constraint_definition(
            admin_cursor, "review", "reviews", "fk_reviews_latest_submission"
        )
    )
    assert "REFERENCES valuation.review_submissions(submission_id)" in (
        _constraint_definition(
            admin_cursor,
            "valuation",
            "validation_runs",
            "fk_validation_runs_submission",
        )
    )
    admin_cursor.execute(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE schemaname = 'valuation'
          AND indexname = 'idx_validation_runs_submission'
        """
    )
    assert "(submission_id)" in admin_cursor.fetchone()[0]


def test_submission_checks_and_handoff_statuses(
    admin_cursor, submission_fixture_graphs
):
    ids = _seed_submission_graph(admin_cursor, cleanup=submission_fixture_graphs)

    for values, expected_constraint in (
        ({"submission_no": 0}, "ck_review_submissions_submission_no"),
        ({"input_fingerprint": "A" * 64}, "ck_review_submissions_fingerprint"),
        ({"input_snapshot": Jsonb([])}, "ck_review_submissions_input_snapshot"),
    ):
        admin_cursor.execute("SAVEPOINT invalid_submission")
        try:
            with pytest.raises(Exception) as raised:
                _insert_submission(admin_cursor, ids, **values)
            assert expected_constraint in str(raised.value)
        finally:
            admin_cursor.execute("ROLLBACK TO SAVEPOINT invalid_submission")
            admin_cursor.execute("RELEASE SAVEPOINT invalid_submission")

    case_status = _constraint_definition(
        admin_cursor, "valuation", "cases", "ck_cases_status"
    )
    for status in ("IN_REVIEW", "REVISION_REQUIRED", "REVIEW_COMPLETED"):
        assert status in case_status
    review_status = _constraint_definition(
        admin_cursor, "review", "reviews", "ck_reviews_status"
    )
    assert "RETURNED_FOR_REVISION" in review_status


def test_composite_supersedes_fk_rejects_submission_from_another_review(
    admin_cursor, submission_fixture_graphs
):
    first = _seed_submission_graph(admin_cursor, cleanup=submission_fixture_graphs)
    second = _seed_submission_graph(admin_cursor, cleanup=submission_fixture_graphs)

    admin_cursor.execute("SAVEPOINT cross_review_supersedes")
    try:
        with pytest.raises(Exception) as raised:
            _insert_submission(
                admin_cursor,
                second,
                supersedes_submission_id=first["submission_id"],
            )
        assert "fk_review_submissions_supersedes" in str(raised.value)
    finally:
        admin_cursor.execute("ROLLBACK TO SAVEPOINT cross_review_supersedes")
        admin_cursor.execute("RELEASE SAVEPOINT cross_review_supersedes")


def test_migration_owner_is_nonmember_and_can_run_migrations(
    admin_cursor, db_cursor, migration_roundtrip
):
    admin_cursor.execute(
        "SELECT current_user, "
        "pg_has_role(current_user, 'land_valuation_app', 'MEMBER'), "
        "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
    )
    migration_user, migration_is_app_member, migration_is_superuser = (
        admin_cursor.fetchone()
    )
    db_cursor.execute(
        "SELECT current_user, pg_has_role(current_user, 'land_valuation_app', 'MEMBER')"
    )
    runtime_user, runtime_is_app_member = db_cursor.fetchone()

    assert migration_user != runtime_user
    assert migration_is_app_member is False
    assert migration_is_superuser is False
    assert runtime_is_app_member is True
    migration_roundtrip("upgrade", "head")


def test_integration_harness_separates_bootstrap_migration_and_runtime_roles():
    role_sql = RUNTIME_ROLE_SQL_PATH.read_text(encoding="utf-8")
    compose = INTEGRATION_COMPOSE_PATH.read_text(encoding="utf-8")

    assert (
        "CREATE ROLE land_valuation_migrator LOGIN PASSWORD "
        "'integration-migration-owner'" in role_sql
    )
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION" in role_sql
    assert (
        "ALTER DATABASE :\"database_name\" OWNER TO land_valuation_migrator"
        in role_sql
    )
    assert "REVOKE land_valuation_app FROM land_valuation_migrator" in role_sql
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE land_valuation_migrator" in role_sql
    assert "ALTER ROLE land_valuation_migrator NOSUPERUSER" not in role_sql
    assert "POSTGRES_USER: postgres" in compose
    assert "POSTGRES_PASSWORD: integration-bootstrap-owner" in compose
    assert "pg_isready -U postgres" in compose
    assert "POSTGRES_HOST: db" in compose
    assert 'POSTGRES_PORT: "5432"' in compose
    assert "POSTGRES_USER: land_valuation_migrator" in compose
    assert "POSTGRES_PASSWORD: integration-migration-owner" in compose
    assert (
        "postgresql+psycopg://land_valuation_migrator:"
        "integration-migration-owner@db:5432/${POSTGRES_DB}" in compose
    )
    assert "postgresql+psycopg://postgres:" not in compose


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="requires Docker Compose CLI"
)
def test_primary_compose_provisions_idempotent_app_group_before_migrations():
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            ".env.example",
            "-f",
            str(PRIMARY_COMPOSE_PATH),
            "config",
            "--format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    primary_config = json.loads(result.stdout)
    role_init = primary_config["services"]["db-role-init"]
    db_environment = primary_config["services"]["db"]["environment"]
    assert PRIMARY_ROLE_INIT_SQL_PATH.is_file()
    role_sql = PRIMARY_ROLE_INIT_SQL_PATH.read_text(encoding="utf-8")

    assert role_init["depends_on"]["db"]["condition"] == "service_healthy"
    assert (
        primary_config["services"]["migrate"]["depends_on"]["db-role-init"][
            "condition"
        ]
        == "service_completed_successfully"
    )
    assert role_init["entrypoint"] == ["psql"]
    assert role_init["environment"] == {
        "PGHOST": "db",
        "PGDATABASE": db_environment["POSTGRES_DB"],
        "PGUSER": db_environment["POSTGRES_USER"],
        "PGPASSWORD": db_environment["POSTGRES_PASSWORD"],
    }
    assert role_init["command"] == [
        "-v",
        "ON_ERROR_STOP=1",
        "-v",
        "app_group_role=land_valuation_app",
        "-v",
        f"app_login_role={role_init['environment']['PGUSER']}",
        "-f",
        "/role-init/001_land_valuation_app.sql",
    ]
    assert "CREATE ROLE %I NOLOGIN" in role_sql
    assert "WHERE NOT EXISTS" in role_sql
    assert "GRANT %I TO %I" in role_sql
    assert "pg_has_role" not in role_sql
    assert "FROM pg_auth_members AS membership" in role_sql
    assert "group_role.oid = membership.roleid" in role_sql
    assert "login_role.oid = membership.member" in role_sql
    assert "group_role.rolname = :'app_group_role'" in role_sql
    assert "login_role.rolname = :'app_login_role'" in role_sql
    assert ":'app_group_role'" in role_sql
    assert ":'app_login_role'" in role_sql


@pytest.mark.parametrize("statement", ["UPDATE", "DELETE"])
def test_runtime_role_cannot_mutate_review_submissions(
    admin_cursor, db_cursor, submission_fixture_graphs, statement: str
):
    ids = _seed_submission_graph(admin_cursor, cleanup=submission_fixture_graphs)
    admin_cursor.connection.commit()

    db_cursor.execute("SAVEPOINT immutable_submission")
    try:
        with pytest.raises(Exception) as raised:
            if statement == "UPDATE":
                db_cursor.execute(
                    """
                    UPDATE valuation.review_submissions
                    SET input_snapshot = '{"changed": true}'::jsonb
                    WHERE submission_id = %s
                    """,
                    (ids["submission_id"],),
                )
            else:
                db_cursor.execute(
                    "DELETE FROM valuation.review_submissions WHERE submission_id = %s",
                    (ids["submission_id"],),
                )
        assert "permission denied for table review_submissions" in str(
            raised.value
        ).lower()
    finally:
        db_cursor.execute("ROLLBACK TO SAVEPOINT immutable_submission")
        db_cursor.execute("RELEASE SAVEPOINT immutable_submission")

    assert os.environ["POSTGRES_DB"].startswith("land_valuation_test_vr_")
    admin_cursor.execute(
        "DELETE FROM valuation.review_submissions WHERE submission_id = %s",
        (ids["submission_id"],),
    )
    assert admin_cursor.rowcount == 1
    admin_cursor.connection.commit()


def test_downgrade_refuses_submission_then_succeeds_after_owner_cleanup(
    admin_cursor, submission_fixture_graphs, migration_roundtrip
):
    _seed_submission_graph(admin_cursor, cleanup=submission_fixture_graphs)
    admin_cursor.connection.commit()

    result = migration_roundtrip(
        "downgrade", "20260901_0011", expect_success=False
    )
    assert "cannot downgrade while review submissions exist" in (
        result.stdout + result.stderr
    ).lower()
    assert table_exists(admin_cursor, "review_submissions", "valuation")

    _delete_submission_fixture_graph(admin_cursor, submission_fixture_graphs[-1])
    admin_cursor.connection.commit()
    migration_roundtrip("downgrade", "20260901_0011")
    migration_roundtrip("upgrade", "head")


def test_downgrade_locks_submission_dependencies_before_guard_queries():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.index("def downgrade")
    lock = source.index("LOCK TABLE", downgrade)
    guard = source.index("IF EXISTS", downgrade)

    assert "valuation.review_submissions" in source[lock:guard]
    assert "valuation.validation_runs" in source[lock:guard]
    assert "review.reviews" in source[lock:guard]
    assert lock < guard


def test_migration_owner_updates_are_not_silently_replaced_with_old_row():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "IF TG_OP = 'DELETE' THEN" in source
    assert "RETURN NEW;" in source


def test_matching_orm_and_pydantic_handoff_types():
    from app.review.models import Review, ValidationRun
    from app.review.schemas import ReviewRead, ValidationRunRead
    from app.valuation.models import ReviewSubmissionRecord
    from app.valuation.schemas import CaseStatus

    columns = ReviewSubmissionRecord.__table__.c
    assert set(columns.keys()) == {
        "submission_id",
        "review_id",
        "case_id",
        "submission_no",
        "submitted_by_user_id",
        "submitted_at",
        "source_validation_run_id",
        "source_report_document_id",
        "input_snapshot",
        "input_fingerprint",
        "supersedes_submission_id",
        "request_id",
    }
    assert columns.supersedes_submission_id.nullable
    assert all(
        not column.nullable
        for column in columns
        if column.name != "supersedes_submission_id"
    )
    assert Review.__table__.c.latest_submission_id.nullable
    assert ValidationRun.__table__.c.submission_id.nullable
    assert "latest_submission_id" in ReviewRead.model_fields
    assert "submission_id" in ValidationRunRead.model_fields
    assert {
        "IN_REVIEW",
        "REVISION_REQUIRED",
        "REVIEW_COMPLETED",
    } <= {status.value for status in CaseStatus}


def test_submission_orm_retains_handoff_integrity_constraints():
    from app.valuation.models import ReviewSubmissionRecord

    table = ReviewSubmissionRecord.__table__
    assert {
        constraint.name
        for constraint in table.constraints
        if constraint.name is not None
    } >= {
        "uq_review_submissions_review_no",
        "uq_review_submissions_case_request",
        "uq_review_submissions_review_id",
        "ck_review_submissions_submission_no",
        "ck_review_submissions_fingerprint",
        "ck_review_submissions_input_snapshot",
        "fk_review_submissions_supersedes",
    }
