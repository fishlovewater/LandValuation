from typing import Annotated

from fastapi import Depends
from minio import Minio

from app.storage.client import get_minio_client
from app.storage.service import StorageService


def get_storage_service(client: Annotated[Minio, Depends(get_minio_client)]) -> StorageService:
    return StorageService(client)


Storage = Annotated[StorageService, Depends(get_storage_service)]
