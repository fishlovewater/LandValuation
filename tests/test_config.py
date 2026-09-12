import pytest
from pydantic import ValidationError

from app.core.config import F03_PRODUCTION_RULE_SET_CODE, Settings


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


@pytest.mark.parametrize(
    "unsafe_secret",
    ["change-me-before-use", "change-this-competition-secret"],
)
def test_non_development_rejects_known_insecure_jwt_defaults(unsafe_secret):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            app_env="production",
            minio_bucket="land-valuation",
            f03_validation_rule_set_code=F03_PRODUCTION_RULE_SET_CODE,
            jwt_secret_key=unsafe_secret,
            smtp_host="smtp.example.test",
            smtp_from_email="no-reply@example.test",
        )


def test_test_environment_accepts_approved_demo_f03_rule_set(monkeypatch):
    monkeypatch.setenv("F03_VALIDATION_RULE_SET_CODE", "DEMO-F03-FORMAL-VALIDATION")
    settings = Settings(app_env="test", _env_file=None)

    assert settings.resolved_f03_validation_rule_set_code == "DEMO-F03-FORMAL-VALIDATION"


def test_gemini_provider_requires_dedicated_api_key():
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(ai_provider="gemini")


def test_ollama_provider_uses_local_defaults_without_api_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT_SECONDS", raising=False)
    settings = Settings(app_env="test", _env_file=None, ai_provider="ollama")

    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "qwen3.5:latest"
    assert settings.ollama_timeout_seconds == 120


def test_ollama_base_url_trailing_slash_is_normalized():
    settings = Settings(
        app_env="test",
        _env_file=None,
        ai_provider="ollama",
        ollama_base_url="http://localhost:11434/",
    )

    assert settings.ollama_base_url == "http://localhost:11434"


def test_knowledge_answer_provider_defaults_to_evidence_only(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_ANSWER_PROVIDER", raising=False)
    settings = Settings(app_env="test", _env_file=None)

    assert settings.knowledge_answer_provider == "evidence_only"


def test_knowledge_runtime_limits_have_bounded_defaults(monkeypatch):
    for name in (
        "DEMO_QUICK_LOGIN_ENABLED",
        "DOCUMENT_PREVIEW_MAX_BYTES",
        "KNOWLEDGE_RUNTIME_MAX_OBJECTS",
        "KNOWLEDGE_RUNTIME_MAX_OBJECT_BYTES",
        "KNOWLEDGE_RUNTIME_MAX_TOTAL_BYTES",
        "KNOWLEDGE_RUNTIME_MAX_TOTAL_CHARACTERS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(app_env="test", _env_file=None)

    assert settings.demo_quick_login_enabled is False
    assert settings.document_preview_max_bytes == 10 * 1024 * 1024
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


@pytest.mark.parametrize(
    "value",
    [1024 * 1024 - 1, 50 * 1024 * 1024 + 1],
)
def test_document_preview_limit_rejects_out_of_bounds(value):
    with pytest.raises(ValidationError):
        Settings(
            app_env="test",
            _env_file=None,
            document_preview_max_bytes=value,
        )


def test_official_report_blank_template_keys_must_be_configured_as_a_pair():
    with pytest.raises(ValidationError, match="OFFICIAL_REPORT_BLANK_TEMPLATE"):
        Settings(
            app_env="test",
            _env_file=None,
            official_report_blank_template_object_key="templates/official/report.pdf",
        )


def test_official_report_blank_template_keys_are_optional_and_normalized():
    disabled = Settings(app_env="test", _env_file=None)
    assert disabled.official_report_blank_template_object_key is None
    assert disabled.official_report_blank_template_manifest_object_key is None

    enabled = Settings(
        app_env="test",
        _env_file=None,
        official_report_blank_template_object_key="  templates/official/report.pdf  ",
        official_report_blank_template_manifest_object_key=(
            "  templates/official/report.manifest.json  "
        ),
    )
    assert (
        enabled.official_report_blank_template_object_key
        == "templates/official/report.pdf"
    )
    assert (
        enabled.official_report_blank_template_manifest_object_key
        == "templates/official/report.manifest.json"
    )
