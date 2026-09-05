from __future__ import annotations

import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


TEST_UI_URL = "/api/v1/valuation/test-ui"
REQUIRED_MARKERS = (
    '<title>估價製作測試台</title>',
    "<h1>估價製作測試台</h1>",
    'id="login-view"',
    'id="workbench-shell"',
    'id="case-list"',
    'id="intake-step"',
    'id="candidate-step"',
    'id="formal-step"',
    'id="correction-panel"',
    'id="developer-drawer"',
    'id="request-log"',
    'id="status-message"',
    'id="copy-demo-command"',
    "python -m app.valuation.demo seed",
)


def test_valuation_test_ui_is_available_in_development(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.valuation.router.get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )

    with TestClient(app) as client:
        response = client.get(TEST_UI_URL)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.encoding == "utf-8"
    for marker in REQUIRED_MARKERS:
        assert marker in response.text


def test_valuation_test_ui_is_404_outside_development(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.valuation.router.get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )

    with TestClient(app) as client:
        response = client.get(TEST_UI_URL)

    assert response.status_code == 404


def test_valuation_test_ui_is_not_exposed_in_openapi() -> None:
    assert TEST_UI_URL not in app.openapi()["paths"]


def test_valuation_test_ui_has_accessible_static_shell(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.valuation.router.get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )

    with TestClient(app) as client:
        html = client.get(TEST_UI_URL).text

    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert ":focus-visible" in html
    assert "prefers-reduced-motion" in html
    assert 'aria-live="polite"' in html
    assert re.search(r'<details\s+id="developer-drawer"[^>]*>', html)
    assert not re.search(r'<details\s+id="developer-drawer"[^>]*\bopen(?:\s|=|>)', html)
    assert '<form id="login-form"' in html
    assert 'for="login-username"' in html
    assert 'for="login-password"' in html
    assert 'for="case-selector"' in html
    assert 'for="parcel-selector"' in html
    assert 'for="benchmark-selector"' in html
    assert 'for="document-selector"' in html
    assert 'for="candidate-decision"' in html
    assert 'for="form-selector"' in html


def test_valuation_test_ui_does_not_expose_secrets_or_external_assets(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.valuation.router.get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )

    with TestClient(app) as client:
        html = client.get(TEST_UI_URL).text

    assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=', html, re.IGNORECASE)
    assert "@import" not in html
    assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", html, re.IGNORECASE)
    for forbidden in (
        "bucket_name",
        "object_key",
        "API Base",
        "JSON 編輯",
        "JSON editor",
        "presigned",
        "minio",
        "Submission snapshot",
        "Review internal note",
    ):
        assert forbidden not in html
    assert not re.search(
        r'<input\b[^>]*id="login-password"[^>]*\bvalue\s*=',
        html,
        re.IGNORECASE,
    )
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
