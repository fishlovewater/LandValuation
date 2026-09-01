import os

import psycopg

from tests.integration.conftest import _psycopg_connection_url


def test_integration_environment_is_run_scoped():
    run_id = os.environ["TEST_RUN_ID"]
    assert run_id.startswith("vr-")
    assert os.environ["POSTGRES_DB"] == f"land_valuation_test_{run_id.replace('-', '_')}"
    assert os.environ["MINIO_BUCKET"] == f"land-valuation-test-{run_id}"
    assert os.environ.get("APP_ENV") == "test"


def test_runtime_and_migration_urls_connect_with_psycopg():
    for name in ("DATABASE_URL", "MIGRATION_DATABASE_URL"):
        connection_url = _psycopg_connection_url(os.environ[name])
        assert connection_url.startswith("postgresql://")
        with psycopg.connect(connection_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                assert cursor.fetchone() == (1,)
