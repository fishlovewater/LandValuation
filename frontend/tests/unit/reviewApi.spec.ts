import { afterEach, describe, expect, it, vi } from 'vitest'
import { http } from '../../src/api/http'
import { reviewApi, safeReviewErrorMessage } from '../../src/modules/review/review.api'

function conflictError(code: string, details?: Record<string, unknown>) {
  return {
    isAxiosError: true,
    response: {
      status: 409,
      data: { error: { code, details } },
    },
  }
}

describe('review API error messages', () => {
  const originalAdapter = http.defaults.adapter

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    vi.restoreAllMocks()
  })

  it('turns known conflicts into actionable Chinese and hides unknown transport details', () => {
    expect(safeReviewErrorMessage(conflictError('FINDING_DECISION_CONFLICT')))
      .toBe('此疑點已被其他流程更新，請重新整理後確認目前狀態。')
    expect(safeReviewErrorMessage(conflictError('UNEXPECTED_BACKEND_CODE')))
      .toBe('案件狀態不允許此操作，請重新整理後確認。')
  })

  it('explains whole-case OCR blockers with the pending field count', () => {
    expect(safeReviewErrorMessage(conflictError(
      'REVIEW_OCR_CONFIRMATION_REQUIRED',
      { pending_external_field_count: 3 },
    ))).toBe('案件仍有 3 筆辨識欄位尚未完成確認並填表或排除。請檢查案件全部有效文件後再開始智慧審查。')
  })

  it('submits the supplement due date through the existing completeness endpoint', async () => {
    const reviewId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    const dueAt = '2026-09-18T02:00:00.000Z'
    let captured: Record<string, unknown> | null = null

    http.defaults.adapter = vi.fn(async (config) => {
      expect(config.method).toBe('post')
      expect(config.url).toBe(`/review/cases/${reviewId}/supplement-request`)
      captured = JSON.parse(String(config.data)) as Record<string, unknown>
      return { data: [], status: 200, statusText: 'OK', headers: {}, config }
    }) as unknown as typeof originalAdapter

    await reviewApi.requestSupplement(reviewId, dueAt)
    expect(captured).toEqual({ due_at: dueAt })
  })
})
