from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ReportCase(BaseModel):
    case_id: UUID
    case_no: str
    case_title: str
    valuation_base_date: str
    district_code: str


class ReportRun(BaseModel):
    validation_run_id: UUID
    run_no: int
    run_status: str
    rule_version_id: UUID | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class ReportDecision(BaseModel):
    decision_id: UUID
    finding_id: UUID | None = None
    decision: str
    reason: str
    decided_by_user_id: UUID | None = None
    decided_at: datetime
    before_value: dict | None = None
    after_value: dict | None = None


class ReportAIAssessment(BaseModel):
    status: str
    reasoning_summary: str | None = None
    confidence: Decimal | None = None


class ReportFinding(BaseModel):
    finding_id: UUID
    finding_code: str
    finding_type: str
    severity: str
    title: str
    description: str
    status: str
    source_evidence: list
    reported_text: str | None = None
    reported_value: str | None = None
    legal_basis: list
    reported_grade: str | None = None
    system_grade: str | None = None
    reported_adjustment_rate: Decimal | None = None
    system_adjustment_rate: Decimal | None = None
    comparison_result: dict
    recommended_action: dict
    supersedes_finding_id: UUID | None = None
    ai_assessment: ReportAIAssessment
    decisions: list[ReportDecision] = Field(default_factory=list)


class ReportRiskSummary(BaseModel):
    overall_risk_level: str
    high_count: int
    medium_count: int
    low_count: int
    missing_item_count: int
    risk_reasons: list


class ReviewReportInput(BaseModel):
    case: ReportCase
    run: ReportRun
    review_status: str
    missing_item_count: int
    findings: list[dict[str, Any]]
    risk_summary: ReportRiskSummary
    decisions: list[ReportDecision]


class ReviewReport(BaseModel):
    case: ReportCase
    run: ReportRun
    review_status: str
    missing_item_count: int
    findings: list[ReportFinding]
    risk_summary: ReportRiskSummary
    case_decisions: list[ReportDecision]


def build_review_report(data: ReviewReportInput) -> ReviewReport:
    decisions_by_finding: dict[UUID, list[ReportDecision]] = {}
    case_decisions: list[ReportDecision] = []
    for decision in data.decisions:
        if decision.finding_id is None:
            case_decisions.append(decision)
        else:
            decisions_by_finding.setdefault(decision.finding_id, []).append(decision)

    findings: list[ReportFinding] = []
    for raw in data.findings:
        finding_id = UUID(str(raw["finding_id"]))
        findings.append(
            ReportFinding(
                **{
                    key: value
                    for key, value in raw.items()
                    if key
                    not in {
                        "ai_status",
                        "ai_reasoning_summary",
                        "ai_confidence",
                    }
                },
                ai_assessment=ReportAIAssessment(
                    status=raw.get("ai_status", "NOT_REQUESTED"),
                    reasoning_summary=raw.get("ai_reasoning_summary"),
                    confidence=raw.get("ai_confidence"),
                ),
                decisions=decisions_by_finding.get(finding_id, []),
            )
        )
    return ReviewReport(
        case=data.case,
        run=data.run,
        review_status=data.review_status,
        missing_item_count=data.missing_item_count,
        findings=findings,
        risk_summary=data.risk_summary,
        case_decisions=case_decisions,
    )
