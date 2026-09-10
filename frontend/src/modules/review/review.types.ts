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

export interface WorkbenchCaseDto {
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
  urgency_level: 'OVERDUE' | 'URGENT' | 'DUE_SOON' | 'NORMAL' | 'NOT_SET'
  remaining_days: number | null
  correction_round: number
  latest_correction_status: string | null
}

export interface WorkbenchCaseListDto {
  items: WorkbenchCaseDto[]
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

export interface ReviewReadDto {
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

export interface WorkbenchDocumentDto {
  document_id: string
  document_type: string
  original_filename: string
  mime_type: string
  version_no: number
  is_active: boolean
  uploaded_at: string
}

export interface ValidationRunDto {
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
  input_snapshot: Record<string, unknown>
  model_id: string | null
  prompt_version: string | null
  error_code: string | null
  error_message: string | null
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
  reported_adjustment_rate: string | number | null
  system_adjustment_rate: string | number | null
  comparison_result: Record<string, unknown>
  recommended_action: Record<string, unknown>
  ai_reasoning_summary: string | null
  ai_confidence: string | number | null
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
  risk_score: string | number | null
  summary: string
  high_count: number
  medium_count: number
  low_count: number
  missing_item_count: number
  risk_reasons: unknown[]
  generated_at: string
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
  items: unknown[]
}

export interface WorkbenchDetailDto {
  case: WorkbenchCaseSummaryDto
  review: ReviewReadDto
  documents: WorkbenchDocumentDto[]
  missing_items: MissingItemDto[]
  runs: ValidationRunDto[]
  findings: FindingDto[]
  risk_summary: RiskSummaryDto | null
  decisions: DecisionDto[]
  version_diffs: unknown[]
  report_document: GeneratedReportDto | null
  generated_reports: GeneratedReportDto[]
  correction_requests: CorrectionRequestDto[]
}

export interface CompletenessDto {
  ready: boolean
  review_status: string
  missing_item_count: number
  blocked_rule_codes: string[]
  items: MissingItemDto[]
}

export interface WorkbenchStartDto {
  outcome: 'BLOCKED' | 'COMPLETED'
  completeness: CompletenessDto
  run: ValidationRunDto | null
  findings: FindingDto[]
  risk_summary: RiskSummaryDto | null
}

export interface ReviewSummary {
  statusCounts: Record<string, number>
  totalCount: number
  highRiskCount: number
  openFindingCount: number
  missingItemCount: number
}

export interface ReviewCaseSummary {
  reviewId: string
  caseId: string
  caseNo: string
  title: string
  district?: string
  status: string
  statusLabel: string
  riskLevel?: string
  riskLabel: string
  missingItemCount: number
  highCount: number
  mediumCount: number
  lowCount: number
  receivedAt?: string
  dueAt?: string
  reviewerName?: string
  latestRunId?: string
  urgencyLevel: string
  remainingDays?: number
  correctionRound: number
  raw: { status: string; riskLevel?: string }
}

export interface ReviewDocument {
  documentId: string
  documentType: string
  filename: string
  mimeType: string
  versionNo: number
  isActive: boolean
  uploadedAt: string
  contentAvailable: boolean
}

export interface MissingItem {
  missingItemId: string
  itemCode: string
  itemName: string
  severity: string
  status: string
  reason?: string
}

export interface ReviewRun {
  runId: string
  runNo?: number
  status: string
  passedCount: number
  warningCount: number
  failedCount: number
  startedAt: string
  completedAt?: string
}

export interface FindingViewModel {
  findingId: string
  reviewId: string
  runId?: string
  findingCode: string
  findingType: string
  severity: string
  severityLabel: string
  title: string
  description: string
  status: string
  documentId?: string
  documentVersion?: number
  pageNumber?: number
  fieldPath?: string
  reportedText?: string
  reportedValue?: string
  reportedGrade?: string
  systemGrade?: string
  reportedAdjustmentRate?: string
  systemAdjustmentRate?: string
  aiReasoningSummary?: string
  aiConfidence?: string
  aiStatus: string
}

export interface ReviewRiskSummary {
  riskSummaryId: string
  reviewId: string
  runId?: string
  riskLevel: string
  riskLabel: string
  riskScore?: string
  summary: string
  highCount: number
  mediumCount: number
  lowCount: number
  missingItemCount: number
  generatedAt: string
}

export interface ReviewCaseDetail extends ReviewCaseSummary {
  valuationBaseDate: string
  caseStatus: string
  documents: ReviewDocument[]
  missingItems: MissingItem[]
  runs: ReviewRun[]
  findings: FindingViewModel[]
  riskSummary?: ReviewRiskSummary
  decisions: DecisionDto[]
  reports: GeneratedReportDto[]
  correctionRequests: CorrectionRequestDto[]
}

export interface ReviewCaseQuery {
  q?: string
  status?: string
  riskLevel?: string
  statusGroup?: 'pending' | 'in_progress' | 'needs_input' | 'completed' | 'risk'
  limit?: number
  offset?: number
}

export interface ReviewCasePage {
  items: ReviewCaseSummary[]
  total: number
  limit: number
  offset: number
}

export interface ReviewStartResult {
  outcome: 'BLOCKED' | 'COMPLETED'
  missingItems: MissingItem[]
  run?: ReviewRun
  findings: FindingViewModel[]
  riskSummary?: ReviewRiskSummary
}
