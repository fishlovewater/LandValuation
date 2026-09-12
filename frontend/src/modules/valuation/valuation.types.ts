import { reactive } from 'vue'
import type { CaseIdentity, CaseSummary } from '../../types/case'

export type CaseStatus =
  | 'DRAFT'
  | 'PROCESSING'
  | 'REVIEWING'
  | 'CORRECTION'
  | 'COMPLETED'
  | 'ARCHIVED'
  | 'IN_REVIEW'
  | 'REVISION_REQUIRED'
  | 'REVIEW_COMPLETED'

export type FormCode = 'F01' | 'F02' | 'F03' | 'F04' | 'S01' | 'F02-RF'
export type FormStatus = 'DRAFT' | 'READY' | 'CHECKED' | 'FINAL' | 'VOID'
export type FindingSeverity = 'ERROR' | 'WARNING'
export type ValuationWorkspaceStage =
  | 'case'
  | 'documents'
  | 'ai-review'
  | 'data'
  | 'calculation'
  | 'report'

export interface CaseCreateDto {
  case_no: string
  case_title: string
  case_type: string
  requesting_agency?: string | null
  valuation_base_date: string
  valuation_due_date?: string | null
  city_code: string
  district_code: string
  land_use_type?: string | null
}

export interface CaseResponseDto {
  case_id: string
  case_no: string
  case_title: string
  case_type: string
  requesting_agency: string | null
  valuation_base_date: string
  valuation_due_date: string | null
  city_code: string
  district_code: string
  land_use_type: string | null
  case_status: CaseStatus
  basic_info_confirmed_at?: string | null
  basic_info_confirmed_by_user_id?: string | null
  last_workspace_stage?: ValuationWorkspaceStage
  created_by_user_id: string | null
  updated_by_user_id: string | null
  created_at: string
  updated_at: string
}

export interface CaseWorkspaceUpdateDto {
  confirm_basic_info?: boolean
  last_workspace_stage?: ValuationWorkspaceStage
}

export interface ParcelResponseDto {
  parcel_id: string
  case_id: string
  district_code: string
  section_name: string
  subsection_name: string
  land_no: string
  area_sqm: string
  land_use_zone: string | null
  designated_use: string | null
  ownership_numerator: string | null
  ownership_denominator: string | null
  source_document_id: string | null
  created_at: string
  updated_at: string
}

export interface ParcelCreateDto {
  district_code: string
  section_name: string
  subsection_name?: string
  land_no: string
  area_sqm: string
  land_use_zone?: string | null
  designated_use?: string | null
  ownership_numerator?: string | null
  ownership_denominator?: string | null
  source_document_id?: string | null
}

export type ParcelUpdateDto = Partial<ParcelCreateDto>

export type ParcelImportStatus = 'READY' | 'NEEDS_CONFIRMATION' | 'DUPLICATE'

export interface ParcelImportCandidateDto {
  source_location: string
  source_serial: string | null
  source_owner_name: string | null
  district_code: string | null
  district_name: string | null
  section_name: string | null
  subsection_name: string
  land_no: string | null
  area_sqm: string | null
  land_use_zone: string | null
  designated_use: string | null
  ownership_numerator: string | null
  ownership_denominator: string | null
  status: ParcelImportStatus
  errors: string[]
  warnings: string[]
  existing_parcel_id: string | null
}

export interface ParcelImportPreviewDto {
  document_id: string
  filename: string
  layout: 'OFFICIAL_TRANSPOSED' | 'ROW_TABLE' | string
  candidates: ParcelImportCandidateDto[]
  ready_count: number
  needs_confirmation_count: number
  duplicate_count: number
}

export interface ParcelImportRowDto {
  source_location: string
  source_serial?: string | null
  district_code: string
  section_name: string
  subsection_name?: string
  land_no: string
  area_sqm: string
  land_use_zone?: string | null
  designated_use?: string | null
  ownership_numerator?: string | null
  ownership_denominator?: string | null
}

export interface ParcelBatchImportRequestDto {
  rows: ParcelImportRowDto[]
}

export interface ParcelBatchImportResponseDto {
  created: ParcelResponseDto[]
  skipped_duplicate_count: number
  skipped_duplicate_locations: string[]
}

export interface FormRequirementResponseDto {
  form_type: FormCode
  form_name: string
  required_fields: string[]
  required_documents: string[]
  optional_documents: string[]
  calculated_fields: string[]
}

