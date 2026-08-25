from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


def test_review_router_is_registered():
    paths = set(app.openapi()["paths"])

    assert "/api/v1/review/cases" in paths


def test_review_cases_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/api/v1/review/cases")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_review_cases_rejects_user_without_execute_permission():
    permission = SimpleNamespace(permission_code="case.read")
    role = SimpleNamespace(role_code="APPRAISER", is_active=True, permissions=[permission])
    user = SimpleNamespace(roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/review/cases")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
