import os
from unittest.mock import patch

import psycopg
import pytest
from sqlalchemy.engine import make_url


@pytest.fixture(scope="session", autouse=True)
def review_integration_prerequisites():
    """Prepare only the cross-schema access needed by Review API tests."""
    migration_url = os.environ.get("MIGRATION_DATABASE_URL")
    if migration_url and os.environ.get("TEST_RUN_ID"):
        connection_url = make_url(migration_url).set(
            drivername="postgresql"
        ).render_as_string(hide_password=False)
        with psycopg.connect(connection_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "GRANT USAGE ON SCHEMA auth, knowledge "
                    "TO land_valuation_app"
                )
            connection.commit()
        from app.storage.client import get_minio_client

        client = get_minio_client()
        if not client.bucket_exists("land-valuation"):
            client.make_bucket("land-valuation")
    yield


@pytest.fixture(autouse=True)
def development_only_demo_settings():
    """Keep Demo production guards while enabling integration fixtures."""
    if not os.environ.get("TEST_RUN_ID"):
        yield
        return

    from app.review import demo
    from app.storage import service as storage_service

    settings = demo.get_settings()
    if settings.app_env.lower() != "test":
        yield
        return

    development_settings = settings.model_copy(
        update={"app_env": "development", "minio_bucket": "land-valuation"}
    )
    with patch.object(
        demo, "get_settings", return_value=development_settings
    ), patch.object(
        storage_service, "get_settings", return_value=development_settings
    ):
        yield


@pytest.fixture
def postgres_connection():
    connection = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        yield connection
    finally:
        connection.close()
