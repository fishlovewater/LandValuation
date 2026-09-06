from types import SimpleNamespace

import pytest

from app.storage.service import StorageService, validate_object_key


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
