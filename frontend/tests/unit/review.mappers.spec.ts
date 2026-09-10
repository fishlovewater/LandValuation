import { describe, expect, it } from 'vitest'

import { mapReviewCase, mapWorkbenchDetail, normalizeScalar } from '../../src/modules/review/review.mappers'

describe('review mappers', () => {
  it('maps queue DTOs while preserving raw enum diagnostics', () => {
    const result = mapReviewCase({
      review_id: 'r1', case_id: 'c1', case_no: 'CASE-001', title: '板橋案件', district: '板橋區',
      status: 'IN_REVIEW', overall_risk_level: 'HIGH', missing_item_count: 2,
      received_at: '2026-09-10T08:00:00+08:00', updated_at: '2026-09-10T09:00:00+08:00',
    })
    expect(result.reviewId).toBe('r1')
    expect(result.statusLabel).toBe('審查中')
    expect(result.riskLabel).toBe('高風險')
    expect(result.raw.status).toBe('IN_REVIEW')
  })

  it('does not crash on unknown enum or missing values', () => {
    const result = mapReviewCase({
      review_id: 'r2', case_id: 'c2', case_no: 'CASE-002', title: '未知狀態案件', district: null,
      status: 'NEW_BACKEND_STATUS', overall_risk_level: null, missing_item_count: 0,
      received_at: null, updated_at: '2026-09-10T09:00:00+08:00',
    })
    expect(result.statusLabel).toBe('未知狀態')
    expect(result.district).toBeUndefined()
    expect(result.raw.status).toBe('NEW_BACKEND_STATUS')
  })

  it('normalizes Decimal-like official values without changing meaning', () => {
    expect(normalizeScalar({ toString: () => '1234.50' })).toBe('1234.50')
    expect(normalizeScalar(null)).toBeUndefined()
  })

  it('keeps review, run, finding and document identifiers separate', () => {
    const detail = mapWorkbenchDetail({
      case: {
        review_id: 'review-1', case_id: 'case-1', case_no: 'A1', title: '案件', district: null,
        status: 'IN_REVIEW', overall_risk_level: 'MEDIUM', missing_item_count: 0,
        received_at: null, updated_at: '2026-09-10T09:00:00+08:00',
      },
      documents: [{ document_id: 'doc-1', document_group_id: 'g1', version_no: 1, document_type: 'original', original_filename: 'a.pdf', mime_type: 'application/pdf', file_size_bytes: 100, uploaded_at: '2026-09-10T09:00:00+08:00', content_available: true }],
      runs: [{ validation_run_id: 'run-1', case_id: 'case-1', trigger_type: 'MANUAL', status: 'COMPLETED', rule_version_id: null, created_at: '2026-09-10T09:00:00+08:00', completed_at: '2026-09-10T09:01:00+08:00' }],
      latest_findings: [{ finding_id: 'finding-1', rule_id: 'RULE-1', field_name: 'price', severity: 'WARNING', finding_type: 'DIFF', message: '差異', source_value: '10', recalculated_value: '11', difference_value: '1', status: 'PENDING', ai_explanation: null }],
      latest_risk_summary: null,
    })
    expect(detail.reviewId).toBe('review-1')
    expect(detail.runs[0]?.runId).toBe('run-1')
    expect(detail.findings[0]?.findingId).toBe('finding-1')
    expect(detail.documents[0]?.documentId).toBe('doc-1')
  })
})