import { http } from '../../api/http'
import { mapReviewCase, mapWorkbenchDetail } from './review.mappers'
import type {
  ReviewCaseDetail,
  ReviewCasePage,
  ReviewCaseQuery,
  ReviewSummary,
  WorkbenchCaseListDto,
  WorkbenchDetailDto,
  WorkbenchSummaryDto,
} from './review.types'

export const reviewApi = {
  async getWorkbenchSummary(): Promise<ReviewSummary> {
    const { data } = await http.get<WorkbenchSummaryDto>('/api/v1/review/workbench/summary')
    return {
      totalCount:data.total_count, pendingCount:data.pending_count, inReviewCount:data.in_review_count,
      actionRequiredCount:data.action_required_count, completedCount:data.completed_count, urgentCount:data.urgent_count,
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
}