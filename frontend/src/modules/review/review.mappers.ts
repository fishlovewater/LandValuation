import type {
  DecisionDto,
  FindingDto,
  GeneratedReportDto,
  ReviewDecisionModel,
  ReviewDetailModel,
  ReviewDocumentModel,
  ReviewFindingModel,
  ReviewQueueItemModel,
  ReviewReferenceModel,
  ReviewRunModel,
  ReviewSummaryModel,
  ReviewVersionDiffModel,
  RiskSummaryDto,
  WorkbenchCaseDetailDto,
  WorkbenchCaseListItemDto,
  WorkbenchSummaryDto,
} from './review.types'
import { decisionLabel as sharedDecisionLabel, statusLabel as sharedStatusLabel } from '../../utils/enumLabels'

const STATUS_LABELS: Readonly<Record<string, string>> = {
  RECEIVED: '已收件',
  PREPROCESSING: '前處理中',
  PENDING_MATERIALS: '待補資料',
  READY_FOR_REVIEW: '待審查',
  ANALYZING: '分析中',
  REVIEW_REQUIRED: '需審查',
  RETURNED_FOR_REVISION: '退回補正',
  SUPPLEMENT_REQUIRED: '待補件',
  EXPERT_REVIEW: '專家審查',
  APPROVED: '已核准',
  REVIEW_COMPLETED: '審查完成',
  COMPLETED: '已完成',
  PROCESSING: '處理中',
  IN_REVIEW: '審查中',
  CORRECTION: '補正中',
  REVISION_REQUIRED: '需補正',
  DRAFT: '草稿',
  ARCHIVED: '已封存',
  READY: '可執行',
  BLOCKED: '受阻',
}

const REVIEW_TYPE_LABELS: Readonly<Record<string, string>> = {
  SMART_REVIEW: '智慧審查',
  MANUAL_REVIEW: '人工審查',
}

const RISK_LABELS: Readonly<Record<string, string>> = {
  LOW: '低風險',
  MEDIUM: '中風險',
  HIGH: '高風險',
  CRITICAL: '極高風險',
}

const RUN_STATUS_LABELS: Readonly<Record<string, string>> = {
  READY: '可執行',
  BLOCKED: '受阻',
  RUNNING: '執行中',
  COMPLETED: '已完成',
  FAILED: '執行失敗',
}

const FINDING_STATUS_LABELS: Readonly<Record<string, string>> = {
  OPEN: '待處理',
  REQUIRES_SUPPLEMENT: '待補件',
  EXPERT_REVIEW: '專家審查',
  ACCEPTED: '已接受',
  PARTIALLY_ACCEPTED: '部分接受',
  REJECTED: '已駁回',
  CONFIRMED_ISSUE: '已確認問題',
  DISMISSED_FALSE_POSITIVE: '已排除誤報',
}

const URGENCY_LABELS: Readonly<Record<string, string>> = {
  OVERDUE: '已逾期',
  URGENT: '緊急',
  DUE_SOON: '即將到期',
  NORMAL: '一般',
  NOT_SET: '未設定',
}

const STATUS_GROUP_LABELS: Readonly<Record<string, string>> = {
  PENDING: '待處理案件',
  IN_PROGRESS: '處理中案件',
  NEEDS_INPUT: '待補資料案件',
  COMPLETED: '已完成案件',
  RISK: '高風險案件',
}

const DOCUMENT_TYPE_LABELS: Readonly<Record<string, string>> = {
  ORIGINAL: '原始查估文件',
  'LAND-REGISTER': '土地登記謄本',
  'CADASTRAL-MAP': '地籍圖',
  PHOTOS: '現場照片',
  ATTACHMENTS: '附件',
  'MAP-SECTION-SKETCH': '地段圖',
  'MAP-ZONING': '使用分區圖',
  'MAP-LAND-VALUE-SECTION': '公告土地現值圖',
  'COMPLETE-VALUATION-REPORT': '完整送審 PDF',
  'REVIEW-REPORT': '審查報告',
  'CORRECTION-REQUEST': '修正通知',
}

const MIME_TYPE_LABELS: Readonly<Record<string, string>> = {
  'APPLICATION/PDF': 'PDF 文件',
  'IMAGE/JPEG': 'JPEG 圖片',
  'IMAGE/PNG': 'PNG 圖片',
  'APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.WORDPROCESSINGML.DOCUMENT': 'Word 文件',
  'APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.SPREADSHEETML.SHEET': 'Excel 文件',
}

