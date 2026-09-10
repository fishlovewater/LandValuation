import type { CaseIdentity, CaseSummary } from '../../types/case'

export type HistoryResultCode =
  | 'PASSED'
  | 'CORRECTION'
  | 'RETURNED'
  | 'SUPPLEMENT_REQUIRED'
  | 'IN_PROGRESS'

export type HistoryDateField = 'updated_at' | 'received_at' | 'completed_at'
export type HistorySortField = 'updated_at' | 'received_at' | 'risk_level'
export type HistorySortOrder = 'asc' | 'desc'

export interface HistorySearchParams {
  keyword?: string
  cityCode?: string
  districtCode?: string
  sectionName?: string
  result?: HistoryResultCode
  dateField?: HistoryDateField
  dateFrom?: string
  dateTo?: string
  sort?: HistorySortField
  order?: HistorySortOrder
  offset?: number
  limit?: number
}
export interface HistoryPermissionsDto {
  can_view_valuation: boolean
  can_view_review: boolean
}

export interface HistoryCaseSummaryDto {
  case_id: string
  case_no: string
  case_title: string
  case_type: string
  valuation_base_date: string
  city_code: string
  district_code: string
  case_status: string
  updated_at: string
  review_status?: string | null
  received_at?: string | null
  completed_at?: string | null
  current_risk_level?: string | null
  history_result: HistoryResultCode
  visible_modules: string[]
  has_structured_data: boolean
  has_document_metadata: boolean
}

export interface HistoryCasePageDto {
  items: HistoryCaseSummaryDto[]
  total: number
  offset: number
  limit: number
  permissions: HistoryPermissionsDto
}

export interface HistoryDocumentDto {
  document_id: string
  case_id: string
  document_type: string
  source_module: 'valuation' | 'review'
  file_name: string
  content_type: string
  created_at: string
  updated_at?: null
  document_group_id: string
  version_no: number
  is_active: boolean
  file_size_bytes: number
  checksum_sha256: string
  download_available?: boolean | null
}

export interface HistoryCaseDetailDto {
  case: Record<string, unknown>
  parcels: Record<string, unknown>[]
  documents: HistoryDocumentDto[]
  valuation?: Record<string, unknown> | null
  review?: Record<string, unknown> | null
  permissions: HistoryPermissionsDto
}

export interface HistoryCaseModel extends CaseSummary {
  caseType: string
  valuationBaseDate: string
  cityCode: string
  districtCode: string
  caseStatusCode: string
  caseStatusLabel: string
  historyResultCode: HistoryResultCode
  historyResultLabel: string
  reviewStatusCode: string | null
  receivedAt: string | null
  completedAt: string | null
  riskLevelCode: string | null
  visibleModules: string[]
  hasStructuredData: boolean
  hasDocumentMetadata: boolean
}

export interface HistoryPermissionsModel {
  canViewValuation: boolean
  canViewReview: boolean
}

export interface HistoryDocumentModel {
  documentId: string
  caseId: string
  documentType: string
  documentTypeLabel: string
  sourceModule: 'valuation' | 'review'
  sourceModuleLabel: string
  fileName: string
  contentType: string
  contentTypeLabel: string
  createdAt: string
  versionNo: number
  isActive: boolean
  fileSizeBytes: number
  checksumSha256: string
  downloadAvailable: boolean | null
}

export interface HistoryTimelineEvent {
  id: string
  occurredAt: string
  title: string
  description: string
  module: 'case' | 'valuation' | 'review' | 'document'
  sourceType: string
  sourceId: string | null
}

export interface HistoryValuationModel {
  forms: Record<string, unknown>[]
  valuations: Record<string, unknown>[]
  comparisonAnalyses: Record<string, unknown>[]
  benchmarkValuations: Record<string, unknown>[]
  parcelValuations: Record<string, unknown>[]
  validationRuns: Record<string, unknown>[]
  validationFindings: Record<string, unknown>[]
}

export interface HistoryReviewModel {
  reviews: Record<string, unknown>[]
  findings: Record<string, unknown>[]
  riskSummaries: Record<string, unknown>[]
  decisions: Record<string, unknown>[]
}

export interface HistoryCaseDetailModel extends CaseIdentity {
  caseTitle: string
  caseType: string
  caseStatusCode: string
  caseStatusLabel: string
  valuationBaseDate: string
  cityCode: string
  districtCode: string
  createdAt: string | null
  updatedAt: string | null
  riskLevelCode: string | null
  riskLevelLabel: string
  parcels: Record<string, unknown>[]
  documents: HistoryDocumentModel[]
  valuation: HistoryValuationModel | null
  review: HistoryReviewModel | null
  permissions: HistoryPermissionsModel
  timeline: HistoryTimelineEvent[]
}
