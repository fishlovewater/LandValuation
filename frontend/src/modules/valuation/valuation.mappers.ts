import type { CaseSummary } from '../../types/case'
import type {
  BenchmarkLandModel,
  BenchmarkLandResponseDto,
  CalculationModel,
  CalculationResponseDto,
  CaseResponseDto,
  DocumentArtifactModel,
  DocumentResponseDto,
  F03DraftModel,
  F03DraftResponseDto,
  F03DraftUpdateDto,
  F03EditableValues,
  FormalValidationModel,
  FormalValidationResponseDto,
  FormalReportModel,
  FormalReportResponseDto,
  FormResponseDto,
  ReportArtifactModel,
  ReportProgressResponseDto,
  ReportResponseDto,
  SourceMarker,
  SubmissionModel,
  SubmitForReviewResultDto,
  ValidationFindingModel,
  ValidationResponseDto,
  ValidationRunModel,
  ValuationCaseModel,
  ValuationFormModel,
} from './valuation.types'

const automaticSource: SourceMarker = {
  kind: 'automatic',
  label: '來源：案件原始資料',
}

const confirmedSource = (documentId: string | null): SourceMarker => ({
  kind: 'human-confirmed',
  label: '來源：人工確認欄位',
  documentId,
})

const calculatedSource: SourceMarker = {
  kind: 'calculated',
  label: '來源：系統計算',
}

function displayValidationValue(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === 'required') return '必填'
    if (normalized === 'true') return '是'
    if (normalized === 'false') return '否'
    return value
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number' || typeof value === 'bigint') {
    return String(value)
  }
  try {
    const serialized = JSON.stringify(value)
    return serialized === undefined ? String(value) : serialized
  } catch {
    return String(value)
  }
}

function formContentString(dto: FormResponseDto, key: string): string | null {
  const value = dto.form_content?.[key]
  return typeof value === 'string' && value.length > 0 ? value : null
}

export function mapCaseResponse(dto: CaseResponseDto): ValuationCaseModel {
  const summary: CaseSummary = {
    caseId: dto.case_id,
    caseNo: dto.case_no,
    name: dto.case_title,
    district: dto.district_code,
    status: dto.case_status,
    updatedAt: dto.updated_at,
    dueAt: dto.valuation_due_date,
  }

  return {
    ...summary,
    caseType: dto.case_type,
    requestingAgency: dto.requesting_agency,
    valuationBaseDate: dto.valuation_base_date,
    valuationDueDate: dto.valuation_due_date,
    cityCode: dto.city_code,
    districtCode: dto.district_code,
    landUseType: dto.land_use_type,
    source: automaticSource,
  }
}

export function mapFormResponse(dto: FormResponseDto): ValuationFormModel {
  return {
    formInstanceId: dto.form_instance_id,
    caseId: dto.case_id,
    formCode: dto.form_code,
    versionNo: dto.version_no,
    status: dto.form_status,
    preparedDate: dto.prepared_date,
    sourceDocumentId: dto.source_document_id,
    outputDocumentId: dto.output_document_id,
    reportType: formContentString(dto, 'report_type'),
    reportId: formContentString(dto, 'report_id'),
    source: confirmedSource(dto.source_document_id),
  }
}

export function mapDocumentResponse(dto: DocumentResponseDto): DocumentArtifactModel {
  return {
    documentId: dto.document_id,
    documentGroupId: dto.document_group_id,
    caseId: dto.case_id,
    documentType: dto.document_type,
    filename: dto.original_filename,
    mimeType: dto.mime_type,
    versionNo: dto.version_no,
    fileSizeBytes: dto.file_size_bytes,
    uploadedAt: dto.uploaded_at,
    isActive: dto.is_active,
  }
}

export function mapBenchmarkLandResponse(dto: BenchmarkLandResponseDto): BenchmarkLandModel {
  return {
    benchmarkLandId: dto.benchmark_land_id,
    caseId: dto.case_id,
    parcelId: dto.parcel_id,
    benchmarkLandNo: dto.benchmark_land_no,
    priceZoneNo: dto.price_zone_no,
    landConsolidationSerial: dto.land_consolidation_serial,
    latitude: dto.latitude,
    longitude: dto.longitude,
    isActive: dto.is_active,
    updatedAt: dto.updated_at,
  }
}

