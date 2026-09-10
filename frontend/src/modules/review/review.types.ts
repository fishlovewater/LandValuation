import type { CaseSummary } from '../../types/case'

export type ReviewStatusCode =
  | 'RECEIVED'
  | 'PREPROCESSING'
  | 'PENDING_MATERIALS'
  | 'READY_FOR_REVIEW'
  | 'ANALYZING'
  | 'REVIEW_REQUIRED'
  | 'RETURNED_FOR_REVISION'
  | 'SUPPLEMENT_REQUIRED'
  | 'EXPERT_REVIEW'
  | 'APPROVED'
  | 'REVIEW_COMPLETED'
  | string

export type RiskLevelCode = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string
export type WorkbenchStatusGroup = 'pending' | 'in_progress' | 'needs_input' | 'completed' | 'risk'
export type FindingTriageDecision =
  | 'CONFIRMED_ISSUE'
  | 'DISMISSED_FALSE_POSITIVE'
  | 'EXPERT_REVIEW'

export interface WorkbenchSummaryDto {
  status_counts: Record<string, number>
  high_risk_count: number
  open_finding_count: number
  missing_item_count: number
}

export interface WorkbenchLatestRunDto {
  validation_run_id: string
  run_no: number | null
  run_status: string
}

export interface WorkbenchCaseListItemDto {
  review_id: string
  case_id: string
  case_no: string
  case_title: string
  district_code: string
  review_status: string
  current_risk_level: string | null
  missing_item_count: number
  high_count: number
  medium_count: number
  low_count: number
  received_at: string
  due_at: string | null
  assigned_reviewer_display_name: string | null
  latest_run: WorkbenchLatestRunDto | null
  urgency_level: string
  remaining_days: number | null
  correction_round: number
  latest_correction_status: string | null
}

export interface WorkbenchCaseListDto {
  items: WorkbenchCaseListItemDto[]
  total: number
  limit: number
  offset: number
}

export interface WorkbenchCaseSummaryDto {
  case_id: string
  case_no: string
  case_title: string
  district_code: string
  valuation_base_date: string
  case_status: string
}

export interface ReviewDto {
  review_id: string
  case_id: string
  review_type: string
  review_status: string
  started_by_user_id: string | null
  started_at: string
  completed_at: string | null
  received_at: string
  due_at: string | null
  assigned_reviewer_id: string | null
  manual_priority: number
  manual_priority_reason: string | null
  current_risk_level: string | null
  high_count: number
  medium_count: number
  low_count: number
  missing_item_count: number
  latest_validation_run_id: string | null
  latest_submission_id?: string | null
}

export interface WorkbenchDocumentDto {
  document_id: string
  document_type: string
  original_filename: string
  mime_type: string
  version_no: number
  is_active: boolean
  uploaded_at: string
}

export interface MissingItemDto {
  missing_item_id: string
  review_id: string
  item_code: string
  item_name: string
  document_type: string | null
  severity: string
  status: string
  field_path: string | null
  reason: string | null
  affected_rule_codes: string[]
  due_at: string | null
  notified_at: string | null
  notification_status: string | null
  created_at: string
}

export interface WorkbenchRunDto {
  validation_run_id: string
  case_id: string
  review_id: string | null
  run_no: number | null
  run_status: string
  passed_count: number
  warning_count: number
  failed_count: number
  started_at: string
  completed_at: string | null
  triggered_by_user_id: string | null
  rule_version_id: string | null
  model_id: string | null
  prompt_version: string | null
  error_code: string | null
  error_message: string | null
  submission_id?: string | null
  submission_no?: number | null
  submitted_at?: string | null
  input_fingerprint?: string | null
}

export interface FindingDto {
  finding_id: string
  review_id: string
  validation_run_id: string | null
  finding_code: string
  finding_type: string
  severity: string
  title: string
  description: string
  status: string
  document_id: string | null
  document_version: number | null
  page_number: number | null
  field_path: string | null
  source_evidence: unknown[]
  reported_text: string | null
  reported_value: string | null
  legal_basis: unknown[]
  reported_grade: string | null
  system_grade: string | null
  reported_adjustment_rate: string | null
  system_adjustment_rate: string | null
  comparison_result: Record<string, unknown>
  recommended_action: Record<string, unknown>
  ai_reasoning_summary: string | null
  ai_confidence: string | null
  ai_status: string
  supersedes_finding_id: string | null
  rule_version_id: string | null
  created_at: string
}

