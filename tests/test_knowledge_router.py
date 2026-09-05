from fastapi.testclient import TestClient

from app.main import app


def test_knowledge_routes_are_registered() -> None:
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/knowledge/search" in paths
    assert "/api/v1/knowledge/ask" in paths
    assert "/api/v1/knowledge/provider-status" in paths
    assert "/api/v1/knowledge/sources/{document_id}/download" in paths
    assert "/api/v1/knowledge/cases/{case_id}/context" in paths


def test_knowledge_route_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/knowledge/ask",
            json={"question": "道路條件怎麼判斷？"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
