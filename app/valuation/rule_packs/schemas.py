from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.valuation.rule_packs.coverage import (
    NEW_TAIPEI_DISTRICT_CODES,
    NEW_TAIPEI_DISTRICTS,
)


class LandUseType(StrEnum):
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    INDUSTRIAL = "INDUSTRIAL"
    AGRICULTURAL = "AGRICULTURAL"
    OTHER = "OTHER"


class DistrictScopeMode(StrEnum):
    ALL = "ALL"
    INCLUDE = "INCLUDE"


class RuleSourceRole(StrEnum):
    PRIMARY = "PRIMARY"
    LEGAL_BASIS = "LEGAL_BASIS"
    NATIONAL_MANUAL = "NATIONAL_MANUAL"
    LOCAL_MANUAL = "LOCAL_MANUAL"
    FACTOR_STANDARD = "FACTOR_STANDARD"
    FORM_TEMPLATE = "FORM_TEMPLATE"
    CASE_EXAMPLE = "CASE_EXAMPLE"
    OTHER = "OTHER"


class DistrictScope(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: DistrictScopeMode
    district_codes: list[str] = Field(default_factory=list, max_length=29)

    @model_validator(mode="after")
    def validate_scope(self):
        codes = [item for item in self.district_codes if item]
        if len(codes) != len(set(codes)):
            raise ValueError("行政區代碼不可重複")
        if any(len(item) > 20 for item in codes):
            raise ValueError("行政區代碼長度不可超過 20")
        unknown = sorted(set(codes) - NEW_TAIPEI_DISTRICT_CODES)
        if unknown:
            raise ValueError(
                "行政區代碼不屬於新北市29區：" + ", ".join(unknown)
            )
        if self.mode == DistrictScopeMode.ALL and codes:
            raise ValueError("ALL 適用範圍不可同時指定行政區")
        if self.mode == DistrictScopeMode.INCLUDE and not codes:
            raise ValueError("INCLUDE 適用範圍至少需要一個行政區")
        self.district_codes = codes
        return self


class RulePackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rule_set_code: str = Field(pattern=r"^[A-Z][A-Z0-9_.-]{2,49}$")
    version_name: str = Field(min_length=1, max_length=200)
    effective_from: date | None = None
    effective_to: date | None = None
    effective_date_status: Literal["CONFIRMED", "UNKNOWN"] = "CONFIRMED"
    jurisdiction_code: Literal["NEW_TAIPEI_CITY"] = "NEW_TAIPEI_CITY"
    land_use_types: list[LandUseType] = Field(min_length=1, max_length=5)
    formula_code: Literal["NTPC_COMPARISON_V1"] = "NTPC_COMPARISON_V1"
    rounding_code: Literal["NTPC_LAND_PRICE_V1"] = "NTPC_LAND_PRICE_V1"
    source_document_type: Literal["REGULATION", "STANDARD", "MANUAL", "OTHER"]
    source_reference: str | None = Field(default=None, max_length=1000)
    primary_source_role: RuleSourceRole = RuleSourceRole.PRIMARY
    primary_page_reference: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    confirm_source_upload: bool

    @model_validator(mode="after")
    def validate_manifest(self):
        if self.effective_date_status == "CONFIRMED" and self.effective_from is None:
            raise ValueError("已確認適用日必須提供 effective_from")
        if self.effective_date_status == "UNKNOWN" and self.effective_from is not None:
            raise ValueError("適用日未知時不可同時填寫 effective_from")
        if self.effective_date_status == "UNKNOWN" and self.effective_to is not None:
            raise ValueError("適用日未知時不可填寫 effective_to")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to 不可早於 effective_from")
        if len(self.land_use_types) != len(set(self.land_use_types)):
            raise ValueError("土地用途不可重複")
        if self.primary_source_role != RuleSourceRole.PRIMARY:
            raise ValueError("主要來源角色必須是 PRIMARY")
        if not self.confirm_source_upload:
            raise ValueError("上傳規則原檔前必須明確確認")
        return self


class ExistingKnowledgeRulePackCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_document_id: UUID
    rule_set_code: str = Field(pattern=r"^[A-Z][A-Z0-9_.-]{2,49}$")
    version_name: str = Field(min_length=1, max_length=200)
    effective_from: date | None = None
    effective_to: date | None = None
    effective_date_status: Literal["CONFIRMED", "UNKNOWN"] = "CONFIRMED"
    jurisdiction_code: Literal["NEW_TAIPEI_CITY"] = "NEW_TAIPEI_CITY"
    land_use_types: list[LandUseType] = Field(min_length=1, max_length=5)
    formula_code: Literal["NTPC_COMPARISON_V1"] = "NTPC_COMPARISON_V1"
    rounding_code: Literal["NTPC_LAND_PRICE_V1"] = "NTPC_LAND_PRICE_V1"
    source_reference: str | None = Field(default=None, max_length=1000)
    primary_page_reference: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    confirm_source_link: bool

    @model_validator(mode="after")
    def validate_request(self):
        if self.effective_date_status == "CONFIRMED" and self.effective_from is None:
            raise ValueError("已確認適用日必須提供 effective_from")
        if self.effective_date_status == "UNKNOWN" and self.effective_from is not None:
            raise ValueError("適用日未知時不可同時填寫 effective_from")
        if self.effective_date_status == "UNKNOWN" and self.effective_to is not None:
            raise ValueError("適用日未知時不可填寫 effective_to")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to 不可早於 effective_from")
        if len(self.land_use_types) != len(set(self.land_use_types)):
            raise ValueError("土地用途不可重複")
        if not self.confirm_source_link:
            raise ValueError("以既有文件建立規則草稿前必須明確確認")
        return self


class RulePackSourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_role: RuleSourceRole
    source_document_type: Literal["REGULATION", "STANDARD", "MANUAL", "OTHER"]
    title: str = Field(min_length=1, max_length=300)
    source_reference: str | None = Field(default=None, max_length=1000)
    page_reference: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    is_required: bool = True
    confirm_source_upload: bool

    @model_validator(mode="after")
    def validate_source_manifest(self):
        if self.source_role == RuleSourceRole.PRIMARY:
            raise ValueError("追加來源不可使用 PRIMARY；主要來源由建立規則版本時指定")
        if not self.confirm_source_upload:
            raise ValueError("上傳規則來源前必須明確確認")
        return self


class ExistingRulePackSourceLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_document_id: UUID
    source_role: RuleSourceRole
    source_reference: str | None = Field(default=None, max_length=1000)
    page_reference: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    is_required: bool = True
    confirm_link: bool

    @model_validator(mode="after")
    def validate_link(self):
        if self.source_role == RuleSourceRole.PRIMARY:
            raise ValueError("既有文件追加關聯不可取代主要來源")
        if not self.confirm_link:
            raise ValueError("關聯既有來源文件前必須明確確認")
        return self


class RulePackEffectiveDateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_from: date
    effective_to: date | None = None
    confirm_effective_date: bool

    @model_validator(mode="after")
    def validate_effective_date(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to 不可早於 effective_from")
        if not self.confirm_effective_date:
            raise ValueError("設定規則適用日之前必須明確確認")
        return self


class FactorDefinitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    factor_code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,49}$")
    factor_name: str = Field(min_length=1, max_length=100)
    factor_category: str = Field(min_length=1, max_length=50)
    data_type: Literal["NUMBER", "TEXT", "ENUM", "BOOLEAN", "JSON"]
    unit: str | None = Field(default=None, max_length=20)
    display_order: int = Field(gt=0)


class FactorLevelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    factor_code: str = Field(min_length=1, max_length=50)
    land_use_type: LandUseType
    level_code: str = Field(min_length=1, max_length=50)
    level_name: str = Field(min_length=1, max_length=100)
    range_min: Decimal | None = None
    range_max: Decimal | None = None
    qualitative_value: str | None = Field(default=None, max_length=200)
    suggested_rate: Decimal
    maximum_impact_rate: Decimal = Field(ge=0)
    sort_order: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_level(self):
        if self.range_min is not None and self.range_max is not None:
            if self.range_max < self.range_min:
                raise ValueError("range_max 不可小於 range_min")
        if abs(self.suggested_rate) > self.maximum_impact_rate:
            raise ValueError("suggested_rate 不可超過 maximum_impact_rate")
        return self


class RulePackImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_definitions: list[FactorDefinitionInput] = Field(min_length=1)
    factor_levels: list[FactorLevelInput] = Field(min_length=1)
    confirm_import: bool = False


class RuleEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    factor_code: str = Field(min_length=1, max_length=50)
    level_code: str | None = Field(default=None, max_length=50)
    source_page: int | None = Field(default=None, ge=1)
    source_text: str = Field(min_length=1, max_length=1000)


class RulePackAIExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: UUID | None = None
    confirm_ai_analysis: bool = False


class RulePackAIExtractionResponse(BaseModel):
    rule_version_id: UUID
    source_document_id: UUID
    status: Literal["NEEDS_CONFIRMATION", "CONFIRMED"]
    provider: str
    model_id: str
    prompt_version: str
    extraction_provider: str
    factor_definitions: list[FactorDefinitionInput]
    factor_levels: list[FactorLevelInput]
    evidence: list[RuleEvidenceInput] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RulePackAIConfirmRequest(RulePackImportRequest):
    evidence: list[RuleEvidenceInput] = Field(default_factory=list)


class RulePackPublishRequest(BaseModel):
    confirm_publish: bool


class RulePackSourceResponse(BaseModel):
    rule_version_source_id: UUID
    rule_version_id: UUID
    source_document_id: UUID
    source_role: RuleSourceRole
    source_order: int
    is_primary: bool
    is_required: bool
    source_document_type: str
    title: str
    original_filename: str
    mime_type: str
    bucket_name: str
    object_key: str
    checksum_sha256: str
    file_size_bytes: int | None
    storage_etag: str | None
    source_reference: str | None
    page_reference: str | None
    notes: str | None
    publication_status: str
    created_at: datetime


class KnowledgeSourceOptionResponse(BaseModel):
    source_document_id: UUID
    document_type: str
    title: str
    original_filename: str
    mime_type: str
    bucket_name: str
    object_key: str
    checksum_sha256: str
    version_no: int
    effective_from: date | None
    effective_to: date | None
    publication_status: str
    object_exists: bool
    formal_rule_eligible: bool
    source_usage: str


class RulePackResponse(BaseModel):
    rule_version_id: UUID
    rule_set_code: str
    version_no: int
    version_name: str
    effective_from: date | None
    effective_to: date | None
    effective_date_status: Literal["CONFIRMED", "UNKNOWN"]
    status: str
    import_status: str
    jurisdiction_code: str | None
    district_scope: dict | None
    land_use_types: list[str]
    formula_code: str | None
    rounding_code: str | None
    source_document_id: UUID | None
    source_filename: str | None
    source_object_key: str | None
    source_checksum_sha256: str | None
    source_count: int = 0
    required_source_count: int = 0
    sources: list[RulePackSourceResponse] = Field(default_factory=list)
    import_summary: dict
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    created_at: datetime


class RulePackImportResponse(BaseModel):
    rule_version_id: UUID
    confirmed: bool
    factor_definition_count: int
    factor_level_count: int
    land_use_types: list[str]
    status: str
    warnings: list[str] = Field(default_factory=list)


class RuleCoverageMatch(BaseModel):
    rule_version_id: UUID
    rule_set_code: str
    version_no: int
    version_name: str
    effective_from: date
    effective_to: date | None


class RuleCoverageResponse(BaseModel):
    jurisdiction_code: Literal["NEW_TAIPEI_CITY"] = "NEW_TAIPEI_CITY"
    district_code: str
    district_name: str
    land_use_type: LandUseType
    valuation_date: date
    status: Literal["COVERED", "MISSING", "AMBIGUOUS"]
    covered: bool
    matches: list[RuleCoverageMatch] = Field(default_factory=list)
    message: str

    @model_validator(mode="after")
    def validate_district(self):
        if self.district_code not in NEW_TAIPEI_DISTRICTS:
            raise ValueError("行政區代碼不屬於新北市29區")
        if self.district_name != NEW_TAIPEI_DISTRICTS[self.district_code]:
            raise ValueError("行政區代碼與名稱不一致")
        return self


class RuleCoverageMatrixResponse(BaseModel):
    jurisdiction_code: Literal["NEW_TAIPEI_CITY"] = "NEW_TAIPEI_CITY"
    valuation_date: date
    total_combinations: int
    covered_count: int
    missing_count: int
    ambiguous_count: int
    items: list[RuleCoverageResponse]


class RulePackAuditFinding(BaseModel):
    code: str
    severity: Literal["ERROR", "WARNING"]
    message: str
    factor_code: str | None = None
    land_use_type: str | None = None


class RulePackAuditResponse(BaseModel):
    rule_version_id: UUID
    rule_set_code: str
    version_no: int
    status: str
    formal_calculation_eligible: bool
    jurisdiction_code: str | None
    district_scope: dict | None
    land_use_types: list[str]
    source_count: int
    factor_definition_count: int
    factor_level_count: int
    error_count: int
    warning_count: int
    findings: list[RulePackAuditFinding]
