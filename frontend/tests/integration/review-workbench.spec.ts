import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { http } from '../../src/api/http'
import { reviewApi } from '../../src/modules/review/review.api'
import FindingPanel from '../../src/modules/review/components/FindingPanel.vue'

describe('review workbench transport and states', () => {
  afterEach(() => vi.restoreAllMocks())

  it('maps BLOCKED start without inventing a validation run', async () => {
    vi.spyOn(http, 'post').mockResolvedValue({ data: {
      outcome: 'BLOCKED',
      completeness: {
        ready: false, review_status: 'PENDING_MATERIALS', missing_item_count: 1, blocked_rule_codes: ['R1'],
        items: [{ missing_item_id:'m1', review_id:'r1', item_code:'DOC', item_name:'土地登記資料', document_type:'land-register', severity:'HIGH', status:'OPEN', field_path:null, reason:'缺少必要文件', affected_rule_codes:['R1'], due_at:null, notified_at:null, notification_status:null, created_at:'2026-09-10T08:00:00+08:00' }],
      },
      run: null, findings: [], risk_summary: null,
    } } as never)

    const result = await reviewApi.startWorkbenchCase('r1')
    expect(result.outcome).toBe('BLOCKED')
    expect(result.run).toBeUndefined()
    expect(result.missingItems[0]?.itemName).toBe('土地登記資料')
  })

  it('requests authorized PDF content as a blob', async () => {
    const get = vi.spyOn(http, 'get').mockResolvedValue({ data: new Blob(['pdf'], { type:'application/pdf' }) } as never)
    const blob = await reviewApi.getDocumentContent('r1', 'd1')
    expect(blob.type).toBe('application/pdf')
    expect(get).toHaveBeenCalledWith('/api/v1/review/workbench/cases/r1/documents/d1/content', { responseType:'blob' })
  })

  it('keeps a selected finding visible with evidence metadata', () => {
    const wrapper = mount(FindingPanel, { props: { finding: {
      findingId:'f1', reviewId:'r1', runId:'run1', findingCode:'R1', findingType:'DIFF', severity:'WARNING', severityLabel:'警告', title:'單價差異', description:'申報值與系統值不同', status:'OPEN', documentId:'d1', documentVersion:1, pageNumber:3, fieldPath:'price', reportedValue:'10', systemGrade:'B', aiStatus:'COMPLETED',
    } } })
    expect(wrapper.text()).toContain('單價差異')
    expect(wrapper.text()).toContain('第 3 頁')
    expect(wrapper.text()).toContain('10')
  })
})