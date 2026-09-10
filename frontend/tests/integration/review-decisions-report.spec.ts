import { afterEach, describe, expect, it, vi } from 'vitest'

import { http } from '../../src/api/http'
import { reviewApi } from '../../src/modules/review/review.api'

describe('review decisions, corrections and reports', () => {
  afterEach(() => vi.restoreAllMocks())

  it('uses the verified finding triage endpoint and sends only human decision input', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: { decision_id:'d1', review_id:'r1', finding_id:'f1', decision:'CONFIRMED_ISSUE', reason:'申報內容與證據不一致', decided_by_user_id:'u1', decided_at:'2026-09-10T09:00:00+08:00', request_id:null, before_value:null, after_value:null } } as never)
    await reviewApi.triageFinding('r1', 'f1', 'CONFIRMED_ISSUE', '申報內容與證據不一致')
    expect(post).toHaveBeenCalledWith('/api/v1/review/findings/f1/triage', {
      review_id:'r1', decision:'CONFIRMED_ISSUE', reason:'申報內容與證據不一致',
    })
  })

  it('creates and sends a correction request with a timezone-aware due date', async () => {
    const post = vi.spyOn(http, 'post')
      .mockResolvedValueOnce({ data: { correction_request_id:'cr1' } } as never)
      .mockResolvedValueOnce({ data: { correction_request_id:'cr1' } } as never)
    await reviewApi.createAndSendCorrection('r1', '請補正土地登記資料', '2026-09-15T17:00:00+08:00')
    expect(post).toHaveBeenNthCalledWith(1, '/api/v1/review/cases/r1/correction-requests', { message:'請補正土地登記資料', due_at:'2026-09-15T17:00:00+08:00' })
    expect(post).toHaveBeenNthCalledWith(2, '/api/v1/review/correction-requests/cr1/send', {})
  })

  it('completes review and fetches/downloads reports without object keys', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: { decision_id:'d2' } } as never)
    await reviewApi.completeReview('r1', '疑點均已處理')
    expect(post).toHaveBeenCalledWith('/api/v1/review/cases/r1/complete-review', { reason:'疑點均已處理' })

    const get = vi.spyOn(http, 'get').mockResolvedValue({ data: new Blob(['pdf'], { type:'application/pdf' }) } as never)
    const blob = await reviewApi.downloadReport('doc1')
    expect(blob.type).toBe('application/pdf')
    expect(get).toHaveBeenCalledWith('/api/v1/review/reports/doc1/download', { responseType:'blob' })
  })
})