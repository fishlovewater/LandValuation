import os
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.knowledge import router as knowledge_router
from app.knowledge.schemas import KnowledgeSearchRequest
from app.knowledge.runtime_extraction import RuntimeKnowledgeExtractor
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


@pytest.mark.asyncio
async def test_retrieval_bounds_listing_and_applies_persisted_size_limit(monkeypatch) -> None:
    object_key = "knowledge/manuals/persisted/oversized.txt"
    persisted_document = SimpleNamespace(
        document_id=uuid4(),
        object_key=object_key,
        file_size_bytes=101,
        original_filename="oversized.txt",
        mime_type="text/plain",
        document_type="OTHER",
    )
    settings = SimpleNamespace(
        minio_bucket="land-valuation",
        knowledge_runtime_max_objects=1,
        knowledge_runtime_max_object_bytes=100,
        knowledge_runtime_max_total_bytes=1000,
        knowledge_runtime_max_total_characters=1000,
    )

    class _Repository:
        async def documents_by_object_key(self):
            return {object_key: persisted_document}

        async def retrieval_candidates(self, **_kwargs):
            return []

    class _Storage:
        def __init__(self):
            self.list_calls = []
            self.downloaded = []

        async def list_objects(self, prefix, *, limit):
            self.list_calls.append((prefix, limit))
            return [SimpleNamespace(object_name=object_key, size=101)]

        async def download(self, key):
            self.downloaded.append(key)
            raise AssertionError("oversized persisted source must not be downloaded")

    storage = _Storage()
    monkeypatch.setattr(knowledge_router, "get_settings", lambda: settings)
    monkeypatch.setattr(knowledge_router, "KnowledgeRepository", lambda _session: _Repository())
    monkeypatch.setattr(
        knowledge_router,
        "RuntimeKnowledgeExtractor",
        lambda value: RuntimeKnowledgeExtractor(value, settings=settings),
    )

    candidates, unreadable_sources = await knowledge_router._retrieval_candidates(
        session=SimpleNamespace(),
        storage=storage,
        payload=KnowledgeSearchRequest(question="查詢手冊"),
    )

    assert candidates == []
    assert storage.list_calls == [("knowledge/", 1)]
    assert storage.downloaded == []
    assert "單一文件大小上限" in unreadable_sources[0].reason
