from functools import lru_cache

import re

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

    jwt_secret_key: SecretStr = Field(default=SecretStr("change-me-before-use"))
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    @field_validator("minio_bucket")
    @classmethod
    def validate_bucket(cls, value: str, info: ValidationInfo) -> str:
        if value == "land-valuation":
            return value
        if (
            info.data.get("app_env", "development").lower() == "test"
            and re.fullmatch(r"land-valuation-test-[a-z0-9-]+", value)
        ):
            return value
        raise ValueError("MINIO_BUCKET must be land-valuation outside test")

    @model_validator(mode="after")
    def reject_development_secret_outside_development(self):
        if (
            self.app_env.lower() not in {"development", "test"}
            and self.jwt_secret_key.get_secret_value() == "change-this-competition-secret"
        ):
            raise ValueError("JWT_SECRET_KEY must be replaced outside development")
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
