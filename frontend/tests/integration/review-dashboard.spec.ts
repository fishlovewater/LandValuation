import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { http } from '../../src/api/http'
import { reviewApi } from '../../src/modules/review/review.api'
import ReviewCaseTable from '../../src/modules/review/components/ReviewCaseTable.vue'

describe('review dashboard transport and table', () => {
  afterEach(() => vi.restoreAllMocks())

  it('maps the real summary DTO and serializes only verified queue query params', async () => {
    const get = vi.spyOn(http, 'get')
    get.mockResolvedValueOnce({ data: { total_count: 8, pending_count: 2, in_review_count: 3, action_required_count: 1, completed_count: 2, urgent_count: 1 } } as never)
    const summary = await reviewApi.getWorkbenchSummary()
    expect(summary.totalCount).toBe(8)

    get.mockResolvedValueOnce({ data: { items: [], total: 0, limit: 20, offset: 20 } } as never)
    await reviewApi.listWorkbenchCases({ q: '板橋', statusGroup: 'ACTIVE', riskLevel: 'HIGH', limit: 20, offset: 20 })
    expect(get).toHaveBeenLastCalledWith('/api/v1/review/workbench/cases', {
      params: { q: '板橋', status_group: 'ACTIVE', risk_level: 'HIGH', limit: 20, offset: 20 },
    })
  })

  it('emits the selected review id from a queue row', async () => {
    const wrapper = mount(ReviewCaseTable, { props: { items: [{
      reviewId:'r1', caseId:'c1', caseNo:'CASE-001', title:'板橋案件', district:'板橋區', status:'IN_REVIEW', statusLabel:'審查中', riskLevel:'HIGH', riskLabel:'高風險', missingItemCount:1, updatedAt:'2026-09-10T09:00:00+08:00', raw:{status:'IN_REVIEW',riskLevel:'HIGH'},
    }] } })
    await wrapper.get('button[data-review-id="r1"]').trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual(['r1'])
  })
})