export interface FormResponseDto {
  form_instance_id: string
  case_id: string
  form_code: FormCode
  version_no: number
  form_status: FormStatus
  form_content: Record<string, unknown>
  prepared_date: string | null
  source_document_id: string | null
  output_document_id: string | null
  created_by_user_id: string | null
  updated_by_user_id: string | null
  created_at: string
  updated_at: string
}

export interface CaseBootstrapResponseDto {
  case: CaseResponseDto
  initial_form: FormResponseDto
}

export interface FormCreateDto {
  form_code: FormCode
  prepared_date?: string | null
  source_document_id?: string | null
  form_content?: Record<string, never>
}

export type DocumentCategory =
  | 'original'
  | 'parcel-factor-list'
  | 'cadastral-map'
  | 'land-register'
  | 'photos'
  | 'attachments'
  | 'map-section-sketch'
  | 'map-zoning'
  | 'map-land-value-section'
  | 'complete-valuation-report'

export interface DocumentResponseDto {
  document_id: string
  document_group_id: string
  case_id: string
  document_type: string
  original_filename: string
  mime_type: string
  bucket_name: string
  object_key: string
  checksum_sha256: string
  file_size_bytes: number
  storage_etag: string | null
  version_no: number
  uploaded_by_user_id: string | null
  uploaded_at: string
  is_active: boolean
}

export interface ReportProgressSectionResponseDto {
  code: string
  name: string
  status: string
  form_instance_id: string | null
  document_type: string | null
}

export interface ReportProgressResponseDto {
  report_id: string | null
  report_type: string
  version_no: number | null
  completion_rate: string
  sections: ReportProgressSectionResponseDto[]
  blocking_errors: string[]
}

export interface ReportPackageCreateDto {
  report_type: 'REPORT_COMPARISON_COMMERCIAL'
  prepared_date?: string | null
}

export interface ReportPackageResponseDto {
  report_id: string
  case_id: string
  report_type: 'REPORT_COMPARISON_COMMERCIAL'
  version_no: number
  prepared_date: string | null
  components: Array<{
    code: string
    form_instance_id: string
    form_status: FormStatus
  }>
  created_at: string
  updated_at: string
}

export type ReportPageCode = 'S01' | 'F02-RF' | 'F02'

export interface ReportPageResponseDto {
  report_id: string
  form_instance_id: string
  case_id: string
  page_code: ReportPageCode
  version_no: number
  form_status: FormStatus
  page_schema_version: string
  context: Record<string, unknown>
  warnings: string[]
  data: Record<string, unknown>
}

export interface AutomatedFormGuidanceDto {
  form_code: string
  form_instance_id: string | null
  required_fields: string[]
  confirmed_or_applied_fields: string[]
  pending_confirmation_fields: string[]
  missing_required_fields: string[]
  calculation_ready: boolean
  next_action: string
  fill_endpoint: string | null
  calculate_endpoint: string | null
  validate_endpoint: string | null
}

export interface AutomatedWorkflowResponseDto {
  status: string
  case: CaseResponseDto
  parcel_ids: string[]
  benchmark_land_ids: string[]
  f03_form_instance_id: string
  report_id: string | null
  documents: unknown[]
  candidates: ExtractedFieldResponseDto[]
  pending_candidate_count: number
  blank_fields_remain: boolean
  missing_items: string[]
  warnings: string[]
  ignored_duplicate_files: string[]
  next_action: string
  draft_pages_1_3_url: string | null
  draft_pages_1_6_url: string | null
  form_guidance: AutomatedFormGuidanceDto[]
  automatic_pdf_generation_enabled: boolean
  automatic_confirmation_export_enabled: boolean
  confirmation_export: {
    document_id: string
    filename: string
    download_path: string
  } | null
  manual_fields_saved: string[]
  manual_fields_ignored: string[]
  manual_field_errors: Record<string, string>
  manual_field_values: Record<string, Record<string, unknown>>
}

export interface ManualFieldValuesRequestDto {
  values: Record<string, Record<string, unknown>>
}

export interface ComparisonSetupTargetDto {
  transaction_no: string
  transaction_date: string
  transaction_total_price: string
  normal_land_unit_price: string
  weight: string
  source_notes: string
  subject_address?: string | null
  land_area_sqm?: string | null
}

