from app.main import create_app


def test_valuation_and_review_routes_coexist():
    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/valuation/cases" in paths
    assert "/api/v1/valuation/cases/{case_id}/submit-for-review" in paths
    assert "/api/v1/review/workbench/cases" in paths
    assert "/api/v1/ai-assistant/sessions" in paths
    assert "/api/v1/valuation/cases/{case_id}/calculations" in paths
    assert "/api/v1/history/cases" in paths
    assert "/api/v1/knowledge/search" in paths
    assert "/api/v1/knowledge/ask" in paths
    assert "/api/v1/knowledge/provider-status" in paths
    assert "/api/v1/knowledge/cases/{case_id}/context" in paths
