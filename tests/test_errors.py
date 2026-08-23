from fastapi.testclient import TestClient

from app.main import app


def test_validation_error_uses_common_shape() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"username": "", "password": ""})
    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"]


def test_me_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