export interface RiskSummaryDto {
  risk_summary_id: string
  review_id: string
  validation_run_id: string | null
  overall_risk_level: string
  risk_score: string | null
  summary: string
  high_count: number
  medium_count: number
  low_count: number
  missing_item_count: number
  risk_reasons: unknown[]
  generated_at: string
}

export interface WorkbenchCompletenessDto {
  ready: boolean
  review_status: string
  missing_item_count: number
  blocked_rule_codes: string[]
  items: MissingItemDto[]
}

export interface WorkbenchPreflightDto {
  outcome: 'READY' | 'BLOCKED'
  completeness: WorkbenchCompletenessDto
}

export interface WorkbenchStartDto {
  outcome: 'BLOCKED' | 'COMPLETED'
  completeness: WorkbenchCompletenessDto
  run: WorkbenchRunDto | null
  findings: FindingDto[]
  risk_summary: RiskSummaryDto | null
}

export interface DecisionDto {
  decision_id: string
  review_id: string
  finding_id: string | null
  decision: string
  reason: string | null
  decided_by_user_id: string | null
  decided_at: string
  request_id: string | null
  before_value: Record<string, unknown> | null
  after_value: Record<string, unknown> | null
}

export interface GeneratedReportDto {
  document_id: string
  case_id: string
  document_type: string
  original_filename: string
  mime_type: string
  checksum_sha256: string
  file_size_bytes: number
  version_no: number
}

export interface CorrectionRequestDto {
  correction_request_id: string
  review_id: string
  request_no: number
  based_on_validation_run_id: string
  status: string
  due_at: string
  message: string
  base_document_id: string
  base_document_version: number
  response_document_id: string | null
  response_document_version: number | null
  sent_at: string | null
  resubmitted_by_user_id: string | null
  resubmitted_at: string | null
  rechecked_at: string | null
  items: CorrectionRequestItemDto[]
}

export interface CorrectionRequestItemDto {
  correction_request_item_id: string
  finding_id: string
  finding_code: string
  finding_type: string
  severity: string
  document_id: string | null
  document_version: number | null
  page_number: number | null
  reported_text: string | null
  reported_value: string | null
  legal_basis_snapshot: unknown[]
  source_evidence_snapshot: unknown[]
  issue_summary: string
  requested_correction: string
  recheck_outcome: string
  resulting_finding_id: string | null
  rechecked_at: string | null
}

export interface WorkbenchFieldVersionDto {
  document_id: string
  document_group_id: string
  document_version: number
  field_code: string
  field_path: string | null
  normalized_value: unknown
  raw_text: string | null
  page_number: number | null
}

export interface FieldVersionDiffDto {
  document_group_id: string
  field_code: string
  field_path: string | null
  previous: WorkbenchFieldVersionDto
  current: WorkbenchFieldVersionDto
}

export interface WorkbenchCaseDetailDto {
  case: WorkbenchCaseSummaryDto
  review: ReviewDto
  submission_id: string | null
  submission_no: number | null
  submitted_at: string | null
  input_fingerprint: string | null
  documents: WorkbenchDocumentDto[]
  missing_items: MissingItemDto[]
  runs: WorkbenchRunDto[]
  findings: FindingDto[]
  risk_summary: RiskSummaryDto | null
  decisions: DecisionDto[]
  version_diffs: FieldVersionDiffDto[]
  report_document: GeneratedReportDto | null
  generated_reports: GeneratedReportDto[]
  correction_requests: CorrectionRequestDto[]
}

export interface FindingTriageRequestDto {
  review_id: string
  decision: FindingTriageDecision
  reason: string
}

export interface ReviewCompletionRequestDto {
  reason: string
}

export interface CorrectionRequestCreateDto {
  message: string
  due_at: string
}