export interface ComparisonSetupCreateDto {
  report_id: string
  benchmark_land_id: string
  targets: ComparisonSetupTargetDto[]
  notes?: string | null
}

export interface ComparisonSetupApplyDto {
  report_id: string
  comparison_analysis_id: string
}

export interface ComparisonSetupContextDto {
  parcels: Array<{ parcel_id: string; label: string }>
  benchmark_lands: Array<{ benchmark_land_id: string; label: string }>
  analyses: Array<{
    comparison_analysis_id: string
    benchmark_land_id: string
    analysis_status: string
    label: string
  }>
}

export interface ComparisonSetupResponseDto {
  comparison_analysis_id: string
  benchmark_land_id: string
  report_id: string
  targets: Array<{
    comparison_target_id: string
    transaction_id: string
    transaction_no: string
    transaction_date: string
    normal_land_unit_price: string
    weight: string
  }>
}

export type ExtractionCandidateDecision = 'CONFIRM' | 'REJECT'

export interface ExtractedFieldResponseDto {
  extracted_field_id: string
  extraction_id: string
  document_id: string
  form_code: string
  field_name: string
  /** Canonical Chinese display name resolved from the six-form field catalogue. */
  field_label?: string
  /** Evidence and input guidance resolved from the canonical field catalogue. */
  field_guidance?: string
  extracted_value: unknown
  confidence: string
  source_page: number | null
  source_text: string | null
  analysis_provider: string
  model_id: string | null
  prompt_version: string | null
  field_status: string
  confirmed_value: unknown | null
  confirmed_by_user_id: string | null
  confirmed_at: string | null
  applied_form_instance_id: string | null
  applied_at: string | null
}

export interface ExtractionResponseDto {
  extraction_id: string
  case_id: string
  document_id: string
  provider: string
  extraction_status: string
  page_count: number | null
  extracted_text: string | null
  error_message: string | null
  started_at: string
  completed_at: string | null
  candidates: ExtractedFieldResponseDto[]
}

export interface AutomatedCandidateConfirmationDto {
  document_id: string
  extracted_field_id: string
  decision: ExtractionCandidateDecision
  corrected_value?: unknown
}

export interface AutomatedConfirmRequestDto {
  confirmations: AutomatedCandidateConfirmationDto[]
  confirm_apply: true
}

export interface ValuationReviewHandoffDto {
  case_id: string
  case_status: string
  display_status: string
  review_id: string | null
  review_status: string | null
  latest_submission: {
    submission_id: string
    submission_no: number
    submitted_at: string
  } | null
  correction: {
    correction_request_id: string
    request_no: number
    status: string
    due_at: string
    message: string
    items: Array<{
      finding_code: string
      severity: string
      document_id: string | null
      page_number: number | null
      issue_summary: string
      requested_correction: string
    }>
  } | null
  missing_items: Array<{
    item_code: string
    item_name: string
    document_type: string | null
    severity: string
    status: string
    reason: string | null
    due_at: string | null
    notification_status: string | null
    notified_at: string | null
  }>
}

export interface FormalCalculationRequestDto {
  confirm_calculation: true
}

export interface FormalCalculationResponseDto {
  case_id: string
  report_id: string
  comparison_analysis_id: string | null
  rule_version_id: string | null
  formula_code: string
  rounding_code: string
  benchmark_comparison_price: string | null
  targets: Array<Record<string, unknown>>
  input_fingerprint: string
  calculated_at: string
}

export type FormalValidationFindingSeverity = 'ERROR' | 'WARNING'

export interface FormalValidationFindingResponseDto {
  code: string
  severity: FormalValidationFindingSeverity
  message: string
  field_code: string | null
}

export interface FormalValidationResponseDto {
  validation_run_id: string
  case_id: string
  report_id: string
  run_status: string
  passed_count: number
  warning_count: number
  failed_count: number
  can_generate_formal_report: boolean
  input_fingerprint: string | null
  findings: FormalValidationFindingResponseDto[]
  completed_at: string
}

export interface FormalReportRequestDto {
  confirm_generate: true
  acknowledged_warning_codes: string[]
}

export interface FormalReportResponseDto {
  document_id: string
  case_id: string
  report_id: string
  validation_run_id: string
  filename: string
  mime_type: 'application/pdf'
  version_no: number
  bucket_name: string
  object_key: string
  checksum_sha256: string
  file_size_bytes: number
  download_path: string
  request_id: string | null
}

