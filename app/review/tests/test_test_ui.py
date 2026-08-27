from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


def test_test_ui_is_available_in_development(monkeypatch):
    monkeypatch.setattr(
        "app.review.router.get_settings",
        lambda: SimpleNamespace(app_env="development"),
        raising=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/review/test-ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Review API 手動測試主控台" in response.text
    assert 'id="login-form"' in response.text
    assert 'id="case-form"' in response.text
    assert 'id="run-actions"' in response.text
    assert 'id="decision-form"' in response.text
    assert 'id="report-actions"' in response.text
    assert 'id="request-log"' in response.text
    assert "sessionStorage" in response.text
    assert "/auth/login" in response.text
    assert "/completeness-check" in response.text
    assert "/risk-summary" in response.text
    assert "/report/pdf" in response.text


def test_test_ui_is_hidden_outside_development(monkeypatch):
    monkeypatch.setattr(
        "app.review.router.get_settings",
        lambda: SimpleNamespace(app_env="production"),
        raising=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/review/test-ui")

    assert response.status_code == 404
