import { riskLabel, severityLabel, statusLabel } from '../../utils/enumLabels'
import type * as T from './review.types'

export function normalizeScalar(value: unknown): string | undefined {
  if (value == null) return undefined
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (typeof value === 'object' && 'toString' in value) return String(value)
  return undefined
}

export function mapReviewCase(dto: T.WorkbenchCaseDto): T.ReviewCaseSummary {
  return {
    reviewId: dto.review_id,
    caseId: dto.case_id,
    caseNo: dto.case_no,
    title: dto.case_title,
    district: dto.district_code || undefined,
    status: dto.review_status,
    statusLabel: statusLabel(dto.review_status),
    riskLevel: dto.current_risk_level ?? undefined,
    riskLabel: riskLabel(dto.current_risk_level),
    missingItemCount: dto.missing_item_count,
    highCount: dto.high_count,
    mediumCount: dto.medium_count,
    lowCount: dto.low_count,
    receivedAt: dto.received_at,
    dueAt: dto.due_at ?? undefined,
    reviewerName: dto.assigned_reviewer_display_name ?? undefined,
    latestRunId: dto.latest_run?.validation_run_id,
    urgencyLevel: dto.urgency_level,
    remainingDays: dto.remaining_days ?? undefined,
    correctionRound: dto.correction_round,
    raw: { status: dto.review_status, riskLevel: dto.current_risk_level ?? undefined },
  }
}

function mapMissingItem(dto: T.MissingItemDto): T.MissingItem {
  return {
    missingItemId: dto.missing_item_id,
    itemCode: dto.item_code,
    itemName: dto.item_name,
    severity: dto.severity,
    status: dto.status,
    reason: dto.reason ?? undefined,
  }
}

function mapRun(dto: T.ValidationRunDto): T.ReviewRun {
  return {
    runId: dto.validation_run_id,
    runNo: dto.run_no ?? undefined,
    status: dto.run_status,
    passedCount: dto.passed_count,
    warningCount: dto.warning_count,
    failedCount: dto.failed_count,
    startedAt: dto.started_at,
    completedAt: dto.completed_at ?? undefined,
  }
}

function mapFinding(dto: T.FindingDto): T.FindingViewModel {
  return {
    findingId: dto.finding_id,
    reviewId: dto.review_id,
    runId: dto.validation_run_id ?? undefined,
    findingCode: dto.finding_code,
    findingType: dto.finding_type,
    severity: dto.severity,
    severityLabel: severityLabel(dto.severity),
    title: dto.title,
    description: dto.description,
    status: dto.status,
    documentId: dto.document_id ?? undefined,
    documentVersion: dto.document_version ?? undefined,
    pageNumber: dto.page_number ?? undefined,
    fieldPath: dto.field_path ?? undefined,
    reportedText: dto.reported_text ?? undefined,
    reportedValue: dto.reported_value ?? undefined,
    reportedGrade: dto.reported_grade ?? undefined,
    systemGrade: dto.system_grade ?? undefined,
    reportedAdjustmentRate: normalizeScalar(dto.reported_adjustment_rate),
    systemAdjustmentRate: normalizeScalar(dto.system_adjustment_rate),
    aiReasoningSummary: dto.ai_reasoning_summary ?? undefined,
    aiConfidence: normalizeScalar(dto.ai_confidence),
    aiStatus: dto.ai_status,
  }
}

function mapRiskSummary(dto: T.RiskSummaryDto): T.ReviewRiskSummary {
  return {
    riskSummaryId: dto.risk_summary_id,
    reviewId: dto.review_id,
    runId: dto.validation_run_id ?? undefined,
    riskLevel: dto.overall_risk_level,
    riskLabel: riskLabel(dto.overall_risk_level),
    riskScore: normalizeScalar(dto.risk_score),
    summary: dto.summary,
    highCount: dto.high_count,
    mediumCount: dto.medium_count,
    lowCount: dto.low_count,
    missingItemCount: dto.missing_item_count,
    generatedAt: dto.generated_at,
  }
}

export function mapWorkbenchDetail(dto: T.WorkbenchDetailDto): T.ReviewCaseDetail {
  const pseudoListItem: T.WorkbenchCaseDto = {
    review_id: dto.review.review_id,
    case_id: dto.case.case_id,
    case_no: dto.case.case_no,
    case_title: dto.case.case_title,
    district_code: dto.case.district_code,
    review_status: dto.review.review_status,
    current_risk_level: dto.review.current_risk_level,
    missing_item_count: dto.review.missing_item_count,
    high_count: dto.review.high_count,
    medium_count: dto.review.medium_count,
    low_count: dto.review.low_count,
    received_at: dto.review.received_at,
    due_at: dto.review.due_at,
    assigned_reviewer_display_name: null,
    latest_run: dto.review.latest_validation_run_id
      ? { validation_run_id: dto.review.latest_validation_run_id, run_no: null, run_status: dto.runs[0]?.run_status ?? 'UNKNOWN' }
      : null,
    urgency_level: 'NOT_SET',
    remaining_days: null,
    correction_round: dto.correction_requests.length,
    latest_correction_status: dto.correction_requests.at(-1)?.status ?? null,
  }
  return {
    ...mapReviewCase(pseudoListItem),
    valuationBaseDate: dto.case.valuation_base_date,
    caseStatus: dto.case.case_status,
    documents: dto.documents.map((d) => ({
      documentId: d.document_id,
      documentType: d.document_type,
      filename: d.original_filename,
      mimeType: d.mime_type,
      versionNo: d.version_no,
      isActive: d.is_active,
      uploadedAt: d.uploaded_at,
      contentAvailable: d.mime_type === 'application/pdf',
    })),
    missingItems: dto.missing_items.map(mapMissingItem),
    runs: dto.runs.map(mapRun),
    findings: dto.findings.map(mapFinding),
    riskSummary: dto.risk_summary ? mapRiskSummary(dto.risk_summary) : undefined,
    decisions: dto.decisions,
    reports: [...(dto.report_document ? [dto.report_document] : []), ...dto.generated_reports],
    correctionRequests: dto.correction_requests,
  }
}

export function mapWorkbenchStart(dto: T.WorkbenchStartDto): T.ReviewStartResult {
  return {
    outcome: dto.outcome,
    missingItems: dto.completeness.items.map(mapMissingItem),
    run: dto.run ? mapRun(dto.run) : undefined,
    findings: dto.findings.map(mapFinding),
    riskSummary: dto.risk_summary ? mapRiskSummary(dto.risk_summary) : undefined,
  }
}
