from functools import lru_cache
import re
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


F03_PRODUCTION_RULE_SET_CODE = "F03_MVP_VALIDATION"
F03_DEMO_RULE_SET_CODES = frozenset({"DEMO-F03-FORMAL-VALIDATION"})
UNSAFE_JWT_SECRET_VALUES = frozenset(
    {
        "change-me-before-use",
        "change-this-competition-secret",
    }
)


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
    demo_quick_login_enabled: bool = False
    demo_review_allow_missing_materials: bool = False
    review_auto_fill_confidence: float = Field(default=0.95, ge=0.9, le=1.0)
    password_reset_token_minutes: int = Field(default=30, ge=5, le=1440)
    password_reset_debug_token_enabled: bool = False
    public_app_url: str = "http://127.0.0.1:5173"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    smtp_starttls: bool = True
    document_preview_max_bytes: int = Field(
        default=10 * 1024 * 1024, ge=1024 * 1024, le=50 * 1024 * 1024
    )
    f03_validation_rule_set_code: str = F03_PRODUCTION_RULE_SET_CODE

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
    object_storage_provider: Literal["minio", "aws_s3"] = "minio"
    aws_s3_bucket: str | None = None
    aws_s3_region: str | None = None
    aws_profile: str | None = None
    official_report_blank_template_object_key: str | None = None
    official_report_blank_template_manifest_object_key: str | None = None

    knowledge_answer_provider: str = "evidence_only"
    knowledge_ai_max_source_characters: int = Field(default=60000, ge=2000, le=200000)
    knowledge_runtime_max_objects: int = Field(default=100, ge=1, le=1000)
    knowledge_runtime_max_object_bytes: int = Field(
        default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024
    )
    knowledge_runtime_max_total_bytes: int = Field(
        default=50 * 1024 * 1024, ge=1024, le=500 * 1024 * 1024
    )
    knowledge_runtime_max_total_characters: int = Field(
        default=200000, ge=1000, le=2000000
    )
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

    aws_location_region: str | None = None
    aws_location_place_index_name: str | None = None
    aws_location_language: str = "zh-TW"
    map_provider: Literal["mapbox"] = "mapbox"
    mapbox_access_token: SecretStr | None = None
    mapbox_username: str | None = None
    mapbox_style_id: str | None = None
    mapbox_static_zoom: int = Field(default=16, ge=1, le=22)
    mapbox_image_width: int = Field(default=1280, ge=256, le=1280)
    mapbox_image_height: int = Field(default=800, ge=256, le=1280)
    mapbox_timeout_seconds: int = Field(default=20, ge=5, le=120)

    jwt_secret_key: SecretStr = Field(default=SecretStr("change-me-before-use"))
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    ai_provider: Literal["mock", "ollama", "bedrock", "gemini"] = "mock"
    ai_prompt_version: str = "f03-v1"
    ai_field_analysis_prompt_version: str = "field-analysis-v1"
    ai_codex_import_prompt_version: str = "codex-field-analysis-v1"
    ai_rule_extraction_prompt_version: str = "rule-pack-extraction-v1"
    ai_field_analysis_max_chars: int = Field(default=40000, ge=1000, le=200000)
    ai_field_analysis_max_candidates: int = Field(default=30, ge=1, le=100)
    ai_timeout_seconds: int = Field(default=30, ge=1, le=120)
    ai_max_tool_rounds: int = Field(default=5, ge=1, le=10)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:latest"
    ollama_timeout_seconds: int = Field(default=120, ge=1, le=900)
    bedrock_region: str | None = None
    bedrock_model_id: str | None = None
    bedrock_fallback_model_id: str | None = None
    bedrock_fallback_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    aws_access_key_id: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

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
            and self.jwt_secret_key.get_secret_value().strip() in UNSAFE_JWT_SECRET_VALUES
        ):
            raise ValueError("JWT_SECRET_KEY must be replaced outside development")
        return self

    @model_validator(mode="after")
    def validate_password_reset_delivery(self):
        self.public_app_url = self.public_app_url.rstrip("/")
        if not self.public_app_url:
            raise ValueError("PUBLIC_APP_URL must not be empty")
        if self.app_env.lower() not in {"development", "test"}:
            if not self.smtp_host or not self.smtp_from_email:
                raise ValueError(
                    "SMTP_HOST and SMTP_FROM_EMAIL are required outside development/test"
                )
        return self

    @model_validator(mode="after")
    def validate_official_report_template_pair(self):
        template_key = (self.official_report_blank_template_object_key or "").strip()
        manifest_key = (
            self.official_report_blank_template_manifest_object_key or ""
        ).strip()
        if bool(template_key) != bool(manifest_key):
            raise ValueError(
                "OFFICIAL_REPORT_BLANK_TEMPLATE_OBJECT_KEY and "
                "OFFICIAL_REPORT_BLANK_TEMPLATE_MANIFEST_OBJECT_KEY must be set together"
            )
        self.official_report_blank_template_object_key = template_key or None
        self.official_report_blank_template_manifest_object_key = manifest_key or None
        return self

    @model_validator(mode="after")
    def validate_f03_rule_set_code(self):
        code = self.f03_validation_rule_set_code.strip()
        environment = self.app_env.lower()
        if environment not in {"development", "test"} and code != F03_PRODUCTION_RULE_SET_CODE:
            raise ValueError(
                "F03_VALIDATION_RULE_SET_CODE must be F03_MVP_VALIDATION outside development"
            )
        if environment in {"development", "test"} and code not in {
            F03_PRODUCTION_RULE_SET_CODE,
            *F03_DEMO_RULE_SET_CODES,
        }:
            raise ValueError(
                "F03_VALIDATION_RULE_SET_CODE is not an approved production or Demo code"
            )
        self.f03_validation_rule_set_code = code
        return self

    @model_validator(mode="after")
    def validate_ai_provider(self):
        self.ollama_base_url = self.ollama_base_url.rstrip("/")
        if not self.ollama_base_url:
            raise ValueError("OLLAMA_BASE_URL must not be empty")
        if not self.ollama_model.strip():
            raise ValueError("OLLAMA_MODEL must not be empty")
        if self.ai_provider == "bedrock" and (
            not self.bedrock_region or not self.bedrock_model_id
        ):
            raise ValueError(
                "BEDROCK_REGION and BEDROCK_MODEL_ID are required for AI_PROVIDER=bedrock"
            )
        if self.ai_provider == "gemini" and (
            self.gemini_api_key is None
            or not self.gemini_api_key.get_secret_value().strip()
        ):
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
    def resolved_f03_validation_rule_set_code(self) -> str:
        if self.app_env.lower() not in {"development", "test"}:
            return F03_PRODUCTION_RULE_SET_CODE
        return self.f03_validation_rule_set_code

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

    @property
    def resolved_aws_s3_bucket(self) -> str:
        """Use the configured application bucket, or the existing Textract bucket.

        The fallback keeps the local AWS Demo configuration small while still
        requiring an explicit bucket whenever AWS object storage is selected.
        """

        value = (self.aws_s3_bucket or self.textract_s3_bucket or "").strip()
        if not value:
            raise ValueError(
                "AWS_S3_BUCKET or TEXTRACT_S3_BUCKET is required for AWS S3 storage"
            )
        return value

    @property
    def resolved_aws_s3_region(self) -> str | None:
        return self.aws_s3_region or self.textract_region or self.bedrock_region


@lru_cache
def get_settings() -> Settings:
    return Settings()
