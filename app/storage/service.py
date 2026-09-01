import hashlib
import re
from datetime import timedelta
from typing import BinaryIO

from fastapi.concurrency import run_in_threadpool
from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings
from app.core.exceptions import StorageError

OBJECT_KEY_PATTERN = re.compile(r"^(cases|knowledge)/[^/].+")


def validate_object_key(object_key: str) -> str:
    if (
        not OBJECT_KEY_PATTERN.fullmatch(object_key)
        or object_key.startswith(("http://", "https://", "/"))
        or ".." in object_key.split("/")
    ):
        raise ValueError("object_key must start with cases/ or knowledge/ and cannot be a URL")
    return object_key


class StorageService:
    def __init__(self, client: Minio) -> None:
        self.client = client
        self.settings = get_settings()
        self.bucket = self.settings.minio_bucket

    async def bucket_ready(self) -> bool:
        try:
            return await run_in_threadpool(self.client.bucket_exists, self.bucket)
        except S3Error as exc:
            raise StorageError("無法確認 MinIO bucket") from exc

    async def upload(
        self,
        object_key: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> dict[str, str | int]:
        key = validate_object_key(object_key)
        checksum = hashlib.sha256()

        class HashingReader:
            def read(self, size=-1):
                chunk = data.read(size)
                if chunk:
                    checksum.update(chunk)
                return chunk

        try:
            result = await run_in_threadpool(
                self.client.put_object,
                self.bucket,
                key,
                HashingReader(),
                length,
                content_type=content_type,
            )
            return {
                "bucket_name": self.bucket,
                "object_key": key,
                "checksum_sha256": checksum.hexdigest(),
                "file_size_bytes": length,
                "etag": result.etag,
            }
        except (S3Error, OSError) as exc:
            raise StorageError("MinIO 上傳失敗") from exc

    async def download(self, object_key: str):
        key = validate_object_key(object_key)
        try:
            return await run_in_threadpool(self.client.get_object, self.bucket, key)
        except S3Error as exc:
            raise StorageError("MinIO 下載失敗") from exc

    async def delete(self, object_key: str) -> None:
        key = validate_object_key(object_key)
        try:
            await run_in_threadpool(self.client.remove_object, self.bucket, key)
        except S3Error as exc:
            raise StorageError("MinIO 刪除失敗") from exc

    async def object_exists(self, object_key: str) -> bool:
        key = validate_object_key(object_key)
        try:
            await run_in_threadpool(self.client.stat_object, self.bucket, key)
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
                return False
            raise StorageError("無法確認 MinIO 物件") from exc

    async def presigned_download_url(self, object_key: str) -> str:
        key = validate_object_key(object_key)
        try:
            return await run_in_threadpool(
                self.client.presigned_get_object,
                self.bucket,
                key,
                expires=timedelta(seconds=self.settings.minio_presigned_expiry_seconds),
            )
        except S3Error as exc:
            raise StorageError("無法建立短效下載網址") from exc
