from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.valuation.documents.schemas import DocumentResponse
from app.valuation.extraction.schemas import (
    CandidateDecision,
    ExtractedFieldResponse,
    ExtractionResponse,
)
from app.valuation.f03_schemas import BenchmarkLandCreate
from app.valuation.rule_packs.coverage import NEW_TAIPEI_DISTRICT_CODES
from app.valuation.schemas import CaseCreate, CaseResponse, ParcelCreate


class AutomatedWorkflowStatus(StrEnum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    READY_FOR_DRAFT = "READY_FOR_DRAFT"
    READY_FOR_VALIDATION = "READY_FOR_VALIDATION"


class AutomatedBenchmarkLandInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    parcel_index: int = Field(ge=0)
    benchmark_land_no: str = Field(min_length=1, max_length=30)
    price_zone_no: str = Field(min_length=1, max_length=30)
    land_consolidation_serial: str | None = Field(default=None, max_length=30)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    def as_create(self, parcel_id: UUID) -> BenchmarkLandCreate:
        return BenchmarkLandCreate(
            parcel_id=parcel_id,
            benchmark_land_no=self.benchmark_land_no,
            price_zone_no=self.price_zone_no,
            land_consolidation_serial=self.land_consolidation_serial,
            latitude=self.latitude,
            longitude=self.longitude,
        )


class AutomatedIntakeManifest(BaseModel):
    """All structured input supplied once with the uploaded source documents."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case: CaseCreate
    parcels: list[ParcelCreate] = Field(default_factory=list, max_length=100)
    benchmark_lands: list[AutomatedBenchmarkLandInput] = Field(
        default_factory=list,
        max_length=20,
    )
    prepared_date: date | None = None
    create_commercial_report: bool = True
    category_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_manifest(self):
        if self.case.district_code not in NEW_TAIPEI_DISTRICT_CODES:
            raise ValueError("案件行政區代碼必須屬於新北市29區")
        for parcel in self.parcels:
            if parcel.district_code not in NEW_TAIPEI_DISTRICT_CODES:
                raise ValueError("宗地行政區代碼必須屬於新北市29區")
            if parcel.district_code != self.case.district_code:
                raise ValueError("簡化流程中的宗地行政區必須與案件一致")
        for benchmark in self.benchmark_lands:
            if benchmark.parcel_index >= len(self.parcels):
                raise ValueError("比準地 parcel_index 超出 parcels 範圍")
        return self


class AutomatedDocumentResult(BaseModel):
    document: DocumentResponse
    detected_category: str
    category_source: str
    extraction: ExtractionResponse | None = None


class AutomatedCandidateConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    extracted_field_id: UUID
    decision: CandidateDecision
    corrected_value: Any | None = None

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision == CandidateDecision.REJECT and self.corrected_value is not None:
            raise ValueError("拒絕候選欄位時不可提供 corrected_value")
        return self


class AutomatedConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmations: list[AutomatedCandidateConfirmation] = Field(
        default_factory=list,
        max_length=500,
    )
    confirm_apply: bool

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirm_apply:
            raise ValueError("套用確認資料前必須將 confirm_apply 設為 true")
        return self


class ManualFieldValuesRequest(BaseModel):
    """Non-empty values entered by a user in the confirmation workbench."""

    model_config = ConfigDict(extra="forbid")

    values: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AutomatedFormGuidance(BaseModel):
    form_code: str
    form_instance_id: UUID | None = None
    required_fields: list[str]
    confirmed_or_applied_fields: list[str] = Field(default_factory=list)
    pending_confirmation_fields: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    calculation_ready: bool
    next_action: str
    fill_endpoint: str | None = None
    calculate_endpoint: str | None = None
    validate_endpoint: str | None = None


class AutomatedConfirmationExport(BaseModel):
    document_id: UUID
    filename: str
    download_path: str


class AutomatedWorkflowResponse(BaseModel):
    status: AutomatedWorkflowStatus
    case: CaseResponse
    parcel_ids: list[UUID]
    benchmark_land_ids: list[UUID]
    f03_form_instance_id: UUID
    report_id: UUID | None
    documents: list[AutomatedDocumentResult]
    candidates: list[ExtractedFieldResponse]
    pending_candidate_count: int
    blank_fields_remain: bool
    missing_items: list[str] = Field(default_factory=list)
    warnings: list[str]
    ignored_duplicate_files: list[str] = Field(default_factory=list)
    next_action: str
    draft_pages_1_3_url: str | None = None
    draft_pages_1_6_url: str | None = None
    form_guidance: list[AutomatedFormGuidance] = Field(default_factory=list)
    automatic_pdf_generation_enabled: bool = False
    automatic_confirmation_export_enabled: bool = True
    confirmation_export: AutomatedConfirmationExport | None = None
    manual_fields_saved: list[str] = Field(default_factory=list)
    manual_fields_ignored: list[str] = Field(default_factory=list)
    manual_field_errors: dict[str, str] = Field(default_factory=dict)
    manual_field_values: dict[str, dict[str, Any]] = Field(default_factory=dict)
