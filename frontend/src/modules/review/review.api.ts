import { isAxiosError } from 'axios'
import { ForbiddenError, http } from '../../api/http'
import type {
  DocumentCategory,
  ExtractionCandidateDecision,
  ExtractionResponseDto,
} from '../valuation/valuation.types'
import type {
  CorrectionRequestCreateDto,
  CorrectionRequestDto,
  DecisionDto,
  ExternalReviewCaseCreateDto,
  ExternalReviewCaseCreatedDto,
  FindingDto,
  FindingTriageRequestDto,
  GeneratedReportCreateDto,
  GeneratedReportDto,
  ReviewCompletionRequestDto,
  ReviewReportDto,
  WorkbenchSummaryDto,
  WorkbenchCaseDetailDto,
  WorkbenchCaseListDto,
  WorkbenchPreflightDto,
  WorkbenchStartDto,
  WorkbenchDocumentDto,
  MissingItemDto,
} from './review.types'

export interface ListReviewCasesParams {
  q?: string
  status?: string
  riskLevel?: string
  statusGroup?: string
  source?: string
  district?: string
  urgency?: string
  sortBy?: string
  sortDirection?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export interface ReviewFilledForm {
  form_instance_id: string
  form_code: string
  form_name: string
  version_no: number
  fields: Array<{ field_name: string; label: string; value: unknown; origin: 'AUTO' | 'HUMAN'; source_page: number | null }>
}

export interface ExternalExtractionConfirmation {
  extracted_field_id: string
  decision: ExtractionCandidateDecision
  corrected_value?: unknown
}

function reviewSortKey(value?: string): string | undefined {
  const keys: Record<string, string> = {
    caseNo: 'case_no',
    name: 'case_title',
    status: 'status',
    updatedAt: 'received_at',
    dueAt: 'due_at',
    risk: 'risk',
  }
  return value ? keys[value] ?? 'received_at' : undefined
}

export const reviewApi = {
  async getSummary(signal?: AbortSignal): Promise<WorkbenchSummaryDto> {
    const response = await http.get<WorkbenchSummaryDto>('/review/workbench/summary', { signal })
    return response.data
  },

  async listCases(params: ListReviewCasesParams = {}, signal?: AbortSignal): Promise<WorkbenchCaseListDto> {
    const response = await http.get<WorkbenchCaseListDto>('/review/workbench/cases', {
      signal,
      params: {
        q: params.q,
        status: params.status,
        risk_level: params.riskLevel,
        status_group: params.statusGroup,
        source: params.source,
        district: params.district,
        urgency: params.urgency,
        sort_by: reviewSortKey(params.sortBy),
        sort_direction: params.sortDirection,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      },
    })
    return response.data
  },

  async getCase(reviewId: string): Promise<WorkbenchCaseDetailDto> {
    const response = await http.get<WorkbenchCaseDetailDto>(`/review/workbench/cases/${reviewId}`)
    return response.data
  },

  async createExternalCase(payload: ExternalReviewCaseCreateDto): Promise<ExternalReviewCaseCreatedDto> {
    const response = await http.post<ExternalReviewCaseCreatedDto>(
      '/review/workbench/external-cases',
      payload,
    )
    return response.data
  },

  async uploadExternalDocument(
    reviewId: string,
    category: Exclude<DocumentCategory, 'complete-valuation-report'>,
    file: File,
    documentGroupId?: string | null,
  ): Promise<WorkbenchDocumentDto> {
    const body = new FormData()
    body.append('category', category)
    body.append('file', file)
    if (documentGroupId) body.append('document_group_id', documentGroupId)
    const response = await http.post<WorkbenchDocumentDto>(
      `/review/workbench/cases/${reviewId}/external-documents`,
      body,
      { headers: { 'Content-Type': undefined } },
    )
    return response.data
  },

  async startExternalDocumentExtraction(
    reviewId: string,
    documentId: string,
  ): Promise<ExtractionResponseDto> {
    const response = await http.post<ExtractionResponseDto>(
      `/review/workbench/cases/${reviewId}/external-documents/${documentId}/extract`,
    )
    return response.data
  },

  async getExternalDocumentForms(reviewId: string, documentId: string): Promise<ReviewFilledForm[]> {
    const response = await http.get<ReviewFilledForm[]>(`/review/workbench/cases/${reviewId}/external-documents/${documentId}/forms`)
    return response.data
  },

  async getExternalDocumentExtraction(
    reviewId: string,
    documentId: string,
  ): Promise<ExtractionResponseDto> {
    const response = await http.get<ExtractionResponseDto>(
      `/review/workbench/cases/${reviewId}/external-documents/${documentId}/extraction`,
    )
    return response.data
  },

  async confirmExternalDocumentExtraction(
    reviewId: string,
    documentId: string,
    confirmations: ExternalExtractionConfirmation[],
  ): Promise<ExtractionResponseDto> {
    const response = await http.post<ExtractionResponseDto>(
      `/review/workbench/cases/${reviewId}/external-documents/${documentId}/extraction/confirm`,
      { confirmations },
    )
    return response.data
  },

  async preflightCase(reviewId: string): Promise<WorkbenchPreflightDto> {
    const response = await http.post<WorkbenchPreflightDto>(`/review/workbench/cases/${reviewId}/start/preflight`)
    return response.data
  },

  async startCase(reviewId: string): Promise<WorkbenchStartDto> {
    const response = await http.post<WorkbenchStartDto>(`/review/workbench/cases/${reviewId}/start`)
    return response.data
  },

  async requestSupplement(reviewId: string, dueAt: string): Promise<MissingItemDto[]> {
    const response = await http.post<MissingItemDto[]>(
      `/review/cases/${reviewId}/supplement-request`,
      { due_at: dueAt },
    )
    return response.data
  },

  async getDocumentContent(reviewId: string, documentId: string): Promise<Blob> {
    const response = await http.get<Blob>(
      `/review/workbench/cases/${reviewId}/documents/${documentId}/content`,
      { responseType: 'blob' },
    )
    return response.data
  },

  async listFindings(validationRunId: string): Promise<FindingDto[]> {
    const response = await http.get<FindingDto[]>(`/review/runs/${validationRunId}/findings`)
    return response.data
  },

  async triageFinding(findingId: string, payload: FindingTriageRequestDto): Promise<DecisionDto> {
    const response = await http.post<DecisionDto>(`/review/findings/${findingId}/triage`, payload)
    return response.data
  },

  async createCorrectionRequest(
    reviewId: string,
    payload: CorrectionRequestCreateDto,
  ): Promise<CorrectionRequestDto> {
    const response = await http.post<CorrectionRequestDto>(
      `/review/cases/${reviewId}/correction-requests`,
      payload,
    )
    return response.data
  },

  async sendCorrectionRequest(correctionRequestId: string): Promise<CorrectionRequestDto> {
    const response = await http.post<CorrectionRequestDto>(
      `/review/correction-requests/${correctionRequestId}/send`,
      {},
    )
    return response.data
  },

  async registerCorrectionResubmission(
    correctionRequestId: string,
    documentId: string,
    documentVersion: number,
  ): Promise<CorrectionRequestDto> {
    const response = await http.post<CorrectionRequestDto>(
      `/review/correction-requests/${correctionRequestId}/resubmissions`,
      { document_id: documentId, document_version: documentVersion },
    )
    return response.data
  },

  async recheckCorrectionRequest(correctionRequestId: string): Promise<CorrectionRequestDto> {
    const response = await http.post<CorrectionRequestDto>(
      `/review/correction-requests/${correctionRequestId}/recheck`,
    )
    return response.data
  },

  async completeReview(reviewId: string, payload: ReviewCompletionRequestDto): Promise<DecisionDto> {
    const response = await http.post<DecisionDto>(`/review/cases/${reviewId}/complete-review`, payload)
    return response.data
  },

  async getReport(validationRunId: string): Promise<ReviewReportDto> {
    const response = await http.get<ReviewReportDto>(`/review/runs/${validationRunId}/report`)
    return response.data
  },

  async generateReportPdf(validationRunId: string): Promise<GeneratedReportDto> {
    const response = await http.post<GeneratedReportDto>(`/review/runs/${validationRunId}/report/pdf`)
    return response.data
  },

  async generateReport(
    validationRunId: string,
    payload: GeneratedReportCreateDto,
  ): Promise<GeneratedReportDto> {
    const response = await http.post<GeneratedReportDto>(
      `/review/runs/${validationRunId}/reports`,
      payload,
    )
    return response.data
  },

  async downloadReport(documentId: string): Promise<Blob> {
    const response = await http.get<Blob>(`/review/reports/${documentId}/download`, {
      responseType: 'blob',
    })
    return response.data
  },
}

export function safeReviewErrorMessage(error: unknown): string {
  if (error instanceof ForbiddenError) return error.message
  if (isAxiosError(error) && error.response?.status === 404) {
    return '找不到目前審查案件，請重新整理後再試。'
  }
  if (isAxiosError(error) && error.response?.status === 409) {
    const code = error.response.data?.error?.code
    const knownMessages: Record<string, string> = {
      REVIEW_STATE_CONFLICT: '案件狀態已變更，請重新整理後再試。',
      FINDING_DECISION_CONFLICT: '此疑點已被其他流程更新，請重新整理後確認目前狀態。',
      REVIEW_COMPLETION_BLOCKED: '案件仍有未完成的審查項目，請先處理阻擋項目。',
      REVIEW_ALREADY_COMPLETED: '此案件已完成審查，畫面已切換為唯讀。',
      REVIEW_SUBMISSION_STALE: '目前檢核不是最新送審版本，請重新執行最新版本檢核。',
      REVIEW_REPORT_NOT_AVAILABLE: '審查報告須在案件完成且最新檢核完成後產生。',
      CORRECTION_REQUEST_BLOCKED: '目前無法送出修正通知，請先完成疑點判定或前一筆修正通知。',
      CORRECTION_REQUEST_STATE_CONFLICT: '修正通知狀態已變更，請重新整理後再試。',
      CORRECTION_REQUEST_STALE: '修正通知不是基於最新審查結果，請重新整理案件。',
      CORRECTION_RECHECK_INVALID: '目前修正通知尚未進入可重新檢核的狀態。',
      CORRECTION_RECHECK_INCOMPLETE: '新版資料仍有缺件或完整性問題，請查看案件缺件後再次補正。',
      REVIEW_RESUBMISSION_REQUIRED: '估價端尚未建立並送出較新的正式版本，暫時不能重新檢核。',
      CORRECTION_RECHECK_SUBMISSION_INVALID: '新版送審資料不存在或不屬於此審查案件。',
      CORRECTION_RECHECK_DOCUMENT_MISMATCH: '新版回件文件與目前送審版本不一致，請確認估價端已重新送審。',
      CORRECTION_RESUBMISSION_INVALID: '補正回件版本不符合案件沿革或版本要求。',
      EXTERNAL_RESUBMISSION_EXTRACTION_REQUIRED: '外部修正版尚未完成 OCR／文字擷取，請先完成文件辨識。',
      EXTERNAL_RESUBMISSION_CONFIRMATION_REQUIRED: '外部修正版仍有待確認欄位，請先完成欄位確認。',
      REVIEW_DECISION_INVALID: '請補充審查理由或必要內容。',
      EXTERNAL_REVIEW_OPERATION_NOT_ALLOWED: '此操作只適用於外部審查案件。',
      DATA_CONFLICT: '資料未能儲存，請重試；若仍失敗，請檢查後端資料限制。',
      REVIEW_OCR_CONFIRMATION_REQUIRED: '請先確認或排除疑慮欄位，再開始審查。',
    }
    return knownMessages[code] ?? '案件狀態不允許此操作，請重新整理後確認。'
  }
  if (isAxiosError(error) && error.response?.status === 422) {
    const code = error.response.data?.error?.code
    if (code === 'CORRECTION_DUE_AT_INVALID') return '修正期限必須晚於目前時間。'
    if (code === 'EXTERNAL_REVIEW_DOCUMENT_CATEGORY_INVALID') return '此文件類型不能作為外部審查來源文件。'
    if (code === 'EXTRACTED_TEXT_REQUIRED') return '文件沒有可供欄位辨識的文字內容，請改用可讀取的文件或人工查核。'
    if (code === 'EXTRACTION_CONFIRMATION_INVALID') return '欄位確認內容不完整或已失效，請重新讀取辨識結果後再試。'
    return '文件、欄位或輸入內容格式不正確，請檢查後再試。'
  }
  return '審查服務目前無法完成此操作，請稍後再試。'
}