export function mapF03DraftResponse(
  dto: F03DraftResponseDto,
  sourceDocumentId: string | null = null,
  discoveredFormInstanceId?: string,
): F03DraftModel {
  const editable: F03EditableValues = {
    benchmarkLandId: dto.benchmark_land_id,
    comparisonAnalysisId: dto.comparison_analysis_id,
    valuationBaseDate: dto.valuation_base_date,
    comparisonPrice: dto.comparison_price,
    comparisonWeight: dto.comparison_weight,
    incomePrice: dto.income_price,
    incomeWeight: dto.income_weight,
    marketPeriodStart: dto.market_period_start,
    marketPeriodEnd: dto.market_period_end,
    marketCondition: dto.market_condition,
    selectionScopeReason: dto.selection_scope_reason,
    decisionReason: dto.decision_reason,
  }

  return {
    benchmarkValuationId: dto.benchmark_valuation_id,
    caseId: dto.case_id,
    formInstanceId: dto.form_instance_id ?? discoveredFormInstanceId ?? '',
    editable,
    benchmarkLandPrice: dto.benchmark_land_price,
    versionNo: dto.version_no,
    valuationStatus: dto.valuation_status,
    source: confirmedSource(sourceDocumentId),
    updatedAt: dto.updated_at,
  }
}

export function mapCalculationResponse(dto: CalculationResponseDto): CalculationModel {
  return {
    calculationId: dto.calculation_id,
    caseId: dto.case_id,
    formInstanceId: dto.form_instance_id,
    benchmarkValuationId: dto.benchmark_valuation_id,
    formulaVersion: dto.formula_version,
    result: dto.result,
    currencyCode: dto.currency_code,
    calculatedAt: dto.calculated_at,
  }
}

export function mapValidationResponse(dto: ValidationResponseDto): ValidationRunModel {
  const findings: ValidationFindingModel[] = dto.findings.map((finding) => ({
    findingId: finding.finding_id,
    ruleCode: finding.rule_code,
    ruleVersion: finding.rule_version,
    fieldPath: finding.field_path,
    severity: finding.severity,
    actualValue: displayValidationValue(finding.actual_value),
    expectedValue: displayValidationValue(finding.expected_value),
    message: finding.message,
    createdAt: finding.created_at,
  }))

  return {
    validationRunId: dto.validation_run_id,
    caseId: dto.case_id,
    formInstanceId: dto.form_instance_id,
    runStatus: dto.run_status,
    passedCount: dto.passed_count,
    warningCount: dto.warning_count,
    failedCount: dto.failed_count,
    canGenerateReport: dto.can_generate_report,
    rulesetVersion: dto.ruleset_version,
    correctionHints: dto.correction_hints,
    findings,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
  }
}

export function mapFormalValidationResponse(dto: FormalValidationResponseDto): FormalValidationModel {
  return {
    validationRunId: dto.validation_run_id,
    caseId: dto.case_id,
    reportId: dto.report_id,
    runStatus: dto.run_status,
    passedCount: dto.passed_count,
    warningCount: dto.warning_count,
    failedCount: dto.failed_count,
    canGenerateFormalReport: dto.can_generate_formal_report,
    inputFingerprint: dto.input_fingerprint,
    findings: dto.findings.map((finding) => ({
      code: finding.code,
      severity: finding.severity,
      message: finding.message,
      fieldCode: finding.field_code,
    })),
    completedAt: dto.completed_at,
  }
}

export function mapFormalReportResponse(dto: FormalReportResponseDto): FormalReportModel {
  return {
    documentId: dto.document_id,
    caseId: dto.case_id,
    reportId: dto.report_id,
    validationRunId: dto.validation_run_id,
    filename: dto.filename,
    mimeType: dto.mime_type,
    versionNo: dto.version_no,
    fileSizeBytes: dto.file_size_bytes,
    downloadPath: dto.download_path,
  }
}