export interface GeneratedReportCreateDto {
  format: 'xlsx' | 'docx'
}

export interface ReviewReportDto {
  case: Record<string, unknown>
  run: Record<string, unknown>
  review_status: string
  missing_item_count: number
  findings: unknown[]
  risk_summary: Record<string, unknown>
  case_decisions: unknown[]
  urgency?: Record<string, unknown> | null
  correction_requests?: unknown[]
  history?: unknown[]
}

export interface ReviewSummaryModel {
  statusCounts: Record<string, number>
  highRiskCount: number
  openFindingCount: number
  missingItemCount: number
}

export interface ReviewQueueItemModel extends CaseSummary {
  reviewId: string
  reviewStatusCode: string
  reviewStatusLabel: string
  latestValidationRunId: string | null
  riskLevelCode: string | null
  riskLevelLabel: string
  missingItemCount: number
  highCount: number
  mediumCount: number
  lowCount: number
  receivedAt: string
  dueAt: string | null
  assignedReviewerName: string | null
  latestRunId: string | null
  latestRunStatusCode: string | null
  latestRunStatusLabel: string
  urgencyLabel: string
}

export interface ReviewDocumentModel {
  documentId: string
  documentType: string
  documentTypeLabel: string
  filename: string
  mimeType: string
  mimeTypeLabel: string
  versionNo: number
  isActive: boolean
  uploadedAt: string
}

export interface ReviewRunModel {
  validationRunId: string
  reviewId: string | null
  runNo: number | null
  runStatusCode: string
  runStatusLabel: string
  passedCount: number
  warningCount: number
  failedCount: number
  startedAt: string
  completedAt: string | null
}

export interface ReviewReferenceModel {
  key: string
  title: string
  detail: string | null
  documentId: string | null
  documentVersion: number | null
  pageNumber: number | null
  verificationStatus: string | null
}

export interface ReviewFindingModel {
  findingId: string
  reviewId: string
  validationRunId: string | null
  findingCode: string
  findingCodeLabel: string
  findingType: string
  findingTypeLabel: string
  severityCode: string
  severityLabel: string
  title: string
  description: string
  statusCode: string
  statusLabel: string
  documentId: string | null
  documentVersion: number | null
  pageNumber: number | null
  fieldPath: string | null
  fieldPathLabel: string
  reportedText: string | null
  reportedValue: string | null
  systemValue: string | null
  reportedGrade: string | null
  systemGrade: string | null
  reportedAdjustmentRate: string | null
  systemAdjustmentRate: string | null
  aiReasoningSummary: string | null
  aiConfidence: string | null
  aiStatusLabel: string
  recommendedActionLabel: string | null
  sourceEvidence: ReviewReferenceModel[]
  legalBasis: ReviewReferenceModel[]
}

export interface ReviewDecisionModel {
  decisionId: string
  reviewId: string
  findingId: string | null
  decisionCode: string
  decisionLabel: string
  reason: string | null
  decidedAt: string
}

export interface ReviewVersionDiffModel {
  key: string
  fieldCode: string
  fieldPath: string | null
  fieldLabel: string
  previousDocumentVersion: number
  previousValue: string
  previousRawText: string | null
  previousPageNumber: number | null
  currentDocumentVersion: number
  currentValue: string
  currentRawText: string | null
  currentPageNumber: number | null
}

export interface ReviewDetailModel {
  caseId: string
  caseNo: string
  caseTitle: string
  districtCode: string
  valuationBaseDate: string
  caseStatusCode: string
  caseStatusLabel: string
  reviewId: string
  reviewStatusCode: string
  reviewStatusLabel: string
  latestValidationRunId: string | null
  riskLevelCode: string | null
  riskLevelLabel: string
  documents: ReviewDocumentModel[]
  missingItems: MissingItemDto[]
  runs: ReviewRunModel[]
  findings: ReviewFindingModel[]
  decisions: ReviewDecisionModel[]
  reportDocument: GeneratedReportDto | null
  generatedReports: GeneratedReportDto[]
  correctionRequests: CorrectionRequestDto[]
  versionDiffs: ReviewVersionDiffModel[]
  unresolvedFindingCount: number
}
