from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.valuation.rule_packs.coverage import NEW_TAIPEI_DISTRICT_CODES


VALUATION_CASE_TYPE = "LAND"
VALUATION_CASE_TYPE_ALIASES = frozenset(
    {
        VALUATION_CASE_TYPE,
        "LAND_VALUATION",
        "LAND_ACQUISITION",
        "土地徵收補償市價查估",
        "土地徵收補償市價查估案件",
    }
)
NEW_TAIPEI_CITY_CODE = "65000000"
NEW_TAIPEI_CITY_CODE_ALIASES = frozenset(
    {
        NEW_TAIPEI_CITY_CODE,
        "65000",
        "NWT",
    }
)
def normalize_valuation_case_type(value: str) -> str:
    normalized = value.strip()
    alias = normalized.upper() if normalized.isascii() else normalized
    if alias not in VALUATION_CASE_TYPE_ALIASES:
        raise ValueError("案件類型僅支援土地徵收補償市價查估")
    return VALUATION_CASE_TYPE


def normalize_new_taipei_city_code(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in NEW_TAIPEI_CITY_CODE_ALIASES:
        raise ValueError("本系統估價案件僅支援新北市")
    return NEW_TAIPEI_CITY_CODE


def validate_new_taipei_district_code(value: str) -> str:
    normalized = value.strip()
    if normalized not in NEW_TAIPEI_DISTRICT_CODES:
        raise ValueError("請提供有效的新北市行政區代碼")
    return normalized


class CaseStatus(StrEnum):
    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    REVIEWING = "REVIEWING"
    CORRECTION = "CORRECTION"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    IN_REVIEW = "IN_REVIEW"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"


class ValuationWorkspaceStage(StrEnum):
    CASE = "case"
    DOCUMENTS = "documents"
    AI_REVIEW = "ai-review"
    DATA = "data"
    CALCULATION = "calculation"
    REPORT = "report"


class FormCode(StrEnum):
    F01 = "F01"
    F02 = "F02"
    F03 = "F03"
    F04 = "F04"
    S01 = "S01"
    F02_RF = "F02-RF"


class FormStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    CHECKED = "CHECKED"
    FINAL = "FINAL"
    VOID = "VOID"


class RequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class CaseCreate(RequestModel):
    case_no: str = Field(min_length=1, max_length=50)
    case_title: str = Field(min_length=1, max_length=200)
    case_type: str = Field(min_length=1, max_length=50)
    requesting_agency: str | None = Field(default=None, max_length=200)
    valuation_base_date: date
    valuation_due_date: date | None = None
    city_code: str = Field(default=NEW_TAIPEI_CITY_CODE, min_length=1, max_length=20)
    district_code: str = Field(min_length=1, max_length=20)
    land_use_type: str | None = Field(default=None, max_length=100)

    @field_validator("case_type")
    @classmethod
    def normalize_case_type(cls, value: str) -> str:
        return normalize_valuation_case_type(value)

    @field_validator("city_code")
    @classmethod
    def normalize_city_code(cls, value: str) -> str:
        return normalize_new_taipei_city_code(value)

    @field_validator("district_code")
    @classmethod
    def validate_district_code(cls, value: str) -> str:
        return validate_new_taipei_district_code(value)


class CaseUpdate(RequestModel):
    case_title: str | None = Field(default=None, min_length=1, max_length=200)
    case_type: str | None = Field(default=None, min_length=1, max_length=50)
    requesting_agency: str | None = Field(default=None, max_length=200)
    valuation_base_date: date | None = None
    valuation_due_date: date | None = None
    city_code: str | None = Field(default=None, min_length=1, max_length=20)
    district_code: str | None = Field(default=None, min_length=1, max_length=20)
    land_use_type: str | None = Field(default=None, max_length=100)

    @field_validator("case_type")
    @classmethod
    def normalize_case_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_valuation_case_type(value)

    @field_validator("city_code")
    @classmethod
    def normalize_city_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_new_taipei_city_code(value)

    @field_validator("district_code")
    @classmethod
    def validate_district_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_new_taipei_district_code(value)

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個要修改的欄位")
        required_fields = {
            "case_title",
            "case_type",
            "valuation_base_date",
            "city_code",
            "district_code",
        }
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in required_fields
        ):
            raise ValueError("案件必填欄位不可設為 null")
        return self


class CaseWorkspaceUpdate(RequestModel):
    confirm_basic_info: bool = False
    last_workspace_stage: ValuationWorkspaceStage | None = None

    @model_validator(mode="after")
    def require_workspace_update(self):
        if not self.confirm_basic_info and self.last_workspace_stage is None:
            raise ValueError("至少需要確認案件資料或更新工作階段")
        return self


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: UUID
    case_no: str
    case_title: str
    case_type: str
    requesting_agency: str | None
    valuation_base_date: date
    valuation_due_date: date | None
    city_code: str
    district_code: str
    land_use_type: str | None
    case_status: CaseStatus
    basic_info_confirmed_at: datetime | None = None
    basic_info_confirmed_by_user_id: UUID | None = None
    last_workspace_stage: ValuationWorkspaceStage = ValuationWorkspaceStage.CASE
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ParcelCreate(RequestModel):
    district_code: str = Field(min_length=1, max_length=20)
    section_name: str = Field(min_length=1, max_length=100)
    subsection_name: str = Field(default="", max_length=100)
    land_no: str = Field(min_length=1, max_length=50)
    area_sqm: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    land_use_zone: str | None = Field(default=None, max_length=100)
    designated_use: str | None = Field(default=None, max_length=100)
    ownership_numerator: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    ownership_denominator: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    source_document_id: UUID | None = None

    @model_validator(mode="after")
    def validate_ownership(self):
        numerator = self.ownership_numerator
        denominator = self.ownership_denominator
        if (numerator is None) != (denominator is None):
            raise ValueError("權利分子與分母必須同時提供")
        if numerator is not None and denominator is not None and numerator > denominator:
            raise ValueError("權利分子不可大於分母")
        return self