const FINDING_CODE_LABELS: Readonly<Record<string, string>> = {
  ADJUSTMENT_RATE: '調整率',
  GRADE_MISMATCH: '等級不一致',
  REQUIRED_FIELD_MISSING: '必要欄位缺漏',
}

const FINDING_TYPE_LABELS: Readonly<Record<string, string>> = {
  RULE: '規則檢核',
  AI: '智慧分析',
  COMPLETENESS: '完整性檢核',
}

const FIELD_PATH_LABELS: Readonly<Record<string, string>> = {
  'COMPARISON.ADJUSTMENT_RATE': '調整率',
  'COMPARISON.GRADE': '比較等級',
  'COMPARISON.UNIT_PRICE': '比較單價',
}

const FIELD_PATH_SUFFIX_LABELS: Readonly<Record<string, string>> = {
  ADJUSTMENT_RATE: '調整率',
  GRADE: '比較等級',
  UNIT_PRICE: '比較單價',
  COMPARISON_PRICE: '比較法價格',
  VALUATION_BASE_DATE: '估價基準日',
  BENCHMARK_LAND_ID: '比準地',
}

const MISSING_ITEM_STATUS_LABELS: Readonly<Record<string, string>> = {
  OPEN: '待補',
  RECEIVED: '已收到',
  VERIFIED: '已確認',
  CLOSED: '已結案',
}

const CORRECTION_STATUS_LABELS: Readonly<Record<string, string>> = {
  DRAFT: '草稿',
  SENT: '已送出',
  ACKNOWLEDGED: '估價端已收到',
  RESUBMITTED: '已重新送審',
  RECHECKING: '重新檢核中',
  RECHECKED: '已重新檢核',
  CLOSED: '已結案',
}

const VERIFICATION_STATUS_LABELS: Readonly<Record<string, string>> = {
  EXTRACTED: '已辨識，待確認',
  NEEDS_CONFIRMATION: '待人工確認',
  CONFIRMED: '已人工確認',
  APPLIED: '已確認並套用',
  VERIFIED: '已確認',
  REJECTED: '未採用',
}

function normalized(value: string | null | undefined): string {
  return value?.trim().toUpperCase() ?? ''
}

function label(
  value: string | null | undefined,
  labels: Readonly<Record<string, string>>,
  fallback: string,
): string {
  return labels[normalized(value)] ?? fallback
}

export function reviewStatusLabel(value: string | null | undefined): string {
  return STATUS_LABELS[normalized(value)] ?? sharedStatusLabel(value)
}

export function reviewTypeLabel(value: string | null | undefined): string {
  return label(value, REVIEW_TYPE_LABELS, '其他審查類型')
}

export function riskLevelLabel(value: string | null | undefined): string {
  return label(value, RISK_LABELS, '未標示風險')
}

export function runStatusLabel(value: string | null | undefined): string {
  return label(value, RUN_STATUS_LABELS, '未知執行狀態')
}

export function findingStatusLabel(value: string | null | undefined): string {
  return label(value, FINDING_STATUS_LABELS, '未定義疑點狀態')
}

export const decisionLabel = sharedDecisionLabel

export function urgencyLabel(value: string | null | undefined): string {
  return label(value, URGENCY_LABELS, '未設定')
}

export function statusGroupLabel(value: string | null | undefined): string {
  return label(value, STATUS_GROUP_LABELS, '其他案件群組')
}

export function documentTypeLabel(value: string | null | undefined): string {
  return label(value, DOCUMENT_TYPE_LABELS, '其他文件')
}

export function mimeTypeLabel(value: string | null | undefined): string {
  return label(value, MIME_TYPE_LABELS, '其他檔案格式')
}

export function findingCodeLabel(value: string | null | undefined): string {
  return label(value, FINDING_CODE_LABELS, '其他檢核項目')
}

export function findingTypeLabel(value: string | null | undefined): string {
  return label(value, FINDING_TYPE_LABELS, '其他檢核類型')
}

export function fieldPathLabel(value: string | null | undefined): string {
  const normalizedPath = normalized(value)
  const direct = FIELD_PATH_LABELS[normalizedPath]
  if (direct) return direct
  for (const [suffix, display] of Object.entries(FIELD_PATH_SUFFIX_LABELS)) {
    if (normalizedPath === suffix || normalizedPath.endsWith(`.${suffix}`)) return display
  }
  return '相關必要欄位'
}

