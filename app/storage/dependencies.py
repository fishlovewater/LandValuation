from typing import Annotated, TypeAlias

from fastapi import Depends

from app.core.config import get_settings
from app.storage.client import get_aws_s3_client, get_minio_client
from app.storage.service import S3StorageService, StorageService


StorageBackend: TypeAlias = StorageService | S3StorageService


def get_storage_service() -> StorageBackend:
    settings = get_settings()
    if settings.object_storage_provider == "aws_s3":
        return S3StorageService(get_aws_s3_client())
    return StorageService(get_minio_client())


Storage = Annotated[StorageBackend, Depends(get_storage_service)]
