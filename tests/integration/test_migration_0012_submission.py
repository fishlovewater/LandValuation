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
    / "20260901_0012_valuation_review_submission_handoff.py"
)
RUNTIME_ROLE_SQL_PATH = (
    PROJECT_ROOT / "tests" / "integration" / "sql" / "001_runtime_role.sql"
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


def _seed_submission_graph(cursor) -> dict[str, object]:
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


def test_submission_checks_and_handoff_statuses(admin_cursor):
    ids = _seed_submission_graph(admin_cursor)

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


def test_composite_supersedes_fk_rejects_submission_from_another_review(admin_cursor):
    first = _seed_submission_graph(admin_cursor)
    second = _seed_submission_graph(admin_cursor)

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
    admin_cursor, db_cursor
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
    _run_alembic("upgrade", "head")


def test_runtime_role_harness_demotes_the_migration_owner_after_setup():
    source = RUNTIME_ROLE_SQL_PATH.read_text(encoding="utf-8")

    demotion = source.index("ALTER ROLE land_valuation_migrator NOSUPERUSER")
    privileges = source.index("ALTER DEFAULT PRIVILEGES")
    assert privileges < demotion


@pytest.mark.parametrize("statement", ["UPDATE", "DELETE"])
def test_runtime_role_cannot_mutate_review_submissions(
    admin_cursor, db_cursor, statement: str
):
    ids = _seed_submission_graph(admin_cursor)
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
        assert "review submissions are immutable" in str(raised.value).lower()
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


def test_downgrade_refuses_submission_then_succeeds_after_owner_cleanup(admin_cursor):
    ids = _seed_submission_graph(admin_cursor)
    admin_cursor.connection.commit()

    result = _run_alembic("downgrade", "20260901_0011", expect_success=False)
    assert "cannot downgrade while review submissions exist" in (
        result.stdout + result.stderr
    ).lower()
    assert table_exists(admin_cursor, "review_submissions", "valuation")

    admin_cursor.execute(
        "DELETE FROM valuation.review_submissions WHERE submission_id = %s",
        (ids["submission_id"],),
    )
    admin_cursor.connection.commit()
    _run_alembic("downgrade", "20260901_0011")
    _run_alembic("upgrade", "head")


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
