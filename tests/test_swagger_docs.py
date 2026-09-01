from fastapi.testclient import TestClient

from app.core.swagger_docs import INTAKE_JSON_EDITOR_MARKER
from app.main import app


def test_swagger_docs_include_large_intake_json_editor() -> None:
    with TestClient(app) as client:
        response = client.get("/docs")

    assert response.status_code == 200
    assert f'id="{INTAKE_JSON_EDITOR_MARKER}-style"' in response.text
    assert f'id="{INTAKE_JSON_EDITOR_MARKER}-script"' in response.text
    assert 'input[placeholder="intake_manifest_json"]' in response.text
    assert 'editor.setAttribute("rows", "18")' in response.text
    assert "JSON.stringify(JSON.parse(input.value), null, 2)" in response.text
    assert "min-height: 22rem" in response.text


def test_custom_swagger_route_is_not_in_openapi() -> None:
    assert "/docs" not in app.openapi()["paths"]
