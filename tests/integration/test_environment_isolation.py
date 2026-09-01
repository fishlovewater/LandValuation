import os


def test_integration_environment_is_run_scoped():
    run_id = os.environ["TEST_RUN_ID"]
    assert run_id.startswith("vr-")
    assert os.environ["POSTGRES_DB"] == f"land_valuation_test_{run_id.replace('-', '_')}"
    assert os.environ["MINIO_BUCKET"] == f"land-valuation-test-{run_id}"
    assert os.environ.get("APP_ENV") == "test"