export function missingItemStatusLabel(value: string | null | undefined): string {
  return label(value, MISSING_ITEM_STATUS_LABELS, '待確認')
}

export function correctionStatusLabel(value: string | null | undefined): string {
  return label(value, CORRECTION_STATUS_LABELS, '狀態待確認')
}

export function verificationStatusLabel(value: string | null | undefined): string {
  return label(value, VERIFICATION_STATUS_LABELS, '來源狀態待確認')
}

export function severityLabel(value: string | null | undefined): string {
  return label(value, { ERROR: '錯誤', WARNING: '警示', HIGH: '高', MEDIUM: '中', LOW: '低' }, '一般')
}

export function aiStatusLabel(value: string | null | undefined): string {
  return label(value, { READY: '可供參考', COMPLETED: '已完成', BLOCKED: '受阻', NOT_AVAILABLE: '未提供' }, '未提供')
}

export function mapWorkbenchSummary(dto: WorkbenchSummaryDto): ReviewSummaryModel {
  return {
    statusCounts: { ...dto.status_counts },
    highRiskCount: dto.high_risk_count,
    openFindingCount: dto.open_finding_count,
    missingItemCount: dto.missing_item_count,
  }
}

export function mapWorkbenchCase(dto: WorkbenchCaseListItemDto): ReviewQueueItemModel {
  const reviewStatusCode = dto.review_status
  const riskLevelCode = dto.current_risk_level
  return {
    caseId: dto.case_id,
    reviewId: dto.review_id,
    caseNo: dto.case_no,
    name: dto.case_title,
    district: dto.district_code,
    status: reviewStatusCode,
    updatedAt: dto.received_at,
    reviewStatusCode,
    reviewStatusLabel: reviewStatusLabel(reviewStatusCode),
    latestValidationRunId: dto.latest_run?.validation_run_id ?? null,
    riskLevelCode,
    riskLevelLabel: riskLevelLabel(riskLevelCode),
    missingItemCount: dto.missing_item_count,
    highCount: dto.high_count,
    mediumCount: dto.medium_count,
    lowCount: dto.low_count,
    receivedAt: dto.received_at,
    dueAt: dto.due_at,
    assignedReviewerName: dto.assigned_reviewer_display_name,
    latestRunId: dto.latest_run?.validation_run_id ?? null,
    latestRunStatusCode: dto.latest_run?.run_status ?? null,
    latestRunStatusLabel: runStatusLabel(dto.latest_run?.run_status),
    urgencyLabel: urgencyLabel(dto.urgency_level),
  }
}

export function mapDocument(dto: WorkbenchCaseDetailDto['documents'][number]): ReviewDocumentModel {
  return {
    documentId: dto.document_id,
    documentType: dto.document_type,
    documentTypeLabel: documentTypeLabel(dto.document_type),
    filename: dto.original_filename,
    mimeType: dto.mime_type,
    mimeTypeLabel: mimeTypeLabel(dto.mime_type),
    versionNo: dto.version_no,
    isActive: dto.is_active,
    uploadedAt: dto.uploaded_at,
  }
}

export function mapRun(dto: WorkbenchCaseDetailDto['runs'][number]): ReviewRunModel {
  return {
    validationRunId: dto.validation_run_id,
    reviewId: dto.review_id,
    runNo: dto.run_no,
    runStatusCode: dto.run_status,
    runStatusLabel: runStatusLabel(dto.run_status),
    passedCount: dto.passed_count,
    warningCount: dto.warning_count,
    failedCount: dto.failed_count,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
  }
}

function displayScalar(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return String(value)
  return null
}

function systemValue(dto: FindingDto): string | null {
  const comparison = dto.comparison_result ?? {}
  const candidate =
    comparison.system_value ??
    comparison.systemValue ??
    comparison.actual_value ??
    comparison.expected_value ??
    dto.system_grade ??
    dto.system_adjustment_rate
  return displayScalar(candidate)
}

function recommendedActionLabel(value: Record<string, unknown>): string | null {
  const candidate = value.label ?? value.action ?? value.recommendation
  return displayScalar(candidate)
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function numericValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}

function textValue(...values: unknown[]): string | null {
  for (const value of values) {
    const text = displayScalar(value)?.trim()
    if (text) return text
  }
  return null
}

