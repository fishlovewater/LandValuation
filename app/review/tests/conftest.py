import os
from unittest.mock import patch

import psycopg
import pytest


@pytest.fixture(scope="session", autouse=True)
def review_integration_prerequisites():
    """Prepare only the cross-schema access needed by Review API tests."""
    if os.environ.get("TEST_RUN_ID"):
        from app.storage.client import get_minio_client

        client = get_minio_client()
        bucket_name = "land-valuation"
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
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
        update={
            "app_env": "development",
            "minio_bucket": "land-valuation",
        }
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