class ParcelUpdate(RequestModel):
    district_code: str | None = Field(default=None, min_length=1, max_length=20)
    section_name: str | None = Field(default=None, min_length=1, max_length=100)
    subsection_name: str | None = Field(default=None, max_length=100)
    land_no: str | None = Field(default=None, min_length=1, max_length=50)
    area_sqm: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    land_use_zone: str | None = Field(default=None, max_length=100)
    designated_use: str | None = Field(default=None, max_length=100)
    ownership_numerator: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    ownership_denominator: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    source_document_id: UUID | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個要修改的欄位")
        required_fields = {
            "district_code",
            "section_name",
            "subsection_name",
            "land_no",
            "area_sqm",
        }
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in required_fields
        ):
            raise ValueError("宗地必填欄位不可設為 null")
        ownership_fields = {
            "ownership_numerator",
            "ownership_denominator",
        }
        supplied = ownership_fields.intersection(self.model_fields_set)
        if supplied and supplied != ownership_fields:
            raise ValueError("修改權利範圍時，分子與分母必須同時提供")
        if supplied and (
            (self.ownership_numerator is None)
            != (self.ownership_denominator is None)
        ):
            raise ValueError("權利分子與分母必須同時提供或同時清除")
        if (
            supplied
            and self.ownership_numerator is not None
            and self.ownership_denominator is not None
            and self.ownership_numerator > self.ownership_denominator
        ):
            raise ValueError("權利分子不可大於分母")
        return self


class ParcelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    parcel_id: UUID
    case_id: UUID
    district_code: str
    section_name: str
    subsection_name: str
    land_no: str
    area_sqm: Decimal
    land_use_zone: str | None
    designated_use: str | None
    ownership_numerator: Decimal | None
    ownership_denominator: Decimal | None
    source_document_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ParcelImportCandidateResponse(BaseModel):
    source_location: str
    source_serial: str | None = None
    source_owner_name: str | None = None
    district_code: str | None = None
    district_name: str | None = None
    section_name: str | None = None
    subsection_name: str = ""
    land_no: str | None = None
    area_sqm: Decimal | None = None
    land_use_zone: str | None = None
    designated_use: str | None = None
    ownership_numerator: Decimal | None = None
    ownership_denominator: Decimal | None = None
    status: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    existing_parcel_id: UUID | None = None


class ParcelImportPreviewResponse(BaseModel):
    document_id: UUID
    filename: str
    layout: str
    candidates: list[ParcelImportCandidateResponse]
    ready_count: int
    needs_confirmation_count: int
    duplicate_count: int


class ParcelImportRow(RequestModel):
    source_location: str = Field(min_length=1, max_length=120)
    source_serial: str | None = Field(default=None, max_length=80)
    district_code: str = Field(min_length=1, max_length=20)
    section_name: str = Field(min_length=1, max_length=100)
    subsection_name: str = Field(default="", max_length=100)
    land_no: str = Field(min_length=1, max_length=50)
    area_sqm: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    land_use_zone: str | None = Field(default=None, max_length=100)
    designated_use: str | None = Field(default=None, max_length=100)
    ownership_numerator: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    ownership_denominator: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )

    @model_validator(mode="after")
    def validate_ownership(self):
        numerator = self.ownership_numerator
        denominator = self.ownership_denominator
        if (numerator is None) != (denominator is None):
            raise ValueError("權利分子與分母必須同時提供")
        if numerator is not None and denominator is not None and numerator > denominator:
            raise ValueError("權利分子不可大於分母")
        return self


class ParcelBatchImportRequest(RequestModel):
    rows: list[ParcelImportRow] = Field(min_length=1, max_length=500)


class ParcelBatchImportResponse(BaseModel):
    created: list[ParcelResponse]
    skipped_duplicate_count: int
    skipped_duplicate_locations: list[str] = Field(default_factory=list)


class FormRequirementResponse(BaseModel):
    form_type: FormCode
    form_name: str
    required_fields: list[str]
    required_documents: list[str]
    optional_documents: list[str]
    calculated_fields: list[str]


class OfficialFormTemplateResponse(BaseModel):
    schema_version: str
    form_code: str
    form_name: str
    source_title: str
    sections: list[dict[str, Any]]
    calculated_fields: list[str]


class OfficialFormulaPolicyResponse(BaseModel):
    formula_code: str
    rounding_code: str
    source_roles: list[str]
    formulas: dict[str, str]
    safety: str


class FormCreate(RequestModel):
    form_code: FormCode
    prepared_date: date | None = None
    source_document_id: UUID | None = None
    form_content: dict[str, Any] = Field(default_factory=dict)


class FormDraftUpdate(RequestModel):
    prepared_date: date | None = None
    source_document_id: UUID | None = None
    form_content: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個要修改的欄位")
        if "form_content" in self.model_fields_set and self.form_content is None:
            raise ValueError("表單內容不可設為 null")
        return self


class FormResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    form_instance_id: UUID
    case_id: UUID
    form_code: FormCode
    version_no: int
    form_status: FormStatus
    form_content: dict[str, Any]
    prepared_date: date | None
    source_document_id: UUID | None
    output_document_id: UUID | None
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CaseBootstrapResponse(BaseModel):
    case: CaseResponse
    initial_form: FormResponse
