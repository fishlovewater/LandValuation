import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_test_environment_allows_run_scoped_minio_bucket():
    settings = Settings(
        app_env="test",
        minio_bucket="land-valuation-test-vr-abc123-def456",
    )

    assert settings.minio_bucket == "land-valuation-test-vr-abc123-def456"


@pytest.mark.parametrize(
    "bucket",
    [
        "land-valuation-test-",
        "land-valuation-test-UPPER",
        "land-valuation-test-a/b",
        "land-valuation-test-a.b",
        "https://land-valuation-test-a",
    ],
)
def test_test_environment_rejects_invalid_run_scoped_minio_bucket(bucket):
    with pytest.raises(ValidationError, match="invalid test MINIO_BUCKET"):
        Settings(app_env="test", minio_bucket=bucket)


def test_non_test_environment_rejects_run_scoped_minio_bucket():
    with pytest.raises(ValidationError):
        Settings(
            app_env="development",
            minio_bucket="land-valuation-test-vr-abc123-def456",
        )


def test_gemini_provider_requires_dedicated_api_key():
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(ai_provider="gemini")