export function mapReportProgressResponse(dto: ReportProgressResponseDto): {
  reportId: string | null
  reportType: string
  versionNo: number | null
  completionRate: string
  blockingErrors: string[]
} {
  return {
    reportId: dto.report_id,
    reportType: dto.report_type,
    versionNo: dto.version_no,
    completionRate: dto.completion_rate,
    blockingErrors: dto.blocking_errors,
  }
}

export interface AuthoritativeF02Selection {
  form: ValuationFormModel | null
  completeReport: DocumentArtifactModel | null
  reportPackageId: string | null
}

export function selectAuthoritativeF02(
  forms: ValuationFormModel[],
  documents: DocumentArtifactModel[],
  reportProgress: ReportProgressResponseDto,
): AuthoritativeF02Selection {
  const resumableF02Forms = forms
    .filter(
      (form) =>
        form.formCode === 'F02' &&
        (form.status === 'CHECKED' || form.status === 'FINAL') &&
        form.reportType === 'REPORT_COMPARISON_COMMERCIAL',
    )
    .sort((left, right) => {
      const versionOrder = right.versionNo - left.versionNo
      if (versionOrder !== 0) return versionOrder
      return (right.status === 'FINAL' ? 1 : 0) - (left.status === 'FINAL' ? 1 : 0)
    })
  const progress = mapReportProgressResponse(reportProgress)

  const pairs = resumableF02Forms.flatMap((form): Array<{
    form: ValuationFormModel
    completeReport: DocumentArtifactModel | null
  }> => {
    if (
      !form.reportId ||
      !progress.reportId ||
      form.reportId !== progress.reportId ||
      progress.reportType !== form.reportType
    ) return []
    const completeReport = documents
      .filter(
        (document) =>
          document.isActive &&
          document.documentType === 'complete-valuation-report' &&
          document.documentId === form.outputDocumentId,
      )
      .sort((left, right) => right.versionNo - left.versionNo)[0]
    if (completeReport) return [{ form, completeReport }]
    if (form.status === 'CHECKED' && form.outputDocumentId === null) {
      return [{ form, completeReport: null }]
    }
    return []
  })

  const selected = pairs[0]
  if (selected) {
    return {
      form: selected.form,
      completeReport: selected.completeReport,
      reportPackageId: selected.form.reportId,
    }
  }

  return {
    form: null,
    completeReport: null,
    reportPackageId: null,
  }
}

export function mapReportResponse(dto: ReportResponseDto): ReportArtifactModel {
  return {
    documentId: dto.document_id,
    caseId: dto.case_id,
    formInstanceId: dto.form_instance_id,
    validationRunId: dto.validation_run_id,
    calculationId: dto.calculation_id,
    filename: dto.filename,
    mimeType: dto.mime_type,
    versionNo: dto.version_no,
    fileSizeBytes: dto.file_size_bytes,
  }
}

export function mapSubmitForReviewResult(dto: SubmitForReviewResultDto): SubmissionModel {
  return {
    submissionId: dto.submission_id,
    submissionNo: dto.submission_no,
    reviewId: dto.review_id,
    caseStatus: dto.case_status,
    submittedAt: dto.submitted_at,
  }
}

export function mapF03Update(values: F03EditableValues): F03DraftUpdateDto {
  return {
    benchmark_land_id: values.benchmarkLandId,
    comparison_analysis_id: values.comparisonAnalysisId,
    valuation_base_date: values.valuationBaseDate,
    comparison_price: values.comparisonPrice,
    comparison_weight: values.comparisonWeight,
    income_price: values.incomePrice,
    income_weight: values.incomeWeight,
    market_period_start: values.marketPeriodStart,
    market_period_end: values.marketPeriodEnd,
    market_condition: values.marketCondition,
    selection_scope_reason: values.selectionScopeReason,
    decision_reason: values.decisionReason,
  }
}

export function sourceForCalculatedValue(): SourceMarker {
  return calculatedSource
}