export interface FormalWorkflowStatusResponseDto {
  validation: FormalValidationResponseDto | null
  report: FormalReportResponseDto | null
  requires_revalidation_for_submission: boolean
}

export interface F03DraftResponseDto {
  benchmark_valuation_id: string
  case_id: string
  benchmark_land_id: string
  comparison_analysis_id: string | null
  form_instance_id: string | null
  valuation_base_date: string
  comparison_price: string | null
  comparison_weight: string
  income_price: string | null
  income_weight: string
  benchmark_land_price: string | null
  market_period_start: string | null
  market_period_end: string | null
  market_condition: string | null
  selection_scope_reason: string | null
  decision_reason: string | null
  version_no: number
  valuation_status: string
  created_at: string
  updated_at: string
}

export interface F03DraftUpdateDto {
  benchmark_land_id?: string | null
  comparison_analysis_id?: string | null
  valuation_base_date?: string | null
  comparison_price?: string | null
  comparison_weight?: string | null
  income_price?: string | null
  income_weight?: string | null
  market_period_start?: string | null
  market_period_end?: string | null
  market_condition?: string | null
  selection_scope_reason?: string | null
  decision_reason?: string | null
}

export interface BenchmarkLandResponseDto {
  benchmark_land_id: string
  case_id: string
  parcel_id: string
  benchmark_land_no: string
  price_zone_no: string
  land_consolidation_serial: string | null
  latitude: string | null
  longitude: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface BenchmarkLandCreateDto {
  parcel_id: string
  benchmark_land_no: string
  price_zone_no: string
  land_consolidation_serial?: string | null
  latitude?: string | null
  longitude?: string | null
}

export interface CalculationRequestDto {
  form_instance_id: string
}

export interface CalculationResponseDto {
  calculation_id: string
  case_id: string
  form_instance_id: string
  benchmark_valuation_id: string
  formula_version: string
  result: string
  currency_code: string
  calculation_snapshot: Record<string, unknown>
  request_id: string | null
  calculated_at: string
}

export interface ValidationRequestDto {
  form_instance_id: string
}

export interface ValidationFindingResponseDto {
  finding_id: string
  rule_code: string
  rule_version: string
  field_path: string | null
  severity: FindingSeverity
  actual_value?: unknown
  expected_value?: unknown
  message: string
  request_id: string | null
  created_at: string
}

export interface ValidationResponseDto {
  validation_run_id: string
  case_id: string
  form_instance_id: string
  run_status: string
  passed_count: number
  warning_count: number
  failed_count: number
  can_generate_report: boolean
  ruleset_version: string
  correction_hints: string[]
  findings: ValidationFindingResponseDto[]
  request_id: string | null
  started_at: string
  completed_at: string | null
}

export interface ReportRequestDto {
  form_instance_id: string
}

export interface ReportResponseDto {
  document_id: string
  case_id: string
  form_instance_id: string
  validation_run_id: string
  calculation_id: string
  filename: string
  mime_type: string
  version_no: number
  bucket_name: string
  object_key: string
  checksum_sha256: string
  file_size_bytes: number
  download_path: string
  request_id: string | null
}

export interface SubmitForReviewCommandDto {
  request_id: string
  expected_case_version: number
  source_validation_run_id: string
  source_report_document_id: string
}

export interface SubmitForReviewResultDto {
  submission_id: string
  submission_no: number
  review_id: string
  case_status: string
  submitted_at: string
}

export type ValuationValueKind = 'automatic' | 'human-confirmed' | 'calculated'

export interface SourceMarker {
  kind: ValuationValueKind
  label: string
  documentId?: string | null
}

export interface ValuationCaseModel extends CaseSummary {
  caseType: string
  requestingAgency: string | null
  valuationBaseDate: string
  valuationDueDate: string | null
  cityCode: string
  districtCode: string
  landUseType: string | null
  basicInfoConfirmedAt: string | null
  basicInfoConfirmedByUserId: string | null
  lastWorkspaceStage: ValuationWorkspaceStage
  source: SourceMarker
}

export interface ValuationFormModel {
  formInstanceId: string
  caseId: string
  formCode: FormCode
  versionNo: number
  status: FormStatus
  preparedDate: string | null
  sourceDocumentId: string | null
  outputDocumentId: string | null
  reportType: string | null
  reportId: string | null
  source: SourceMarker
}

export interface BenchmarkLandModel {
  benchmarkLandId: string
  caseId: string
  parcelId: string
  benchmarkLandNo: string
  priceZoneNo: string
  landConsolidationSerial: string | null
  latitude: string | null
  longitude: string | null
  isActive: boolean
  updatedAt: string
}

export interface F03EditableValues {
  benchmarkLandId: string | null
  comparisonAnalysisId: string | null
  valuationBaseDate: string | null
  comparisonPrice: string | null
  comparisonWeight: string | null
  incomePrice: string | null
  incomeWeight: string | null
  marketPeriodStart: string | null
  marketPeriodEnd: string | null
  marketCondition: string | null
  selectionScopeReason: string | null
  decisionReason: string | null
}

export interface F03DraftModel {
  benchmarkValuationId: string
  caseId: string
  formInstanceId: string
  editable: F03EditableValues
  benchmarkLandPrice: string | null
  versionNo: number
  valuationStatus: string
  source: SourceMarker
  updatedAt: string
}

export interface CalculationModel {
  calculationId: string
  caseId: string
  formInstanceId: string
  benchmarkValuationId: string
  formulaVersion: string
  result: string
  currencyCode: string
  calculatedAt: string
}

export interface ValidationFindingModel {
  findingId: string
  ruleCode: string
  ruleVersion: string
  fieldPath: string | null
  severity: FindingSeverity
  actualValue: string | null
  expectedValue: string | null
  message: string
  createdAt: string
}

export interface ValidationRunModel {
  validationRunId: string
  caseId: string
  formInstanceId: string
  runStatus: string
  passedCount: number
  warningCount: number
  failedCount: number
  canGenerateReport: boolean
  rulesetVersion: string
  correctionHints: string[]
  findings: ValidationFindingModel[]
  startedAt: string
  completedAt: string | null
}

export interface ReportArtifactModel {
  documentId: string
  caseId: string
  formInstanceId: string
  validationRunId: string
  calculationId: string
  filename: string
  mimeType: string
  versionNo: number
  fileSizeBytes: number
}

export interface DocumentArtifactModel {
  documentId: string
  documentGroupId: string
  caseId: string
  documentType: string
  filename: string
  mimeType: string
  versionNo: number
  fileSizeBytes: number
  uploadedAt: string
  isActive: boolean
}

export interface FormalValidationFindingModel {
  code: string
  severity: FormalValidationFindingSeverity
  message: string
  fieldCode: string | null
}

export interface FormalValidationModel {
  validationRunId: string
  caseId: string
  reportId: string
  runStatus: string
  passedCount: number
  warningCount: number
  failedCount: number
  canGenerateFormalReport: boolean
  inputFingerprint: string | null
  findings: FormalValidationFindingModel[]
  completedAt: string
}

export interface FormalReportModel {
  documentId: string
  caseId: string
  reportId: string
  validationRunId: string
  filename: string
  mimeType: 'application/pdf'
  versionNo: number
  fileSizeBytes: number
  downloadPath: string
}

export interface SubmissionModel {
  submissionId: string
  submissionNo: number
  reviewId: string
  caseStatus: string
  submittedAt: string
}

export interface ValuationFlowState {
  case: ValuationCaseModel | null
  forms: ValuationFormModel[]
  benchmarks: BenchmarkLandModel[]
  f03: F03DraftModel | null
  documents: DocumentArtifactModel[]
  authoritativeF02: ValuationFormModel | null
  completeReport: DocumentArtifactModel | null
  reportPackageId: string | null
  calculation: CalculationModel | null
  validation: ValidationRunModel | null
  report: ReportArtifactModel | null
  formalValidation: FormalValidationModel | null
  formalReport: FormalReportModel | null
  submission: SubmissionModel | null
}

function initialFlowState(): ValuationFlowState {
  return {
    case: null,
    forms: [],
    benchmarks: [],
    f03: null,
    documents: [],
    authoritativeF02: null,
    completeReport: null,
    reportPackageId: null,
    calculation: null,
    validation: null,
    report: null,
    formalValidation: null,
    formalReport: null,
    submission: null,
  }
}

export const valuationFlowState = reactive<ValuationFlowState>(initialFlowState())

export function resetValuationFlow(): void {
  Object.assign(valuationFlowState, initialFlowState())
}

export type ValuationCaseIdentity = CaseIdentity
