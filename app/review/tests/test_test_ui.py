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
    assert "審查人員工作台" in response.text
    assert 'id="login-view"' in response.text
    assert 'id="workbench-shell"' in response.text
    assert 'id="case-list"' in response.text
    assert 'id="case-detail"' in response.text
    assert 'id="eligible-case-dialog"' in response.text
    assert 'id="finding-list"' in response.text
    assert 'id="version-diff"' in response.text
    assert 'id="report-panel"' in response.text
    assert 'id="decision-timeline"' in response.text
    assert 'id="developer-drawer"' in response.text
    assert '<details id="developer-drawer"' in response.text
    assert 'id="login-form"' in response.text
    assert 'id="request-log"' in response.text
    assert "sessionStorage" in response.text
    assert "redactForLog" in response.text
    assert "[REDACTED]" in response.text
    assert "/auth/login" in response.text
    assert "/review/workbench/summary" in response.text
    assert "/review/workbench/cases" in response.text
    assert "/review/workbench/eligible-cases" in response.text
    assert "/start" in response.text
    assert 'started.outcome === "BLOCKED"' in response.text
    assert "/review/demo/revise" in response.text
    assert "/report/pdf" in response.text
    assert "API Base" not in response.text
    assert ">Case ID<" not in response.text
    assert ">Review ID" not in response.text
    assert "prefers-reduced-motion" in response.text
    assert ":focus-visible" in response.text
    assert "原始文字" in response.text
    assert "法規依據" in response.text
    assert "data-finding-after-value" in response.text
    assert 'id="case-prev"' in response.text
    assert 'id="case-next"' in response.text
    assert "status_group=" in response.text


def test_test_ui_is_hidden_outside_development(monkeypatch):
    monkeypatch.setattr(
        "app.review.router.get_settings",
        lambda: SimpleNamespace(app_env="production"),
        raising=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/review/test-ui")

    assert response.status_code == 404
