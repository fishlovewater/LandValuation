import { afterEach, describe, expect, it, vi } from 'vitest'
import { http } from '../../src/api/http'
import { reviewApi, safeReviewErrorMessage } from '../../src/modules/review/review.api'

function conflictError(code: string) {
  return {
    isAxiosError: true,
    response: {
      status: 409,
      data: { error: { code } },
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
