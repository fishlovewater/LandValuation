from app.history.test_app import app


def test_integration_app_mounts_all_three_subsystems():
    paths = set(app.openapi()["paths"])
    assert "/api/v1/valuation/cases" in paths
    assert "/api/v1/valuation/cases/{case_id}/submit-for-review" in paths
    assert "/api/v1/review/cases" in paths
    assert "/api/v1/history/cases" in paths
