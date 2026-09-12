from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportType(StrEnum):
    REPORT_COMPARISON_COMMERCIAL = "REPORT_COMPARISON_COMMERCIAL"


class ReportSectionStatus(StrEnum):
    MISSING = "MISSING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class ReportPageRequirementResponse(BaseModel):
    code: str
    name: str
    kind: str
    form_code: str | None = None
    document_type: str | None = None


class ReportTypeResponse(BaseModel):
    report_type: ReportType
    name: str
    land_use_type: str
    valuation_method: str
    page_count: int


class ReportRequirementsResponse(ReportTypeResponse):
    pages: list[ReportPageRequirementResponse]


class ReportPackageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_type: ReportType = ReportType.REPORT_COMPARISON_COMMERCIAL
    prepared_date: date | None = None


class ReportComponentResponse(BaseModel):
    code: str
    form_instance_id: UUID
    form_status: str


class ReportPackageResponse(BaseModel):
    report_id: UUID
    case_id: UUID
    report_type: ReportType
    version_no: int
    prepared_date: date | None
    components: list[ReportComponentResponse]
    created_at: datetime
    updated_at: datetime


class ReportProgressSectionResponse(BaseModel):
    code: str
    name: str
    status: ReportSectionStatus
    form_instance_id: UUID | None = None
    document_type: str | None = None


class ReportProgressResponse(BaseModel):
    report_id: UUID | None
    report_type: ReportType
    version_no: int | None
    completion_rate: str
    sections: list[ReportProgressSectionResponse]
    blocking_errors: list[str]


class ReportDraftReadinessResponse(BaseModel):
    report_id: UUID
    case_id: UUID
    can_generate_pages_1_3_draft: bool
    can_generate_pages_1_6_draft: bool
    can_generate_formal_report: bool
    missing_map_document_types: list[str]
    blocking_errors: list[str]
    warnings: list[str]
