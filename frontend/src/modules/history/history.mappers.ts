import { decisionLabel, riskLabel, statusLabel } from '../../utils/enumLabels'
import { userFieldLabel, userStructuredValue } from '../../utils/fieldLabels'
import { formatDateZhTw } from '../../utils/formatters'
import type {
  HistoryCaseDetailDto,
  HistoryCaseDetailModel,
  HistoryCaseModel,
  HistoryCaseSummaryDto,
  HistoryDocumentDto,
  HistoryDocumentModel,
  HistoryPermissionsDto,
  HistoryPermissionsModel,
  HistoryReviewModel,
  HistoryTimelineEvent,
  HistoryValuationModel,
} from './history.types'

const RESULT_LABELS: Readonly<Record<string, string>> = {
  PASSED: '審查通過',
  CORRECTION: '補正中',
  RETURNED: '已退回',
  SUPPLEMENT_REQUIRED: '待補件',
  IN_PROGRESS: '處理中',
}

const VALUATION_TYPE_LABELS: Readonly<Record<string, string>> = {
  CASE: '案件估價',
  PARCEL: '宗地估價',
}

const CASE_TYPE_LABELS: Readonly<Record<string, string>> = {
  LAND: '土地徵收補償市價查估案件',
}

const FORM_CODE_LABELS: Readonly<Record<string, string>> = {
  S01: '地價區段勘查表',
  F01: '買賣實例調查估價表',
  F02: '比較法調查估價表',
  'F02-RF': '影響地價區域因素分析明細表',
  F03: '比準地地價估計表',
  F04: '徵收土地宗地市價估計表',
}

const DOCUMENT_TYPE_LABELS: Readonly<Record<string, string>> = {
  ORIGINAL: '原始查估文件',
  'LAND-REGISTER': '土地登記謄本',
  'CADASTRAL-MAP': '地籍圖',
  'AI-MAP-EVIDENCE': 'AI 地圖證據',
  PHOTOS: '現場照片',
  ATTACHMENTS: '附件',
  'COMPLETE-VALUATION-REPORT': '完整送審 PDF',
  'CANDIDATE-CONFIRMATION-EXPORT': '辨識結果確認匯出',
  'GENERATED-DRAFT-REPORT': '草稿報告',
  'GENERATED-REPORT': '正式報告',
  'REVIEW-REPORT': '審查報告',
  'REVIEW-REPORT-PDF': '審查報告',
  'CORRECTION-REQUEST': '修正通知',
}

const MIME_TYPE_LABELS: Readonly<Record<string, string>> = {
  'APPLICATION/PDF': 'PDF 文件',
  'IMAGE/JPEG': 'JPEG 圖片',
  'IMAGE/PNG': 'PNG 圖片',
  'APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.WORDPROCESSINGML.DOCUMENT': 'Word 文件',
  'APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.SPREADSHEETML.SHEET': 'Excel 文件',
}

function normalized(value: unknown): string {
  return typeof value === 'string' ? value.trim().toUpperCase() : ''
}

