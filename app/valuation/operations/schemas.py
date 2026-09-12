from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CalculationRequest(BaseModel):
    form_instance_id: UUID


class CalculationResponse(BaseModel):
    calculation_id: UUID
    case_id: UUID
    form_instance_id: UUID
    benchmark_valuation_id: UUID
    formula_version: str
    result: Decimal
    currency_code: str
    calculation_snapshot: dict[str, Any]
    request_id: UUID | None
    calculated_at: datetime


class ValidationRequest(BaseModel):
    form_instance_id: UUID


class ValidationFindingResponse(BaseModel):
    finding_id: UUID
    rule_code: str
    rule_version: str
    field_path: str | None
    severity: Literal["ERROR", "WARNING"]
    actual_value: Any = None
    expected_value: Any = None
    message: str
    request_id: UUID | None
    created_at: datetime


class ValidationResponse(BaseModel):
    validation_run_id: UUID
    case_id: UUID
    form_instance_id: UUID
    run_status: str
    passed_count: int
    warning_count: int
    failed_count: int
    can_generate_report: bool
    ruleset_version: str
    correction_hints: list[str]
    findings: list[ValidationFindingResponse]
    request_id: UUID | None
    started_at: datetime
    completed_at: datetime | None


class ReportRequest(BaseModel):
    form_instance_id: UUID


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    case_id: UUID
    form_instance_id: UUID
    validation_run_id: UUID
    calculation_id: UUID
    filename: str
    mime_type: str
    version_no: int
    bucket_name: str
    object_key: str
    checksum_sha256: str
    file_size_bytes: int
    download_path: str
    request_id: UUID | None
