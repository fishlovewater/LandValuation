from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentCategory(StrEnum):
    ORIGINAL = "original"
    PARCEL_FACTOR_LIST = "parcel-factor-list"
    CADASTRAL_MAP = "cadastral-map"
    LAND_REGISTER = "land-register"
    PHOTOS = "photos"
    ATTACHMENTS = "attachments"
    MAP_SECTION_SKETCH = "map-section-sketch"
    MAP_ZONING = "map-zoning"
    MAP_LAND_VALUE_SECTION = "map-land-value-section"
    COMPLETE_VALUATION_REPORT = "complete-valuation-report"


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    document_group_id: UUID
    case_id: UUID
    document_type: str
    original_filename: str
    mime_type: str
    bucket_name: str
    object_key: str
    checksum_sha256: str
    file_size_bytes: int
    storage_etag: str | None
    version_no: int
    uploaded_by_user_id: UUID | None
    uploaded_at: datetime
    is_active: bool


class DocumentCategoryUpdate(BaseModel):
    category: DocumentCategory