function mapSourceEvidence(values: unknown[]): ReviewReferenceModel[] {
  return values.flatMap((value, index) => {
    const record = objectRecord(value)
    if (!record) return []
    const documentId = textValue(record.document_id, record.documentId)
    const pageNumber = numericValue(record.page ?? record.page_number)
    const fieldCode = textValue(record.field_code)
    const fieldPath = textValue(record.field_path)
    const field = fieldCode
      ? findingCodeLabel(fieldCode)
      : fieldPath
        ? fieldPathLabel(fieldPath)
        : null
    const excerpt = textValue(record.excerpt, record.raw_text)
    const verification = textValue(record.verification_status)
    return [{
      key: textValue(record.source_id, record.extracted_field_id) ?? `evidence-${index}`,
      title: field ? `資料來源｜${field}` : '資料來源',
      detail: excerpt,
      documentId,
      documentVersion: numericValue(record.document_version),
      pageNumber,
      verificationStatus: verification,
    }]
  })
}

function mapLegalBasis(values: unknown[]): ReviewReferenceModel[] {
  return values.flatMap((value, index) => {
    const record = objectRecord(value)
    if (!record) return []
    const ruleName = textValue(record.rule_name, record.rule_code, record.article)
    const version = textValue(record.version_name, record.rule_set_code)
    const article = textValue(record.article)
    const detailParts = [version, article && article !== ruleName ? article : null].filter(Boolean)
    return [{
      key: textValue(record.rule_version_id, record.source_id, record.rule_code) ?? `legal-${index}`,
      title: ruleName ? `法規／規則｜${ruleName}` : '法規／規則依據',
      detail: detailParts.length ? detailParts.join(' · ') : null,
      documentId: textValue(record.document_id),
      documentVersion: numericValue(record.document_version),
      pageNumber: numericValue(record.page ?? record.page_number),
      verificationStatus: null,
    }]
  })
}

export function mapFinding(dto: FindingDto): ReviewFindingModel {
  return {
    findingId: dto.finding_id,
    reviewId: dto.review_id,
    validationRunId: dto.validation_run_id,
    findingCode: dto.finding_code,
    findingCodeLabel: findingCodeLabel(dto.finding_code),
    findingType: dto.finding_type,
    findingTypeLabel: findingTypeLabel(dto.finding_type),
    severityCode: dto.severity,
    severityLabel: severityLabel(dto.severity),
    title: dto.title,
    description: dto.description,
    statusCode: dto.status,
    statusLabel: findingStatusLabel(dto.status),
    documentId: dto.document_id,
    documentVersion: dto.document_version,
    pageNumber: dto.page_number,
    fieldPath: dto.field_path,
    fieldPathLabel: fieldPathLabel(dto.field_path),
    reportedText: dto.reported_text,
    reportedValue: dto.reported_value,
    systemValue: systemValue(dto),
    reportedGrade: dto.reported_grade,
    systemGrade: dto.system_grade,
    reportedAdjustmentRate: dto.reported_adjustment_rate,
    systemAdjustmentRate: dto.system_adjustment_rate,
    aiReasoningSummary: dto.ai_reasoning_summary,
    aiConfidence: dto.ai_confidence,
    aiStatusLabel: aiStatusLabel(dto.ai_status),
    recommendedActionLabel: recommendedActionLabel(dto.recommended_action),
    sourceEvidence: mapSourceEvidence(dto.source_evidence),
    legalBasis: mapLegalBasis(dto.legal_basis),
  }
}

export function mapDecision(dto: DecisionDto): ReviewDecisionModel {
  return {
    decisionId: dto.decision_id,
    reviewId: dto.review_id,
    findingId: dto.finding_id,
    decisionCode: dto.decision,
    decisionLabel: decisionLabel(dto.decision),
    reason: dto.reason,
    decidedAt: dto.decided_at,
  }
}

function diffDisplayValue(value: unknown): string {
  const scalar = displayScalar(value)
  if (scalar !== null) return scalar
  if (value === null || value === undefined) return '—'
  try {
    return JSON.stringify(value)
  } catch {
    return '已提供結構化資料'
  }
}

