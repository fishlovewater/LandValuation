from fastapi.testclient import TestClient

from app.main import app


GUIDE_PATHS = {
    "/api/v1/valuation/cases",
    "/api/v1/valuation/cases/bootstrap",
    "/api/v1/valuation/cases/{case_id}",
    "/api/v1/valuation/cases/{case_id}/archive",
    "/api/v1/valuation/cases/{case_id}/parcels",
    "/api/v1/valuation/cases/{case_id}/parcels/{parcel_id}",
    "/api/v1/valuation/form-types",
    "/api/v1/valuation/form-templates",
    "/api/v1/valuation/form-templates/formula-policy",
    "/api/v1/valuation/form-templates/{form_type}",
    "/api/v1/valuation/form-templates/{form_type}/coordinates",
    "/api/v1/valuation/form-templates/{form_type}/blank-pdf",
    "/api/v1/valuation/form-types/{form_type}/requirements",
    "/api/v1/valuation/cases/{case_id}/forms",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/submit",
    "/api/v1/valuation/cases/{case_id}/benchmark-lands",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/f03",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/f01",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/f01/calculate",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/f01/validate",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/f04",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/f04/calculate",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/f04/validate",
    "/api/v1/valuation/cases/{case_id}/forms/{form_id}/official-pdf",
    "/api/v1/valuation/cases/{case_id}/documents",
    "/api/v1/valuation/cases/{case_id}/documents/{document_id}/download",
    "/api/v1/valuation/cases/{case_id}/documents/{document_id}/extract",
    "/api/v1/valuation/cases/{case_id}/documents/{document_id}/extraction",
    "/api/v1/valuation/cases/{case_id}/documents/{document_id}/extraction/analyze-fields",
    "/api/v1/valuation/cases/{case_id}/documents/{document_id}/extraction/codex-package",
    "/api/v1/valuation/cases/{case_id}/documents/{document_id}/extraction/import-codex-candidates",
    "/api/v1/valuation/cases/{case_id}/documents/{document_id}/extraction/confirm",
    "/api/v1/ai-assistant/sessions",
    "/api/v1/ai-assistant/sessions/{session_id}",
    "/api/v1/ai-assistant/sessions/{session_id}/messages",
    "/api/v1/ai-assistant/sessions/{session_id}/progress",
    "/api/v1/valuation/cases/{case_id}/calculations",
    "/api/v1/valuation/cases/{case_id}/calculations/{calculation_id}",
    "/api/v1/valuation/cases/{case_id}/validations",
    "/api/v1/valuation/cases/{case_id}/validations/{validation_run_id}",
    "/api/v1/valuation/cases/{case_id}/reports",
    "/api/v1/valuation/cases/{case_id}/reports/{document_id}/download",
    "/api/v1/valuation/report-types",
    "/api/v1/valuation/report-types/{report_type}/requirements",
    "/api/v1/valuation/cases/{case_id}/report-packages",
    "/api/v1/valuation/cases/{case_id}/reports/{report_id}",
    "/api/v1/valuation/cases/{case_id}/report-progress",
    "/api/v1/valuation/cases/{case_id}/reports/{report_id}/pages/S01",
    "/api/v1/valuation/cases/{case_id}/reports/{report_id}/pages/F02-RF",
    "/api/v1/valuation/cases/{case_id}/reports/{report_id}/pages/F02",
    "/api/v1/valuation/cases/{case_id}/reports/{report_id}/draft-pages-1-3/download",
    "/api/v1/valuation/cases/{case_id}/reports/{report_id}/draft-readiness",
    "/api/v1/valuation/cases/{case_id}/reports/{report_id}/draft-pages-1-6/download",
    "/api/v1/valuation/cases/{case_id}/facilities/nearest",
}


def test_backend_guide_routes_are_in_openapi() -> None:
    assert GUIDE_PATHS.issubset(app.openapi()["paths"])


def test_form_types_requires_login() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/valuation/form-types")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
