import { describe, expect, it } from 'vitest'
import { REVIEW_REQUIRED_CAPABILITIES } from '../../src/types/capability'

describe('Review MVP capability boundary', () => {
  it('requires only verified auth and review capabilities', () => {
    expect(REVIEW_REQUIRED_CAPABILITIES).toEqual({
      authLogin: true,
      authMe: true,
      reviewSummary: true,
      reviewCases: true,
      reviewDetail: true,
      reviewStart: true,
      reviewDecision: true,
      reviewCompletion: true,
      reviewReport: true,
    })
  })
})
