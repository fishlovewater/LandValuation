import os
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.storage.client import get_minio_client


_MINIO_ENVIRONMENT_KEYS = (
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
)


@contextmanager
def _without_minio_credentials() -> Iterator[None]:
    previous_environment = {
        key: os.environ.get(key) for key in _MINIO_ENVIRONMENT_KEYS
    }
    for key in _MINIO_ENVIRONMENT_KEYS:
        os.environ.pop(key, None)
    get_minio_client.cache_clear()
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_minio_client.cache_clear()
        get_settings.cache_clear()


def _assert_authentication_required(response) -> None:
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_knowledge_routes_are_registered() -> None:
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/knowledge/search" in paths
    assert "/api/v1/knowledge/ask" in paths
    assert "/api/v1/knowledge/provider-status" in paths
    assert "/api/v1/knowledge/sources/{document_id}/download" in paths
    assert "/api/v1/knowledge/cases/{case_id}/context" in paths


def test_knowledge_route_requires_authentication() -> None:
    with _without_minio_credentials(), TestClient(
        app, raise_server_exceptions=False
    ) as client:
        response = client.post(
            "/api/v1/knowledge/ask", json={"question": "道路條件怎麼判斷？"}
        )

    _assert_authentication_required(response)


def test_knowledge_search_requires_authentication_without_minio_credentials() -> None:
    with _without_minio_credentials(), TestClient(
        app, raise_server_exceptions=False
    ) as client:
        response = client.post(
            "/api/v1/knowledge/search",
            json={"question": "道路條件怎麼判斷？"},
        )

    _assert_authentication_required(response)


def test_knowledge_source_download_requires_authentication_without_minio_credentials() -> None:
    with _without_minio_credentials(), TestClient(
        app, raise_server_exceptions=False
    ) as client:
        response = client.get(
            "/api/v1/knowledge/sources/00000000-0000-0000-0000-000000000000/download"
        )

    _assert_authentication_required(response)
