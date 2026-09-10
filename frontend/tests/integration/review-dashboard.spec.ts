import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { http } from '../../src/api/http'
import { reviewApi } from '../../src/modules/review/review.api'
import ReviewCaseTable from '../../src/modules/review/components/ReviewCaseTable.vue'

describe('review dashboard transport and table', () => {
  afterEach(() => vi.restoreAllMocks())

  it('maps the current summary DTO and serializes only verified queue query params', async () => {
    const get = vi.spyOn(http, 'get')
    get.mockResolvedValueOnce({ data: { status_counts: { RECEIVED: 2, REVIEW_REQUIRED: 3, REVIEW_COMPLETED: 3 }, high_risk_count: 2, open_finding_count: 5, missing_item_count: 1 } } as never)
    const summary = await reviewApi.getWorkbenchSummary()
    expect(summary.totalCount).toBe(8)
    expect(summary.openFindingCount).toBe(5)

    get.mockResolvedValueOnce({ data: { items: [], total: 0, limit: 20, offset: 20 } } as never)
    await reviewApi.listWorkbenchCases({ q: '板橋', statusGroup: 'in_progress', riskLevel: 'HIGH', limit: 20, offset: 20 })
    expect(get).toHaveBeenLastCalledWith('/api/v1/review/workbench/cases', {
      params: { q: '板橋', status_group: 'in_progress', risk_level: 'HIGH', limit: 20, offset: 20 },
    })
  })

  it('emits the selected review id from a queue row', async () => {
    const wrapper = mount(ReviewCaseTable, { props: { items: [{
      reviewId:'r1', caseId:'c1', caseNo:'CASE-001', title:'板橋案件', district:'3101', status:'REVIEW_REQUIRED', statusLabel:'需人工審查', riskLevel:'HIGH', riskLabel:'高風險', missingItemCount:1,
      highCount:1, mediumCount:0, lowCount:0, receivedAt:'2026-09-10T08:00:00+08:00', dueAt:undefined, reviewerName:'審查員', latestRunId:'run-1', urgencyLevel:'NORMAL', remainingDays:3, correctionRound:0,
      raw:{status:'REVIEW_REQUIRED',riskLevel:'HIGH'},
    }] } })
    await wrapper.get('button[data-review-id="r1"]').trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual(['r1'])
  })
})
