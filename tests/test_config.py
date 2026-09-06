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


def test_knowledge_answer_provider_defaults_to_evidence_only(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_ANSWER_PROVIDER", raising=False)
    settings = Settings(app_env="test", _env_file=None)

    assert settings.knowledge_answer_provider == "evidence_only"


def test_knowledge_runtime_limits_have_bounded_defaults():
    settings = Settings(app_env="test", _env_file=None)

    assert settings.knowledge_runtime_max_objects == 100
    assert settings.knowledge_runtime_max_object_bytes == 10 * 1024 * 1024
    assert settings.knowledge_runtime_max_total_bytes == 50 * 1024 * 1024
    assert settings.knowledge_runtime_max_total_characters == 200000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("knowledge_runtime_max_objects", 0),
        ("knowledge_runtime_max_objects", 1001),
        ("knowledge_runtime_max_object_bytes", 1023),
        ("knowledge_runtime_max_object_bytes", 100 * 1024 * 1024 + 1),
        ("knowledge_runtime_max_total_bytes", 1023),
        ("knowledge_runtime_max_total_bytes", 500 * 1024 * 1024 + 1),
        ("knowledge_runtime_max_total_characters", 999),
        ("knowledge_runtime_max_total_characters", 2000001),
    ],
)
def test_knowledge_runtime_limits_reject_out_of_bounds(field, value):
    with pytest.raises(ValidationError):
        Settings(app_env="test", _env_file=None, **{field: value})