function stringValue(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

function nullableString(value: unknown): string | null {
  const result = stringValue(value)
  return result || null
}

function recordValue(record: Record<string, unknown>, key: string): unknown {
  return record[key]
}

function rows(data: Record<string, unknown> | null | undefined, key: string): Record<string, unknown>[] {
  const value = data?.[key]
  if (!Array.isArray(value)) return []
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
}

function resultLabel(value: string): string {
  return RESULT_LABELS[normalized(value)] ?? '未知歷程結果'
}

export function valuationTypeLabel(value: string | null | undefined): string {
  return VALUATION_TYPE_LABELS[normalized(value)] ?? '其他估價類型'
}

export function caseTypeLabel(value: string | null | undefined): string {
  return CASE_TYPE_LABELS[normalized(value)] ?? '其他案件類型'
}

export function formCodeLabel(value: string | null | undefined): string {
  return FORM_CODE_LABELS[normalized(value)] ?? '查估書表'
}

function documentTypeLabel(value: string): string {
  return DOCUMENT_TYPE_LABELS[normalized(value)] ?? '其他文件'
}

function mimeTypeLabel(value: string): string {
  return MIME_TYPE_LABELS[normalized(value)] ?? '其他檔案格式'
}

function sourceModuleLabel(value: 'valuation' | 'review'): string {
  return value === 'review' ? '智慧審查' : '估價作業'
}

export function mapHistoryPermissions(dto: HistoryPermissionsDto): HistoryPermissionsModel {
  return {
    canViewValuation: dto.can_view_valuation,
    canViewReview: dto.can_view_review,
  }
}

export function mapHistoryCaseSummary(
  dto: HistoryCaseSummaryDto,
  permissions?: HistoryPermissionsDto,
): HistoryCaseModel {
  const visibleModules = dto.visible_modules.filter((module) => {
    if (module === 'valuation') return permissions?.can_view_valuation !== false
    if (module === 'review') return permissions?.can_view_review !== false
    return false
  })
  return {
    caseId: dto.case_id,
    caseNo: dto.case_no,
    name: dto.case_title,
    district: dto.district_code,
    status: dto.case_status,
    updatedAt: dto.updated_at,
    caseType: dto.case_type,
    valuationBaseDate: dto.valuation_base_date,
    cityCode: dto.city_code,
    districtCode: dto.district_code,
    caseStatusCode: dto.case_status,
    caseStatusLabel: statusLabel(dto.case_status),
    historyResultCode: dto.history_result,
    historyResultLabel: resultLabel(dto.history_result),
    reviewStatusCode: dto.review_status ?? null,
    receivedAt: dto.received_at ?? null,
    completedAt: dto.completed_at ?? null,
    riskLevelCode: dto.current_risk_level ?? null,
    visibleModules,
    hasStructuredData: dto.has_structured_data,
    hasDocumentMetadata: dto.has_document_metadata,
  }
}

export const mapHistoryCase = mapHistoryCaseSummary

export function mapHistoryDocument(dto: HistoryDocumentDto): HistoryDocumentModel {
  return {
    documentId: dto.document_id,
    caseId: dto.case_id,
    documentGroupId: dto.document_group_id,
    documentType: dto.document_type,
    documentTypeLabel: documentTypeLabel(dto.document_type),
    sourceModule: dto.source_module,
    sourceModuleLabel: sourceModuleLabel(dto.source_module),
    fileName: dto.file_name,
    contentType: dto.content_type,
    contentTypeLabel: mimeTypeLabel(dto.content_type),
    createdAt: dto.created_at,
    versionNo: dto.version_no,
    isActive: dto.is_active,
    fileSizeBytes: dto.file_size_bytes,
    checksumSha256: dto.checksum_sha256,
    downloadAvailable: dto.download_available ?? null,
  }
}

export const mapDocument = mapHistoryDocument

function mapValuation(data: Record<string, unknown> | null | undefined): HistoryValuationModel | null {
  if (!data) return null
  return {
    forms: rows(data, 'forms'),
    valuations: rows(data, 'valuations'),
    comparisonAnalyses: rows(data, 'comparison_analyses'),
    benchmarkValuations: rows(data, 'benchmark_valuations'),
    parcelValuations: rows(data, 'parcel_valuations'),
    validationRuns: rows(data, 'validation_runs'),
    validationFindings: rows(data, 'validation_findings'),
  }
}

function mapReview(data: Record<string, unknown> | null | undefined): HistoryReviewModel | null {
  if (!data) return null
  return {
    reviews: rows(data, 'reviews'),
    validationRuns: rows(data, 'validation_runs'),
    inputSnapshots: rows(data, 'input_snapshots'),
    findings: rows(data, 'findings'),
    riskSummaries: rows(data, 'risk_summaries'),
    decisions: rows(data, 'decisions'),
  }
}

function addEvent(
  events: HistoryTimelineEvent[],
  input: Omit<HistoryTimelineEvent, 'id'> & { id?: string },
): void {
  if (!input.occurredAt || Number.isNaN(new Date(input.occurredAt).getTime())) return
  events.push({ ...input, id: input.id ?? `${input.sourceType}-${input.sourceId ?? input.occurredAt}` })
}

function addRowEvent(
  events: HistoryTimelineEvent[],
  collection: Record<string, unknown>[],
  options: {
    module: HistoryTimelineEvent['module']
    sourceType: string
    dateKeys: string[]
    title: string
    description: (row: Record<string, unknown>) => string
    idKey?: string
  },
): void {
  collection.forEach((row) => {
    const occurredAt = options.dateKeys.map((key) => nullableString(recordValue(row, key))).find(Boolean)
    if (!occurredAt) return
    const sourceId = nullableString(recordValue(row, options.idKey ?? 'id'))
    addEvent(events, {
      occurredAt,
      title: options.title,
      description: options.description(row),
      module: options.module,
      sourceType: options.sourceType,
      sourceId,
      id: `${options.sourceType}-${sourceId ?? occurredAt}`,
    })
  })
}

export function mapHistoryTimeline(dto: HistoryCaseDetailDto): HistoryTimelineEvent[] {
  const events: HistoryTimelineEvent[] = []
  const caseData = dto.case
  const caseId = nullableString(caseData.case_id)
  const caseCreatedAt = nullableString(caseData.created_at)
  const caseUpdatedAt = nullableString(caseData.updated_at)
  if (caseCreatedAt) {
    addEvent(events, {
      occurredAt: caseCreatedAt,
      title: '案件建立',
      description: '案件資料已建立。',
      module: 'case',
      sourceType: 'case_created',
      sourceId: caseId,
    })
  }
  if (caseUpdatedAt && caseUpdatedAt !== caseCreatedAt) {
    addEvent(events, {
      occurredAt: caseUpdatedAt,
      title: '案件資料更新',
      description: '案件基本資料有最新更新。',
      module: 'case',
      sourceType: 'case_updated',
      sourceId: caseId,
    })
  }

  const canViewValuation = dto.permissions.can_view_valuation
  const canViewReview = dto.permissions.can_view_review
  dto.documents.filter((document) => document.source_module === 'valuation' ? canViewValuation : canViewReview).forEach((document) => {
    addEvent(events, {
      occurredAt: document.created_at,
      title: `${sourceModuleLabel(document.source_module)}文件建立`,
      description: `${document.file_name}（第 ${document.version_no} 版）`,
      module: 'document',
      sourceType: 'document_created',
      sourceId: document.document_id,
    })
  })

  const valuation = canViewValuation ? dto.valuation : null
  addRowEvent(events, rows(valuation, 'forms'), {
    module: 'valuation',
    sourceType: 'valuation_form',
    dateKeys: ['updated_at', 'created_at'],
    title: '估價表單更新',
    idKey: 'form_instance_id',
    description: (row) => {
      const code = formCodeLabel(stringValue(row.form_code))
      const status = stringValue(row.form_status)
      return status ? `${code}，狀態：${statusLabel(status)}` : code
    },
  })
  addRowEvent(events, rows(valuation, 'valuations'), {
    module: 'valuation',
    sourceType: 'valuation_result',
    dateKeys: ['calculated_at', 'updated_at', 'created_at'],
    title: '估價結果完成',
    idKey: 'valuation_id',
    description: (row) => {
      const status = stringValue(row.result_status)
      return status ? `估價結果：${statusLabel(status)}` : '估價結果已儲存。'
    },
  })
  addRowEvent(events, rows(valuation, 'validation_runs'), {
    module: 'valuation',
    sourceType: 'valuation_validation',
    dateKeys: ['completed_at', 'started_at'],
    title: '估價檢核完成',
    idKey: 'validation_run_id',
    description: (row) => {
      const status = stringValue(row.run_status)
      return status ? `檢核狀態：${statusLabel(status)}` : '估價檢核已完成。'
    },
  })

  const review = canViewReview ? dto.review : null
  addRowEvent(events, rows(review, 'reviews'), {
    module: 'review',
    sourceType: 'review_received',
    dateKeys: ['received_at'],
    title: '案件送達審查',
    idKey: 'review_id',
    description: (row) => {
      const status = stringValue(row.review_status)
      return status ? `審查狀態：${statusLabel(status)}` : '案件已進入審查流程。'
    },
  })
  addRowEvent(events, rows(review, 'reviews'), {
    module: 'review',
    sourceType: 'review_started',
    dateKeys: ['started_at'],
    title: '審查開始',
    idKey: 'review_id',
    description: () => '審查人員已開始處理案件。',
  })
  addRowEvent(events, rows(review, 'reviews'), {
    module: 'review',
    sourceType: 'review_completed',
    dateKeys: ['completed_at'],
    title: '審查完成',
    idKey: 'review_id',
    description: () => '審查流程已完成。',
  })
  addRowEvent(events, rows(review, 'input_snapshots'), {
    module: 'review',
    sourceType: 'review_input_snapshot',
    dateKeys: ['frozen_at'],
    title: '審查輸入版本凍結',
    idKey: 'external_input_snapshot_id',
    description: (row) => {
      const source = normalized(row.source)
      const sourceLabel = source === 'PLATFORM' ? '平台送審' : source === 'EXTERNAL' ? '外部案件' : '審查輸入'
      const version = stringValue(row.input_version)
      return `${sourceLabel}${version ? ` v${version}` : ''} 已凍結作為檢核依據。`
    },
  })
  addRowEvent(events, rows(review, 'validation_runs'), {
    module: 'review',
    sourceType: 'review_validation_run',
    dateKeys: ['completed_at', 'started_at'],
    title: '審查檢核完成',
    idKey: 'validation_run_id',
    description: (row) => {
      const runNo = stringValue(row.run_no)
      const status = stringValue(row.run_status)
      return `檢核批次${runNo ? ` #${runNo}` : ''}${status ? `，狀態：${statusLabel(status)}` : ''}`
    },
  })
  addRowEvent(events, rows(review, 'findings'), {
    module: 'review',
    sourceType: 'review_finding',
    dateKeys: ['created_at'],
    title: '審查疑點建立',
    idKey: 'finding_id',
    description: (row) => stringValue(row.title, '審查疑點已建立。'),
  })
  addRowEvent(events, rows(review, 'decisions'), {
    module: 'review',
    sourceType: 'review_decision',
    dateKeys: ['decided_at', 'created_at'],
    title: '審查決定儲存',
    idKey: 'decision_id',
    description: (row) => {
      const decision = stringValue(row.decision)
      return decision ? `決定：${decisionLabel(decision)}` : '審查決定已儲存。'
    },
  })
  addRowEvent(events, rows(review, 'risk_summaries'), {
    module: 'review',
    sourceType: 'review_risk_summary',
    dateKeys: ['generated_at', 'created_at'],
    title: '風險摘要更新',
    idKey: 'risk_summary_id',
    description: (row) => {
      const level = stringValue(row.overall_risk_level)
      return level ? `風險等級：${riskLabel(level)}` : '風險摘要已更新。'
    },
  })

  return events.sort((left, right) => {
    const dateOrder = new Date(left.occurredAt).getTime() - new Date(right.occurredAt).getTime()
    return dateOrder || left.id.localeCompare(right.id)
  })
}

export function mapHistoryDetail(dto: HistoryCaseDetailDto): HistoryCaseDetailModel {
  const caseData = dto.case
  const permissions = mapHistoryPermissions(dto.permissions)
  const valuation = permissions.canViewValuation ? dto.valuation : null
  const review = permissions.canViewReview ? dto.review : null
  const caseId = stringValue(caseData.case_id)
  const caseNo = stringValue(caseData.case_no, caseId)
  const caseTitle = stringValue(caseData.case_title, '未命名案件')
  const caseStatusCode = stringValue(caseData.case_status)
  const riskLevelCode = nullableString(
    caseData.current_risk_level
      ?? rows(review, 'risk_summaries')[0]?.overall_risk_level,
  )
  return {
    caseId,
    caseNo,
    caseTitle,
    caseType: caseTypeLabel(stringValue(caseData.case_type)),
    caseStatusCode,
    caseStatusLabel: statusLabel(caseStatusCode),
    valuationBaseDate: stringValue(caseData.valuation_base_date),
    cityCode: stringValue(caseData.city_code),
    districtCode: stringValue(caseData.district_code),
    createdAt: nullableString(caseData.created_at),
    updatedAt: nullableString(caseData.updated_at),
    riskLevelCode,
    riskLevelLabel: riskLevelCode ? riskLabel(riskLevelCode) : '未標示風險',
    parcels: permissions.canViewValuation ? dto.parcels : [],
    documents: dto.documents
      .filter((document) => document.source_module === 'valuation' ? permissions.canViewValuation : permissions.canViewReview)
      .map(mapHistoryDocument),
    valuation: mapValuation(valuation),
    review: mapReview(review),
    permissions,
    timeline: mapHistoryTimeline({ ...dto, valuation, review }),
    versions: dto.versions ?? [],
    changes: dto.changes ?? [],
    versionDiffs: dto.version_diffs ?? [],
  }
}

export const mapHistoryCaseDetail = mapHistoryDetail

export function readableValue(value: unknown): string {
  return userStructuredValue(value)
}

export function readableDate(value: unknown): string {
  return formatDateZhTw(typeof value === 'string' ? value : null)
}

export function readableFieldLabel(value: string): string {
  return userFieldLabel(value)
}
