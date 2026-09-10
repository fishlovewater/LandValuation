import { describe, expect, it } from 'vitest'

import { mapReviewCase, mapWorkbenchDetail, normalizeScalar } from '../../src/modules/review/review.mappers'
import type { WorkbenchDetailDto } from '../../src/modules/review/review.types'

const queueItem = {
  review_id: 'r1', case_id: 'c1', case_no: 'CASE-001', case_title: '板橋案件', district_code: '3101',
  review_status: 'REVIEW_REQUIRED', current_risk_level: 'HIGH', missing_item_count: 2,
  high_count: 1, medium_count: 2, low_count: 0, received_at: '2026-09-10T08:00:00+08:00', due_at: null,
  assigned_reviewer_display_name: '王審查員', latest_run: { validation_run_id: 'run-1', run_no: 1, run_status: 'COMPLETED' },
  urgency_level: 'NORMAL' as const, remaining_days: 3, correction_round: 0, latest_correction_status: null,
}

function detailFixture(): WorkbenchDetailDto {
  return {
    case: { case_id:'c1', case_no:'CASE-001', case_title:'板橋案件', district_code:'3101', valuation_base_date:'2026-09-01', case_status:'SUBMITTED' },
    review: {
      review_id:'r1', case_id:'c1', review_type:'SMART', review_status:'REVIEW_REQUIRED', started_by_user_id:null,
      started_at:'2026-09-10T08:00:00+08:00', completed_at:null, received_at:'2026-09-10T08:00:00+08:00', due_at:null,
      assigned_reviewer_id:null, manual_priority:0, manual_priority_reason:null, current_risk_level:'HIGH', high_count:1,
      medium_count:0, low_count:0, missing_item_count:0, latest_validation_run_id:'run-1',
    },
    documents:[{ document_id:'doc-1', document_type:'original', original_filename:'a.pdf', mime_type:'application/pdf', version_no:1, is_active:true, uploaded_at:'2026-09-10T08:00:00+08:00' }],
    missing_items:[],
    runs:[{ validation_run_id:'run-1', case_id:'c1', review_id:'r1', run_no:1, run_status:'COMPLETED', passed_count:10, warning_count:1, failed_count:0, started_at:'2026-09-10T08:00:00+08:00', completed_at:'2026-09-10T08:01:00+08:00', triggered_by_user_id:null, rule_version_id:null, input_snapshot:{}, model_id:null, prompt_version:null, error_code:null, error_message:null }],
    findings:[{ finding_id:'finding-1', review_id:'r1', validation_run_id:'run-1', finding_code:'RULE-1', finding_type:'DIFF', severity:'WARNING', title:'單價差異', description:'系統計算與申報不同', status:'OPEN', document_id:'doc-1', document_version:1, page_number:2, field_path:'price', source_evidence:[], reported_text:'10', reported_value:'10', legal_basis:[], reported_grade:null, system_grade:null, reported_adjustment_rate:'0.10', system_adjustment_rate:'0.12', comparison_result:{}, recommended_action:{}, ai_reasoning_summary:null, ai_confidence:'0.92', ai_status:'COMPLETED', supersedes_finding_id:null, rule_version_id:null, created_at:'2026-09-10T08:01:00+08:00' }],
    risk_summary:null, decisions:[], version_diffs:[], report_document:null, generated_reports:[], correction_requests:[],
  }
}

describe('review mappers', () => {
  it('maps the current queue DTO while preserving raw enum diagnostics', () => {
    const result = mapReviewCase(queueItem)
    expect(result.reviewId).toBe('r1')
    expect(result.statusLabel).toBe('需人工審查')
    expect(result.riskLabel).toBe('高風險')
    expect(result.raw.status).toBe('REVIEW_REQUIRED')
  })

  it('does not crash on unknown enum or missing values', () => {
    const result = mapReviewCase({ ...queueItem, review_id:'r2', review_status:'NEW_BACKEND_STATUS', current_risk_level:null, district_code:'' })
    expect(result.statusLabel).toBe('未知狀態')
    expect(result.district).toBeUndefined()
    expect(result.raw.status).toBe('NEW_BACKEND_STATUS')
  })

  it('normalizes Decimal-like official values without changing meaning', () => {
    expect(normalizeScalar({ toString: () => '1234.50' })).toBe('1234.50')
    expect(normalizeScalar(null)).toBeUndefined()
  })

  it('keeps review, run, finding and document identifiers separate', () => {
    const detail = mapWorkbenchDetail(detailFixture())
    expect(detail.reviewId).toBe('r1')
    expect(detail.runs[0]?.runId).toBe('run-1')
    expect(detail.findings[0]?.findingId).toBe('finding-1')
    expect(detail.documents[0]?.documentId).toBe('doc-1')
  })
})
