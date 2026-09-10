import { describe, expect, it } from 'vitest'
import { safeReviewErrorMessage } from '../../src/modules/review/review.api'

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
  it('turns known conflicts into actionable Chinese and hides unknown transport details', () => {
    expect(safeReviewErrorMessage(conflictError('FINDING_DECISION_CONFLICT')))
      .toBe('此疑點已被其他流程更新，請重新整理後確認目前狀態。')
    expect(safeReviewErrorMessage(conflictError('UNEXPECTED_BACKEND_CODE')))
      .toBe('案件狀態不允許此操作，請重新整理後確認。')
  })
})