export function mapVersionDiff(
  dto: WorkbenchCaseDetailDto['version_diffs'][number],
): ReviewVersionDiffModel {
  const mappedFieldPath = dto.field_path ?? dto.current.field_path ?? dto.previous.field_path
  const pathLabel = mappedFieldPath ? fieldPathLabel(mappedFieldPath) : '相關必要欄位'
  const fieldLabel = pathLabel === '相關必要欄位'
    ? findingCodeLabel(dto.field_code)
    : pathLabel
  return {
    key: `${dto.document_group_id}-${dto.field_code}-${dto.previous.document_version}-${dto.current.document_version}`,
    fieldCode: dto.field_code,
    fieldPath: mappedFieldPath,
    fieldLabel,
    previousDocumentVersion: dto.previous.document_version,
    previousValue: diffDisplayValue(dto.previous.normalized_value),
    previousRawText: dto.previous.raw_text,
    previousPageNumber: dto.previous.page_number,
    currentDocumentVersion: dto.current.document_version,
    currentValue: diffDisplayValue(dto.current.normalized_value),
    currentRawText: dto.current.raw_text,
    currentPageNumber: dto.current.page_number,
  }
}

export function mapRiskSummary(dto: RiskSummaryDto | null): {
  level: string
  score: string | null
  summary: string
} | null {
  if (!dto) return null
  return {
    level: riskLevelLabel(dto.overall_risk_level),
    score: dto.risk_score,
    summary: dto.summary,
  }
}

function isUnresolvedFinding(finding: ReviewFindingModel): boolean {
  return !['ACCEPTED', 'PARTIALLY_ACCEPTED', 'REJECTED', 'DISMISSED_FALSE_POSITIVE'].includes(
    normalized(finding.statusCode),
  )
}

export function mapWorkbenchDetail(dto: WorkbenchCaseDetailDto): ReviewDetailModel {
  const findings = dto.findings.map(mapFinding)
  return {
    caseId: dto.case.case_id,
    caseNo: dto.case.case_no,
    caseTitle: dto.case.case_title,
    districtCode: dto.case.district_code,
    valuationBaseDate: dto.case.valuation_base_date,
    caseStatusCode: dto.case.case_status,
    caseStatusLabel: reviewStatusLabel(dto.case.case_status),
    reviewId: dto.review.review_id,
    reviewStatusCode: dto.review.review_status,
    reviewStatusLabel: reviewStatusLabel(dto.review.review_status),
    latestValidationRunId: dto.review.latest_validation_run_id,
    riskLevelCode: dto.review.current_risk_level,
    riskLevelLabel: riskLevelLabel(dto.review.current_risk_level),
    documents: dto.documents.map(mapDocument),
    missingItems: dto.missing_items,
    runs: dto.runs.map(mapRun),
    findings,
    decisions: dto.decisions.map(mapDecision),
    reportDocument: dto.report_document,
    generatedReports: dto.generated_reports,
    correctionRequests: dto.correction_requests,
    versionDiffs: (dto.version_diffs ?? []).map(mapVersionDiff),
    unresolvedFindingCount: findings.filter(isUnresolvedFinding).length,
  }
}

export function latestRunId(detail: ReviewDetailModel | null): string | null {
  if (!detail) return null
  return detail.latestValidationRunId ?? detail.runs.reduce<ReviewRunModel | null>(
    (latest, run) => (!latest || (run.runNo ?? 0) > (latest.runNo ?? 0) ? run : latest),
    null,
  )?.validationRunId ?? null
}

export function readableReportName(report: GeneratedReportDto | null): string | null {
  return report?.original_filename ?? null
}

export function latestGeneratedReport(reports: GeneratedReportDto[]): GeneratedReportDto | null {
  return reports
    .filter((report) => normalized(report.document_type) === 'REVIEW-REPORT')
    .slice()
    .sort((left, right) => right.version_no - left.version_no)[0] ?? null
}

export function selectEvidenceDocument(
  documents: ReviewDocumentModel[],
  preferredDocumentId: string | null | undefined,
): ReviewDocumentModel | null {
  const supported = documents
    .filter((document) =>
      normalized(document.documentType) === 'ORIGINAL'
      && document.isActive
      && normalized(document.mimeType) === 'APPLICATION/PDF',
    )
    .slice()
    .sort((left, right) => {
      const versionDelta = right.versionNo - left.versionNo
      if (versionDelta) return versionDelta
      return right.uploadedAt.localeCompare(left.uploadedAt)
    })
  return supported.find((document) => document.documentId === preferredDocumentId) ?? supported[0] ?? null
}
