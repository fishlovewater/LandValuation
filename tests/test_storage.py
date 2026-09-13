import io
from types import SimpleNamespace

import pytest

from app.storage.service import S3StorageService, StorageService, validate_object_key


@pytest.mark.parametrize(
    "key",
    [
        "cases/00000000-0000-0000-0000-000000000000/original/file.pdf",
        "knowledge/manuals/00000000-0000-0000-0000-000000000000/v1/file.pdf",
    ],
)
def test_valid_object_keys(key: str) -> None:
    assert validate_object_key(key) == key


@pytest.mark.parametrize(
    "key",
    ["http://localhost/file.pdf", "/cases/file.pdf", "cases/../file.pdf", "other/file.pdf"],
)
def test_invalid_object_keys(key: str) -> None:
    with pytest.raises(ValueError):
        validate_object_key(key)


@pytest.mark.asyncio
async def test_object_listing_is_restricted_to_knowledge_prefix() -> None:
    service = object.__new__(StorageService)
    with pytest.raises(ValueError, match="knowledge/"):
        await service.list_objects("cases/")


class _ListingClient:
    def __init__(self, objects):
        self.objects = objects
        self.yielded = 0

    def list_objects(self, *_args, **_kwargs):
        for object_info in self.objects:
            self.yielded += 1
            yield object_info


@pytest.mark.asyncio
async def test_object_listing_stops_after_limit_plus_one_objects() -> None:
    client = _ListingClient(
        [SimpleNamespace(object_name=f"knowledge/{index}.txt") for index in range(5)]
    )
    service = object.__new__(StorageService)
    service.client = client
    service.bucket = "land-valuation"

    objects = await service.list_objects("knowledge/", limit=2)

    assert [item.object_name for item in objects] == [
        "knowledge/0.txt",
        "knowledge/1.txt",
        "knowledge/2.txt",
    ]
    assert client.yielded == 3


class _S3Body:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.offset = 0
        self.closed = False

    def read(self, amount=None) -> bytes:
        if amount is None:
            amount = len(self.content) - self.offset
        chunk = self.content[self.offset : self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class _S3Paginator:
    def paginate(self, **_kwargs):
        return [
            {
                "Contents": [
                    {"Key": "knowledge/first.txt", "Size": 3, "ETag": '"a"'},
                    {"Key": "knowledge/second.txt", "Size": 4, "ETag": '"b"'},
                ]
            }
        ]


class _S3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.bucket_checked = False

    def head_bucket(self, **_kwargs) -> None:
        self.bucket_checked = True

    def put_object(self, **kwargs) -> dict[str, str]:
        self.objects[kwargs["Key"]] = kwargs["Body"].read()
        return {"ETag": '"s3-etag"'}

    def get_object(self, **kwargs) -> dict[str, _S3Body]:
        return {"Body": _S3Body(self.objects[kwargs["Key"]])}

    def get_paginator(self, name: str) -> _S3Paginator:
        assert name == "list_objects_v2"
        return _S3Paginator()

    def head_object(self, **kwargs) -> None:
        if kwargs["Key"] not in self.objects:
            raise AssertionError("test only checks an uploaded object")

    def delete_object(self, **kwargs) -> None:
        self.objects.pop(kwargs["Key"], None)

    def generate_presigned_url(self, operation: str, **kwargs) -> str:
        assert operation == "get_object"
        assert kwargs["Params"]["Key"].startswith("knowledge/")
        return "https://example.invalid/download"


@pytest.mark.asyncio
async def test_aws_s3_storage_uses_the_existing_storage_contract() -> None:
    client = _S3Client()
    service = S3StorageService(client)
    object_key = "knowledge/system-tests/s3-storage.txt"
    payload = b"aws s3 storage"

    assert await service.bucket_ready() is True
    assert client.bucket_checked is True

    uploaded = await service.upload(object_key, io.BytesIO(payload), len(payload))
    assert uploaded["bucket_name"] == service.bucket
    assert uploaded["etag"] == "s3-etag"

    response = await service.download(object_key)
    assert response.read() == payload
    response.close()
    response.release_conn()

    listed = await service.list_objects("knowledge/", limit=1)
    assert [item.object_name for item in listed] == [
        "knowledge/first.txt",
        "knowledge/second.txt",
    ]
    assert await service.object_exists(object_key) is True
    assert await service.presigned_download_url(object_key) == "https://example.invalid/download"

    await service.delete(object_key)
    assert object_key not in client.objects
