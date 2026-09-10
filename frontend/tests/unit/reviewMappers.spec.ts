import { describe, expect, it } from 'vitest'
import {
  documentTypeLabel,
  fieldPathLabel,
  latestGeneratedReport,
  mapDocument,
  mapWorkbenchDetail,
  mimeTypeLabel,
  selectEvidenceDocument,
  statusGroupLabel,
} from '../../src/modules/review/review.mappers'

const ids = {
  case: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  review: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  run: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  finding: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
}

describe('review mappers', () => {
  it('localizes review groups and technical evidence labels centrally', () => {
    expect(statusGroupLabel('in_progress')).toBe('處理中案件')
    expect(documentTypeLabel('original')).toBe('原始查估文件')
    expect(mimeTypeLabel('application/pdf')).toBe('PDF 文件')
    expect(fieldPathLabel('comparison.adjustment_rate')).toBe('調整率')
    expect(fieldPathLabel('unknown.path')).toBe('其他檢核欄位')
  })

  it('counts confirmed issues as unresolved until correction recheck', () => {
    const detail = mapWorkbenchDetail({
      case: {
        case_id: ids.case,
        case_no: 'NB-2026-0008',
        case_title: '測試案件',
        district_code: '新店區',
        valuation_base_date: '2026-08-01',
        case_status: 'IN_REVIEW',
      },
      review: {
        review_id: ids.review,
        case_id: ids.case,
        review_type: 'FORMAL',
        review_status: 'REVIEW_REQUIRED',
        started_by_user_id: null,
        started_at: '2026-09-07T01:00:00Z',
        completed_at: null,
        received_at: '2026-09-07T01:00:00Z',
        due_at: null,
        assigned_reviewer_id: null,
        manual_priority: 0,
        manual_priority_reason: null,
        current_risk_level: 'HIGH',
        high_count: 1,
        medium_count: 0,
        low_count: 0,
        missing_item_count: 0,
        latest_validation_run_id: ids.run,
        latest_submission_id: null,
      },
      submission_id: null,
      submission_no: null,
      submitted_at: null,
      input_fingerprint: null,
      documents: [],
      missing_items: [],
      runs: [{
        validation_run_id: ids.run,
        case_id: ids.case,
        review_id: ids.review,
        run_no: 1,
        run_status: 'COMPLETED',
        passed_count: 1,
        warning_count: 0,
        failed_count: 0,
        started_at: '2026-09-07T01:00:00Z',
        completed_at: '2026-09-07T01:01:00Z',
        triggered_by_user_id: null,
        rule_version_id: null,
        model_id: null,
        prompt_version: null,
        error_code: null,
        error_message: null,
      }],
      findings: [{
        finding_id: ids.finding,
        review_id: ids.review,
        validation_run_id: ids.run,
        finding_code: 'ADJUSTMENT_RATE',
        finding_type: 'RULE',
        severity: 'ERROR',
        title: '調整率',
        description: '需確認',
        status: 'CONFIRMED_ISSUE',
        document_id: null,
        document_version: null,
        page_number: null,
        field_path: 'comparison.adjustment_rate',
        source_evidence: [],
        reported_text: null,
        reported_value: '0.10',
        legal_basis: [],
        reported_grade: null,
        system_grade: null,
        reported_adjustment_rate: '0.10',
        system_adjustment_rate: '0.08',
        comparison_result: {},
        recommended_action: {},
        ai_reasoning_summary: null,
        ai_confidence: null,
        ai_status: 'READY',
        supersedes_finding_id: null,
        rule_version_id: null,
        created_at: '2026-09-07T01:01:00Z',
      }],
      risk_summary: null,
      decisions: [],
      version_diffs: [],
      report_document: null,
      generated_reports: [],
      correction_requests: [],
    })

    expect(detail.unresolvedFindingCount).toBe(1)
  })

  it('chooses the latest active original PDF and never falls back to correction files', () => {
    const documents = [
      { document_id: 'old', document_type: 'original', original_filename: 'old.pdf', mime_type: 'application/pdf', version_no: 1, is_active: false, uploaded_at: '2026-09-01T00:00:00Z' },
      { document_id: 'correction', document_type: 'correction-request', original_filename: 'correction.pdf', mime_type: 'application/pdf', version_no: 99, is_active: true, uploaded_at: '2026-09-06T00:00:00Z' },
      { document_id: 'latest', document_type: 'original', original_filename: 'latest.pdf', mime_type: 'application/pdf', version_no: 2, is_active: true, uploaded_at: '2026-09-05T00:00:00Z' },
    ]

    expect(selectEvidenceDocument(documents.map((document) => mapDocument(document)), 'old')?.documentId).toBe('latest')
    expect(mapDocument(documents[2]).documentTypeLabel).toBe('原始查估文件')
  })

  it('selects only review-report outputs when choosing the latest report', () => {
    expect(latestGeneratedReport([
      { document_id: 'correction', case_id: ids.case, document_type: 'correction-request', original_filename: 'correction.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', checksum_sha256: 'a', file_size_bytes: 1, version_no: 9 },
      { document_id: 'review', case_id: ids.case, document_type: 'review-report', original_filename: 'review-risk-report.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', checksum_sha256: 'b', file_size_bytes: 1, version_no: 2 },
    ])?.document_id).toBe('review')
  })
})
