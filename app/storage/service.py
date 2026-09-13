import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from itertools import islice
from typing import Any, BinaryIO, Iterator

from botocore.exceptions import BotoCoreError, ClientError
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
            raise StorageError("文件服務目前無法使用，請稍後再試。") from exc

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
            raise StorageError("文件上傳失敗，請稍後再試。") from exc

    async def download(self, object_key: str):
        key = validate_object_key(object_key)
        try:
            return await run_in_threadpool(self.client.get_object, self.bucket, key)
        except S3Error as exc:
            raise StorageError("文件下載失敗，請稍後再試。") from exc

    async def list_objects(self, prefix: str, *, limit: int | None = None) -> list:
        if prefix != "knowledge/":
            raise ValueError("only the knowledge/ prefix may be listed")
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")

        def collect_objects() -> list:
            objects = self.client.list_objects(
                self.bucket, prefix=prefix, recursive=True
            )
            if limit is None:
                return list(objects)
            return list(islice(objects, limit + 1))

        try:
            return await run_in_threadpool(collect_objects)
        except S3Error as exc:
            raise StorageError("目前無法讀取知識文件，請稍後再試。") from exc

    async def delete(self, object_key: str) -> None:
        key = validate_object_key(object_key)
        try:
            await run_in_threadpool(self.client.remove_object, self.bucket, key)
        except S3Error as exc:
            raise StorageError("文件刪除失敗，請稍後再試。") from exc

    async def object_exists(self, object_key: str) -> bool:
        key = validate_object_key(object_key)
        try:
            await run_in_threadpool(self.client.stat_object, self.bucket, key)
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
                return False
            raise StorageError("目前無法確認文件狀態，請稍後再試。") from exc

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
            raise StorageError("目前無法建立文件下載連結，請稍後再試。") from exc


@dataclass(slots=True)
class S3ObjectInfo:
    """The small MinIO-compatible metadata surface used by knowledge search."""

    object_name: str
    size: int | None = None
    etag: str | None = None
    last_modified: Any | None = None
    content_type: str | None = None


class S3DownloadResponse:
    """Expose the response methods used by existing MinIO callers."""

    def __init__(self, body) -> None:
        self._body = body

    def read(self, amt: int | None = None) -> bytes:
        return self._body.read(amt)

    def stream(self, amt: int = 64 * 1024) -> Iterator[bytes]:
        while chunk := self._body.read(amt):
            yield chunk

    def close(self) -> None:
        self._body.close()

    def release_conn(self) -> None:
        # botocore's StreamingBody is released by close().
        return None


class S3StorageService:
    """AWS S3 implementation of the application's existing storage contract."""

    def __init__(self, client) -> None:
        self.client = client
        self.settings = get_settings()
        self.bucket = self.settings.resolved_aws_s3_bucket

    @staticmethod
    def _error(exc: Exception, message: str) -> StorageError:
        return StorageError(message)

    @staticmethod
    def _checksum(data: BinaryIO) -> str:
        checksum = hashlib.sha256()
        try:
            position = data.tell()
            data.seek(0)
            while chunk := data.read(1024 * 1024):
                checksum.update(chunk)
            data.seek(position)
        except (AttributeError, OSError):
            # All application upload sources are seekable.  Keep a clear error
            # rather than silently uploading a stream with an invalid checksum.
            raise StorageError("上傳檔案必須為可重複讀取的串流。")
        return checksum.hexdigest()

    async def bucket_ready(self) -> bool:
        try:
            await run_in_threadpool(self.client.head_bucket, Bucket=self.bucket)
            return True
        except (ClientError, BotoCoreError, OSError) as exc:
            raise self._error(exc, "文件服務目前無法使用，請稍後再試。") from exc

    async def upload(
        self,
        object_key: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> dict[str, str | int]:
        key = validate_object_key(object_key)
        checksum = self._checksum(data)
        try:
            result = await run_in_threadpool(
                self.client.put_object,
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentLength=length,
                ContentType=content_type,
            )
            return {
                "bucket_name": self.bucket,
                "object_key": key,
                "checksum_sha256": checksum,
                "file_size_bytes": length,
                "etag": str(result.get("ETag", "")).strip('"'),
            }
        except (ClientError, BotoCoreError, OSError) as exc:
            raise self._error(exc, "文件上傳失敗，請稍後再試。") from exc

    async def download(self, object_key: str) -> S3DownloadResponse:
        key = validate_object_key(object_key)
        try:
            result = await run_in_threadpool(
                self.client.get_object, Bucket=self.bucket, Key=key
            )
            return S3DownloadResponse(result["Body"])
        except (ClientError, BotoCoreError, OSError) as exc:
            raise self._error(exc, "文件下載失敗，請稍後再試。") from exc

    async def list_objects(self, prefix: str, *, limit: int | None = None) -> list[S3ObjectInfo]:
        if prefix != "knowledge/":
            raise ValueError("only the knowledge/ prefix may be listed")
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")

        def collect_objects() -> list[S3ObjectInfo]:
            objects: list[S3ObjectInfo] = []
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    objects.append(
                        S3ObjectInfo(
                            object_name=item["Key"],
                            size=item.get("Size"),
                            etag=str(item.get("ETag", "")).strip('"') or None,
                            last_modified=item.get("LastModified"),
                        )
                    )
                    if limit is not None and len(objects) > limit:
                        return objects
            return objects

        try:
            return await run_in_threadpool(collect_objects)
        except (ClientError, BotoCoreError, OSError) as exc:
            raise self._error(exc, "目前無法讀取知識文件，請稍後再試。") from exc

    async def delete(self, object_key: str) -> None:
        key = validate_object_key(object_key)
        try:
            await run_in_threadpool(
                self.client.delete_object, Bucket=self.bucket, Key=key
            )
        except (ClientError, BotoCoreError, OSError) as exc:
            raise self._error(exc, "文件刪除失敗，請稍後再試。") from exc

    async def object_exists(self, object_key: str) -> bool:
        key = validate_object_key(object_key)
        try:
            await run_in_threadpool(
                self.client.head_object, Bucket=self.bucket, Key=key
            )
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NoSuchObject", "NotFound"}:
                return False
            raise self._error(exc, "目前無法確認文件狀態，請稍後再試。") from exc
        except (BotoCoreError, OSError) as exc:
            raise self._error(exc, "目前無法確認文件狀態，請稍後再試。") from exc

    async def presigned_download_url(self, object_key: str) -> str:
        key = validate_object_key(object_key)
        try:
            return await run_in_threadpool(
                self.client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=self.settings.minio_presigned_expiry_seconds,
            )
        except (ClientError, BotoCoreError, OSError) as exc:
            raise self._error(exc, "目前無法建立文件下載連結，請稍後再試。") from exc
