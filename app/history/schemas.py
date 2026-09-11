from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HistoryResult = Literal[
    "PASSED", "CORRECTION", "RETURNED", "SUPPLEMENT_REQUIRED", "IN_PROGRESS"
]
HistorySort = Literal["updated_at", "received_at", "risk_level"]
SortOrder = Literal["asc", "desc"]
DateField = Literal["updated_at", "received_at", "completed_at"]


class HistoryPermissions(BaseModel):
    can_view_valuation: bool
    can_view_review: bool


class HistoryCaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: UUID
    case_no: str
    case_title: str
    case_type: str
    valuation_base_date: date
    city_code: str
    district_code: str
    case_status: str
    updated_at: datetime
    review_status: str | None = None
    received_at: datetime | None = None
    completed_at: datetime | None = None
    current_risk_level: str | None = None
    history_result: HistoryResult
    visible_modules: list[str]
    has_structured_data: bool
    has_document_metadata: bool


class HistoryCasePage(BaseModel):
    items: list[HistoryCaseSummary]
    total: int
    offset: int
    limit: int
    permissions: HistoryPermissions


class HistoryDocument(BaseModel):
    document_id: UUID
    case_id: UUID
    document_type: str
    source_module: Literal["valuation", "review"]
    object_key: str = Field(exclude=True)
    file_name: str
    content_type: str
    created_at: datetime
    updated_at: None = None
    document_group_id: UUID
    version_no: int
    is_active: bool
    file_size_bytes: int
    checksum_sha256: str
    download_available: bool | None = None


class HistoryVersionValue(BaseModel):
    document_version: int
    value: Any = None
    raw_text: str | None = None
    page_number: int | None = None


class HistoryVersionDiff(BaseModel):
    field_code: str
    field_path: str | None = None
    previous: HistoryVersionValue
    current: HistoryVersionValue


class HistoryCaseVersion(BaseModel):
    version_no: int
    change_summary: str | None = None
    created_by: str | None = None
    created_at: datetime


class HistoryChange(BaseModel):
    entity_type: str
    field_name: str
    old_value: Any = None
    new_value: Any = None
    change_reason: str | None = None
    changed_by: str | None = None
    changed_at: datetime


class HistoryCaseDetail(BaseModel):
    case: dict[str, Any]
    parcels: list[dict[str, Any]]
    documents: list[HistoryDocument]
    valuation: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    versions: list[HistoryCaseVersion] = Field(default_factory=list)
    changes: list[HistoryChange] = Field(default_factory=list)
    version_diffs: list[HistoryVersionDiff] = Field(default_factory=list)
    permissions: HistoryPermissions


class HistorySearchParams(BaseModel):
    keyword: str | None = Field(default=None, max_length=200)
    city_code: str | None = Field(default=None, max_length=20)
    district_code: str | None = Field(default=None, max_length=20)
    section_name: str | None = Field(default=None, max_length=100)
    result: HistoryResult | None = None
    date_field: DateField = "updated_at"
    date_from: date | None = None
    date_to: date | None = None
    sort: HistorySort = "updated_at"
    order: SortOrder = "desc"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("keyword", "city_code", "district_code", "section_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be later than date_to")
        return self
