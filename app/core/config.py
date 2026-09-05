from functools import lru_cache
import re
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Land Valuation API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_prefix: str = "/api/v1"
    docs_enabled: bool = True
    log_level: str = "INFO"

    database_url: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "land_valuation"
    postgres_user: str = "app_user"
    postgres_password: SecretStr = SecretStr("change_me")
    db_pool_size: int = 5
    db_max_overflow: int = 10

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str | None = None
    minio_secret_key: SecretStr | None = None
    minio_root_user: str | None = None
    minio_root_password: SecretStr | None = None
    minio_bucket: str = "land-valuation"
    minio_secure: bool = False
    minio_presigned_expiry_seconds: int = 900

    knowledge_answer_provider: str = "evidence_only"
    knowledge_ai_max_source_characters: int = Field(default=60000, ge=2000, le=200000)
    codex_cli_command: str = "codex"
    codex_cli_model: str | None = None
    codex_cli_timeout_seconds: int = Field(default=180, ge=10, le=900)
    bedrock_timeout_seconds: int = Field(default=60, ge=10, le=900)
    bedrock_max_tokens: int = Field(default=1200, ge=100, le=8000)
    bedrock_temperature: float = Field(default=0, ge=0, le=1)

    document_extraction_provider: Literal[
        "local_pdf", "local_ocr", "auto", "textract"
    ] = "auto"
    local_ocr_languages: str = "chi_tra+eng"
    local_ocr_dpi: int = Field(default=300, ge=150, le=400)
    local_ocr_psm: int = Field(default=1, ge=0, le=13)
    local_ocr_timeout_seconds: int = Field(default=120, ge=10, le=900)
    local_ocr_max_pages: int = Field(default=50, ge=1, le=500)
    textract_region: str | None = None
    textract_s3_bucket: str | None = None
    textract_s3_prefix: str = "land-valuation-textract"
    textract_timeout_seconds: int = Field(default=120, ge=10, le=900)
    textract_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=10)

    jwt_secret_key: SecretStr = Field(default=SecretStr("change-me-before-use"))
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    ai_provider: Literal["mock", "bedrock", "gemini"] = "mock"
    ai_prompt_version: str = "f03-v1"
    ai_field_analysis_prompt_version: str = "field-analysis-v1"
    ai_codex_import_prompt_version: str = "codex-field-analysis-v1"
    ai_rule_extraction_prompt_version: str = "rule-pack-extraction-v1"
    ai_field_analysis_max_chars: int = Field(default=40000, ge=1000, le=200000)
    ai_field_analysis_max_candidates: int = Field(default=30, ge=1, le=100)
    ai_timeout_seconds: int = Field(default=30, ge=1, le=120)
    ai_max_tool_rounds: int = Field(default=5, ge=1, le=10)
    bedrock_region: str | None = None
    bedrock_model_id: str | None = None
    aws_access_key_id: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    google_maps_api_key: SecretStr | None = None

    @field_validator("minio_bucket")
    @classmethod
    def validate_bucket(cls, value: str, info: ValidationInfo) -> str:
        if value == "land-valuation":
            return value
        if info.data.get("app_env", "development").lower() == "test":
            if re.fullmatch(r"land-valuation-test-[a-z0-9-]+", value):
                return value
            raise ValueError("invalid test MINIO_BUCKET")
        raise ValueError("MINIO_BUCKET must be land-valuation outside test")

    @field_validator("textract_s3_prefix")
    @classmethod
    def validate_textract_prefix(cls, value: str) -> str:
        normalized = value.strip().strip("/")
        if not normalized:
            raise ValueError("TEXTRACT_S3_PREFIX must not be empty")
        return normalized

    @field_validator("local_ocr_languages")
    @classmethod
    def validate_local_ocr_languages(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", normalized):
            raise ValueError("LOCAL_OCR_LANGUAGES has an invalid format")
        return normalized

    @model_validator(mode="after")
    def reject_development_secret_outside_development(self):
        if (
            self.app_env.lower() not in {"development", "test"}
            and self.jwt_secret_key.get_secret_value() == "change-this-competition-secret"
        ):
            raise ValueError("JWT_SECRET_KEY must be replaced outside development")
        return self

    @model_validator(mode="after")
    def validate_ai_provider(self):
        if self.ai_provider == "bedrock" and (
            not self.bedrock_region or not self.bedrock_model_id
        ):
            raise ValueError(
                "BEDROCK_REGION and BEDROCK_MODEL_ID are required for AI_PROVIDER=bedrock"
            )
        if self.ai_provider == "gemini" and self.gemini_api_key is None:
            raise ValueError(
                "GEMINI_API_KEY is required while AI_PROVIDER=gemini"
            )
        return self

    @model_validator(mode="after")
    def validate_document_extraction_provider(self):
        if self.document_extraction_provider == "textract" and (
            not self.textract_region or not self.textract_s3_bucket
        ):
            raise ValueError(
                "TEXTRACT_REGION and TEXTRACT_S3_BUCKET are required for "
                "DOCUMENT_EXTRACTION_PROVIDER=textract"
            )
        return self

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def resolved_minio_access_key(self) -> str:
        value = self.minio_access_key or self.minio_root_user
        if not value:
            raise ValueError("MINIO_ACCESS_KEY or MINIO_ROOT_USER is required")
        return value

    @property
    def resolved_minio_secret_key(self) -> str:
        value = self.minio_secret_key or self.minio_root_password
        if not value:
            raise ValueError("MINIO_SECRET_KEY or MINIO_ROOT_PASSWORD is required")
        return value.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
