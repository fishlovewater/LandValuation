from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FormalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FormalCalculationRequest(FormalModel):
    confirm_calculation: bool

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirm_calculation:
            raise ValueError("正式計算前必須明確確認")
        return self


class FormalTargetCalculationResponse(BaseModel):
    comparison_target_id: UUID
    regional_adjustment_rate: Decimal
    individual_adjustment_rate: Decimal
    total_adjustment_absolute: Decimal
    date_adjusted_price: Decimal
    regional_adjusted_price: Decimal
    trial_price: Decimal
    weight: Decimal


class FormalCalculationResponse(BaseModel):
    case_id: UUID
    report_id: UUID
    comparison_analysis_id: UUID | None = None
    rule_version_id: UUID | None = None
    formula_code: str
    rounding_code: str
    benchmark_comparison_price: Decimal | None = None
    targets: list[FormalTargetCalculationResponse]
    input_fingerprint: str
    calculated_at: datetime


class FormalValidationFinding(BaseModel):
    code: str
    severity: Literal["ERROR", "WARNING"]
    message: str
    field_code: str | None = None


class FormalValidationResponse(BaseModel):
    validation_run_id: UUID
    case_id: UUID
    report_id: UUID
    run_status: Literal["COMPLETED"] = "COMPLETED"
    passed_count: int
    warning_count: int
    failed_count: int
    can_generate_formal_report: bool
    input_fingerprint: str | None = None
    findings: list[FormalValidationFinding]
    completed_at: datetime


class FormalReportRequest(FormalModel):
    confirm_generate: bool
    acknowledged_warning_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirm_generate:
            raise ValueError("產生正式六頁 PDF 前必須明確確認")
        if len(self.acknowledged_warning_codes) != len(
            set(self.acknowledged_warning_codes)
        ):
            raise ValueError("WARNING 代碼不可重複")
        return self


class FormalReportResponse(BaseModel):
    document_id: UUID
    case_id: UUID
    report_id: UUID
    validation_run_id: UUID
    filename: str
    mime_type: Literal["application/pdf"] = "application/pdf"
    version_no: int
    bucket_name: str
    object_key: str
    checksum_sha256: str
    file_size_bytes: int
    download_path: str
    request_id: UUID | None = None


class TemplateExportResponse(BaseModel):
    form_code: str
    title: str
    location_id: UUID | None = None
    location_label: str | None = None
    document_id: UUID
    filename: str
    mime_type: str
    version_no: int
    file_size_bytes: int
    download_path: str

class FormalWorkflowStatusResponse(BaseModel):
    validation: FormalValidationResponse | None = None
    report: FormalReportResponse | None = None
    template_exports: list[TemplateExportResponse] = Field(default_factory=list)
    requires_revalidation_for_submission: bool = False
