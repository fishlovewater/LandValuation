from functools import lru_cache

from minio import Minio

from app.core.config import get_settings


@lru_cache
def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.resolved_minio_access_key,
        secret_key=settings.resolved_minio_secret_key,
        secure=settings.minio_secure,
    )
