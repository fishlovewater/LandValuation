import { describe, expect, it } from 'vitest'
import {
  correctionStatusLabel,
  documentTypeLabel,
  fieldPathLabel,
  findingCodeLabel,
  findingTypeLabel,
  latestGeneratedReport,
  mapDocument,
  mapVersionDiff,
  mapWorkbenchCase,
  mapWorkbenchDetail,
  mimeTypeLabel,
  missingItemStatusLabel,
  selectEvidenceDocument,
  statusGroupLabel,
  verificationStatusLabel,
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
    expect(fieldPathLabel('comparables[0].adjustment_rate')).toBe('調整率')
    expect(fieldPathLabel('unknown.path')).toBe('相關必要欄位')
    expect(missingItemStatusLabel('VERIFIED')).toBe('已確認')
    expect(correctionStatusLabel('RESUBMITTED')).toBe('已重新送審')
    expect(verificationStatusLabel('APPLIED')).toBe('已確認並套用')
    expect(findingCodeLabel('F03_WEIGHT_SUM')).toBe('F03 權重檢核')
    expect(findingTypeLabel('F03_WEIGHT_SUM_MISMATCH')).toBe('F03 權重規則檢核')
    expect(findingTypeLabel('EXPERT_GRADE_JUDGMENT')).toBe('級距專業覆核')
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
      case_source: 'PLATFORM',
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
        finding_code: '11111111-1111-4111-8111-111111111111:22222222-2222-4222-8222-222222222222',
        finding_type: 'RATE_OUT_OF_RANGE',
        severity: 'ERROR',
        title: '調整率',
        description: '需確認',
        status: 'CONFIRMED_ISSUE',
        document_id: null,
        document_version: null,
        page_number: null,
        field_path: 'comparison.adjustment_rate',
        source_evidence: [{
          field_code: 'ADJUSTMENT_RATE',
          extracted_field_id: 'internal-extracted-field-id',
          verification_status: 'APPLIED',
        }],
        reported_text: null,
        reported_value: '0.10',
        legal_basis: [{
          rule_code: 'ADJUSTMENT_RATE',
          rule_name: '調整率一致性檢核',
        }],
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
    expect(detail.districtLabel).toBe('新店區')
    expect(detail.caseSourceCode).toBe('PLATFORM')
    expect(detail.caseSourceLabel).toBe('平台送審')
    expect(detail.findings[0].sourceEvidence[0].title).toBe('資料來源｜調整率')
    expect(detail.findings[0].sourceEvidence[0].title).not.toContain('internal-extracted-field-id')
    expect(detail.findings[0].findingCodeLabel).toBe('調整率')
    expect(detail.findings[0].findingTypeLabel).toBe('調整率規則檢核')
    expect(detail.findings[0].findingCodeLabel).not.toContain('11111111')
  })

  it('maps district codes to readable names in the review queue', () => {
    const item = mapWorkbenchCase({
      review_id: ids.review,
      case_id: ids.case,
      case_no: 'NB-2026-0009',
      case_title: '行政區顯示測試',
      district_code: '65000060',
      case_source: 'PLATFORM',
      review_status: 'REVIEW_REQUIRED',
      current_risk_level: 'LOW',
      high_count: 0,
      medium_count: 0,
      low_count: 1,
      missing_item_count: 0,
      received_at: '2026-09-07T01:00:00Z',
      due_at: null,
      assigned_reviewer_display_name: null,
      urgency_level: 'NORMAL',
      remaining_days: null,
      correction_round: 0,
      latest_correction_status: null,
      latest_run: null,
    })

    expect(item.district).toBe('新店區')
  })

  it('uses the exact finding document and never substitutes another PDF', () => {
    const documents = [
      { document_id: 'old', document_type: 'original', original_filename: 'old.pdf', mime_type: 'application/pdf', version_no: 1, is_active: false, uploaded_at: '2026-09-01T00:00:00Z' },
      { document_id: 'correction', document_type: 'correction-request', original_filename: 'correction.pdf', mime_type: 'application/pdf', version_no: 99, is_active: true, uploaded_at: '2026-09-06T00:00:00Z' },
      { document_id: 'latest', document_type: 'original', original_filename: 'latest.pdf', mime_type: 'application/pdf', version_no: 2, is_active: true, uploaded_at: '2026-09-05T00:00:00Z' },
    ]
    const mapped = documents.map((document) => mapDocument(document))

    expect(selectEvidenceDocument(mapped, 'old')?.documentId).toBe('old')
    expect(selectEvidenceDocument(mapped, 'missing')).toBeNull()
    expect(selectEvidenceDocument(mapped, null)?.documentId).toBe('latest')
    expect(mapDocument(documents[2]).documentTypeLabel).toBe('原始查估文件')
  })

  it('selects only review-report outputs when choosing the latest report', () => {
    expect(latestGeneratedReport([
      { document_id: 'correction', case_id: ids.case, document_type: 'correction-request', original_filename: 'correction.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', checksum_sha256: 'a', file_size_bytes: 1, version_no: 9 },
      { document_id: 'review', case_id: ids.case, document_type: 'review-report', original_filename: 'review-risk-report.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', checksum_sha256: 'b', file_size_bytes: 1, version_no: 2 },
    ])?.document_id).toBe('review')
  })

  it('maps backend version diffs into explicit before/after values for the reviewer', () => {
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
        current_risk_level: 'MEDIUM',
        high_count: 0,
        medium_count: 1,
        low_count: 0,
        missing_item_count: 0,
        latest_validation_run_id: ids.run,
      },
      case_source: 'EXTERNAL',
      submission_id: null,
      submission_no: null,
      submitted_at: null,
      input_fingerprint: null,
      documents: [],
      missing_items: [],
      runs: [],
      findings: [],
      risk_summary: null,
      decisions: [],
      version_diffs: [{
        document_group_id: '12121212-1212-4121-8121-121212121212',
        field_code: 'ADJUSTMENT_RATE',
        field_path: 'comparison.adjustment_rate',
        previous: {
          document_id: '13131313-1313-4131-8131-131313131313',
          document_group_id: '12121212-1212-4121-8121-121212121212',
          document_version: 1,
          field_code: 'ADJUSTMENT_RATE',
          field_path: 'comparison.adjustment_rate',
          normalized_value: '-12',
          raw_text: '調整率 -12%',
          page_number: 3,
        },
        current: {
          document_id: '14141414-1414-4141-8141-141414141414',
          document_group_id: '12121212-1212-4121-8121-121212121212',
          document_version: 2,
          field_code: 'ADJUSTMENT_RATE',
          field_path: 'comparison.adjustment_rate',
          normalized_value: '-5',
          raw_text: '調整率 -5%',
          page_number: 3,
        },
      }],
      report_document: null,
      generated_reports: [],
      correction_requests: [],
    })

    expect(detail.versionDiffs).toEqual([
      expect.objectContaining({
        fieldLabel: '調整率',
        previousDocumentVersion: 1,
        previousValue: '-12',
        currentDocumentVersion: 2,
        currentValue: '-5',
      }),
    ])
    expect(detail.caseSourceCode).toBe('EXTERNAL')
    expect(detail.caseSourceLabel).toBe('外部案件')
  })

  it('summarizes structured version-diff values without exposing backend field names', () => {
    const mapped = mapVersionDiff({
      document_group_id: '12121212-1212-4121-8121-121212121212',
      field_code: 'ADJUSTMENT_RATE',
      field_path: 'comparison.adjustment_rate',
      previous: {
        document_id: '13131313-1313-4131-8131-131313131313',
        document_group_id: '12121212-1212-4121-8121-121212121212',
        document_version: 1,
        field_code: 'ADJUSTMENT_RATE',
        field_path: 'comparison.adjustment_rate',
        normalized_value: { before_value: '舊值', provider: 'ollama' },
        raw_text: null,
        page_number: 3,
      },
      current: {
        document_id: '14141414-1414-4141-8141-141414141414',
        document_group_id: '12121212-1212-4121-8121-121212121212',
        document_version: 2,
        field_code: 'ADJUSTMENT_RATE',
        field_path: 'comparison.adjustment_rate',
        normalized_value: { after_value: '新值', model_id: 'internal-model' },
        raw_text: null,
        page_number: 3,
      },
    })

    expect(mapped.previousValue).toBe('修改前內容：舊值')
    expect(mapped.currentValue).toBe('修改後內容：新值')
    expect(mapped.previousValue).not.toContain('before_value')
    expect(mapped.currentValue).not.toContain('model_id')
    expect(mapped.currentValue).not.toContain('{')
  })
})
