import { http } from '../../api/http'
import { mapReviewCase, mapWorkbenchDetail, mapWorkbenchStart } from './review.mappers'
import type {
  ReviewCaseDetail,
  ReviewCasePage,
  ReviewCaseQuery,
  ReviewSummary,
  WorkbenchCaseListDto,
  WorkbenchDetailDto,
  WorkbenchSummaryDto,
  WorkbenchStartDto,
  ReviewStartResult,
  FindingTriageDecision,
  DecisionDto,
  CorrectionRequestDto,
  GeneratedReportDto,
  ReviewReportDto,
} from './review.types'

export const reviewApi = {
  async getWorkbenchSummary(): Promise<ReviewSummary> {
    const { data } = await http.get<WorkbenchSummaryDto>('/api/v1/review/workbench/summary')
    return {
      statusCounts: data.status_counts,
      totalCount: Object.values(data.status_counts).reduce((sum, count) => sum + count, 0),
      highRiskCount: data.high_risk_count,
      openFindingCount: data.open_finding_count,
      missingItemCount: data.missing_item_count,
    }
  },

  async listWorkbenchCases(query: ReviewCaseQuery): Promise<ReviewCasePage> {
    const params: Record<string, string | number> = {}
    if (query.q) params.q = query.q
    if (query.status) params.status = query.status
    if (query.riskLevel) params.risk_level = query.riskLevel
    if (query.statusGroup) params.status_group = query.statusGroup
    if (query.limit != null) params.limit = query.limit
    if (query.offset != null) params.offset = query.offset
    const { data } = await http.get<WorkbenchCaseListDto>('/api/v1/review/workbench/cases', { params })
    return { items:data.items.map(mapReviewCase), total:data.total, limit:data.limit, offset:data.offset }
  },

  async getWorkbenchCase(reviewId: string): Promise<ReviewCaseDetail> {
    const { data } = await http.get<WorkbenchDetailDto>(`/api/v1/review/workbench/cases/${reviewId}`)
    return mapWorkbenchDetail(data)
  },

  async startWorkbenchCase(reviewId: string): Promise<ReviewStartResult> {
    const { data } = await http.post<WorkbenchStartDto>(`/api/v1/review/workbench/cases/${reviewId}/start`)
    return mapWorkbenchStart(data)
  },

  async getDocumentContent(reviewId: string, documentId: string): Promise<Blob> {
    const { data } = await http.get<Blob>(
      `/api/v1/review/workbench/cases/${reviewId}/documents/${documentId}/content`,
      { responseType: 'blob' },
    )
    return data
  },

  async triageFinding(reviewId: string, findingId: string, decision: FindingTriageDecision, reason: string): Promise<DecisionDto> {
    const { data } = await http.post<DecisionDto>(`/api/v1/review/findings/${findingId}/triage`, {
      review_id: reviewId,
      decision,
      reason,
    })
    return data
  },

  async createAndSendCorrection(reviewId: string, message: string, dueAt: string): Promise<CorrectionRequestDto> {
    const { data: created } = await http.post<CorrectionRequestDto>(`/api/v1/review/cases/${reviewId}/correction-requests`, {
      message,
      due_at: dueAt,
    })
    const { data: sent } = await http.post<CorrectionRequestDto>(
      `/api/v1/review/correction-requests/${created.correction_request_id}/send`,
      {},
    )
    return sent
  },

  async completeReview(reviewId: string, reason: string): Promise<DecisionDto> {
    const { data } = await http.post<DecisionDto>(`/api/v1/review/cases/${reviewId}/complete-review`, { reason })
    return data
  },

  async getStructuredReport(runId: string): Promise<ReviewReportDto> {
    const { data } = await http.get<ReviewReportDto>(`/api/v1/review/runs/${runId}/report`)
    return data
  },

  async generatePdfReport(runId: string): Promise<GeneratedReportDto> {
    const { data } = await http.post<GeneratedReportDto>(`/api/v1/review/runs/${runId}/report/pdf`)
    return data
  },

  async generateReport(runId: string, format: 'xlsx' | 'docx'): Promise<GeneratedReportDto> {
    const { data } = await http.post<GeneratedReportDto>(`/api/v1/review/runs/${runId}/reports`, { format })
    return data
  },

  async downloadReport(documentId: string): Promise<Blob> {
    const { data } = await http.get<Blob>(`/api/v1/review/reports/${documentId}/download`, { responseType:'blob' })
    return data
  },
}