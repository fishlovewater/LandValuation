import os
import subprocess
import sys

import psycopg
import pytest
from sqlalchemy.engine import make_url


def _database_url(name: str) -> str:
    return os.environ[name]


def _psycopg_connection_url(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


def _assert_separate_database_users() -> None:
    runtime_user = make_url(_database_url("DATABASE_URL")).username
    migration_user = make_url(_database_url("MIGRATION_DATABASE_URL")).username
    assert runtime_user and migration_user and runtime_user != migration_user


@pytest.fixture
def db_cursor():
    _assert_separate_database_users()
    connection = psycopg.connect(_psycopg_connection_url(_database_url("DATABASE_URL")))
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def admin_cursor():
    _assert_separate_database_users()
    connection = psycopg.connect(
        _psycopg_connection_url(_database_url("MIGRATION_DATABASE_URL"))
    )
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def alembic_to():
    migration_database_url = _database_url("MIGRATION_DATABASE_URL")
    _assert_separate_database_users()

    def migrate(revision: str, *, expect_success: bool = True):
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = migration_database_url
        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", revision],
                capture_output=True,
                text=True,
            )
            assert (result.returncode == 0) is expect_success, result.stdout + result.stderr
            return result
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

    return migrate
