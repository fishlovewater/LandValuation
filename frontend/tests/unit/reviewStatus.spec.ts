import { describe, expect, it } from 'vitest'
import {
  canMutateExternalReviewInput,
  reviewInteractionMode,
} from '../../src/modules/review/review.status'

describe('review status policy', () => {
  it('keeps pending and in-progress review states editable', () => {
    expect(reviewInteractionMode('RECEIVED')).toBe('EDITABLE')
    expect(reviewInteractionMode('READY_FOR_REVIEW')).toBe('EDITABLE')
    expect(reviewInteractionMode('REVIEW_REQUIRED')).toBe('EDITABLE')
    expect(reviewInteractionMode('EXPERT_REVIEW')).toBe('EDITABLE')
  })

  it('treats supplement and correction states as limited', () => {
    expect(reviewInteractionMode('PENDING_MATERIALS')).toBe('LIMITED')
    expect(reviewInteractionMode('RETURNED_FOR_REVISION')).toBe('LIMITED')
    expect(reviewInteractionMode('SUPPLEMENT_REQUIRED')).toBe('LIMITED')
  })

  it('treats completed and legacy/unknown states as fail-safe read-only', () => {
    expect(reviewInteractionMode('REVIEW_COMPLETED')).toBe('READ_ONLY')
    expect(reviewInteractionMode('APPROVED')).toBe('READ_ONLY')
    expect(reviewInteractionMode('RUNNING')).toBe('READ_ONLY')
    expect(reviewInteractionMode('COMPLETED')).toBe('READ_ONLY')
    expect(reviewInteractionMode('UNKNOWN')).toBe('READ_ONLY')
  })

  it('allows external input mutation only in intake/recovery states', () => {
    expect(canMutateExternalReviewInput('RECEIVED')).toBe(true)
    expect(canMutateExternalReviewInput('RETURNED_FOR_REVISION')).toBe(true)
    expect(canMutateExternalReviewInput('REVIEW_REQUIRED')).toBe(false)
    expect(canMutateExternalReviewInput('REVIEW_COMPLETED')).toBe(false)
  })
})