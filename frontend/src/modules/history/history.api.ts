import { isAxiosError } from 'axios'
import { ForbiddenError, http } from '../../api/http'
import { historyScopeForRoles } from '../../router/roleAccess'
import type { DocumentTextPreviewDto } from '../../types/documentPreview'
import type { SpreadsheetPreviewDto } from '../../types/spreadsheet'
import type {
  HistoryCaseDetailDto,
  HistoryCasePageDto,
  HistoryDateField,
  HistoryResultCode,
  HistorySearchParams,
  HistorySortField,
  HistorySortOrder,
} from './history.types'

const HISTORY_RESULT_CODES = new Set<HistoryResultCode>([
  'PASSED',
  'CORRECTION',
  'RETURNED',
  'SUPPLEMENT_REQUIRED',
  'IN_PROGRESS',
])
const VALUATION_RESULT_CODES = new Set<HistoryResultCode>(['CORRECTION', 'IN_PROGRESS'])
const HISTORY_DATE_FIELDS = new Set<HistoryDateField>(['updated_at', 'received_at', 'completed_at'])
const HISTORY_SORT_FIELDS = new Set<HistorySortField>(['updated_at', 'received_at', 'risk_level'])
const HISTORY_SORT_ORDERS = new Set<HistorySortOrder>(['asc', 'desc'])

function isHistoryResult(value: unknown): value is HistoryResultCode {
  return typeof value === 'string' && HISTORY_RESULT_CODES.has(value as HistoryResultCode)
}

function isHistoryDateField(value: unknown): value is HistoryDateField {
  return typeof value === 'string' && HISTORY_DATE_FIELDS.has(value as HistoryDateField)
}

function isHistorySortField(value: unknown): value is HistorySortField {
  return typeof value === 'string' && HISTORY_SORT_FIELDS.has(value as HistorySortField)
}

function isHistorySortOrder(value: unknown): value is HistorySortOrder {
  return typeof value === 'string' && HISTORY_SORT_ORDERS.has(value as HistorySortOrder)
}

export function sanitizeHistorySearchParams(
  params: HistorySearchParams,
  roles: readonly string[],
): HistorySearchParams {
  const scope = historyScopeForRoles(roles)
  const sanitized = { ...params }
  if (!isHistorySortOrder(sanitized.order)) {
    delete sanitized.order
  }
  if (!scope.valuation && !scope.review) {
    delete sanitized.result
    delete sanitized.dateField
    delete sanitized.sort
    return sanitized
  }

  if (!isHistoryResult(sanitized.result) || (!scope.review && !VALUATION_RESULT_CODES.has(sanitized.result))) {
    delete sanitized.result
  }
  if (!isHistoryDateField(sanitized.dateField) || (!scope.review && sanitized.dateField !== 'updated_at')) {
    delete sanitized.dateField
  }
  if (!isHistorySortField(sanitized.sort) || (!scope.review && sanitized.sort !== 'updated_at')) {
    delete sanitized.sort
  }
  return sanitized
}

function queryParams(
  params: HistorySearchParams,
  roles: readonly string[],
): Record<string, string | number> {
  const sanitized = sanitizeHistorySearchParams(params, roles)
  const values: Record<string, string | number | undefined> = {
    keyword: sanitized.keyword?.trim() || undefined,
    city_code: sanitized.cityCode?.trim() || undefined,
    district_code: sanitized.districtCode?.trim() || undefined,
    section_name: sanitized.sectionName?.trim() || undefined,
    result: sanitized.result || undefined,
    date_field: sanitized.dateField || undefined,
    date_from: sanitized.dateFrom || undefined,
    date_to: sanitized.dateTo || undefined,
    sort: sanitized.sort || undefined,
    order: sanitized.order || undefined,
    offset: sanitized.offset ?? 0,
    limit: sanitized.limit ?? 20,
  }
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined && value !== ''),
  ) as Record<string, string | number>
}
export const historyApi = {
  async listCases(
    params: HistorySearchParams = {},
    signal?: AbortSignal,
    roles: readonly string[] = [],
  ): Promise<HistoryCasePageDto> {
    const response = await http.get<HistoryCasePageDto>('/history/cases', {
      signal,
      params: queryParams(params, roles),
    })
    return response.data
  },

  async getCase(caseId: string, signal?: AbortSignal): Promise<HistoryCaseDetailDto> {
    const response = await http.get<HistoryCaseDetailDto>(`/history/cases/${caseId}`, { signal })
    return response.data
  },

  async downloadDocument(documentId: string, signal?: AbortSignal): Promise<Blob> {
    const response = await http.get<Blob>(`/history/documents/${documentId}/download`, {
      signal,
      responseType: 'blob',
    })
    return response.data
  },

  async previewSpreadsheet(documentId: string, signal?: AbortSignal): Promise<SpreadsheetPreviewDto> {
    const response = await http.get<SpreadsheetPreviewDto>(
      `/history/documents/${documentId}/spreadsheet-preview`,
      { signal },
    )
    return response.data
  },

  async previewTextDocument(documentId: string, signal?: AbortSignal): Promise<DocumentTextPreviewDto> {
    const response = await http.get<DocumentTextPreviewDto>(
      `/history/documents/${documentId}/text-preview`,
      { signal },
    )
    return response.data
  },
}

export function safeHistoryErrorMessage(error: unknown): string {
  if (error instanceof ForbiddenError) return error.message
  if (isAxiosError(error) && error.response?.status === 404) {
    return '找不到目前案件歷程，請重新整理後再試。'
  }
  return '案件歷程目前無法載入，請稍後再試。'
}

export function safeHistoryDownloadError(error: unknown): string {
  if (error instanceof ForbiddenError) return error.message
  if (isAxiosError(error)) {
    const status = error.response?.status
    const code = error.response?.data?.error?.code
    if (status === 413 && code === 'PREVIEW_TOO_LARGE') {
      return '文件檔案過大，請下載原始文件查看完整內容。'
    }
    if (status === 415 && code === 'PREVIEW_NOT_SUPPORTED') {
      return '此文件格式目前不支援內嵌預覽，請下載原始文件查看。'
    }
    if (status === 404 && code === 'DOCUMENT_OBJECT_MISSING') return '文件目前無法下載'
  }
  return '文件目前無法下載'
}
