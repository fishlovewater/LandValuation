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
