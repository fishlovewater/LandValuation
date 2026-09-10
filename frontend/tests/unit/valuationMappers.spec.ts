import { describe, expect, it } from 'vitest'
import {
  mapDocumentResponse,
  mapFormalReportResponse,
  mapFormResponse,
  selectAuthoritativeF02,
} from '../../src/modules/valuation/valuation.mappers'

const ids = {
  case: '11111111-1111-4111-8111-111111111111',
  form: '12121212-1212-4121-8121-121212121212',
  report: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  document: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
}

function formDto(reportType: string) {
  return {
    form_instance_id: ids.form,
    case_id: ids.case,
    form_code: 'F02' as const,
    version_no: 4,
    form_status: 'FINAL' as const,
    form_content: {
      report_type: reportType,
      report_id: ids.report,
    },
    prepared_date: '2026-09-07',
    source_document_id: null,
    output_document_id: ids.document,
    created_by_user_id: null,
    updated_by_user_id: null,
    created_at: '2026-09-07T01:00:00Z',
    updated_at: '2026-09-07T02:00:00Z',
  }
}

const checkedFormDto = {
  ...formDto('REPORT_COMPARISON_COMMERCIAL'),
  form_status: 'CHECKED' as const,
}

const documentDto = {
  document_id: ids.document,
  document_group_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  case_id: ids.case,
  document_type: 'complete-valuation-report',
  original_filename: 'complete-report.pdf',
  mime_type: 'application/pdf',
  bucket_name: 'internal',
  object_key: 'cases/complete-report.pdf',
  checksum_sha256: 'checksum',
  file_size_bytes: 1024,
  storage_etag: null,
  version_no: 4,
  uploaded_by_user_id: null,
  uploaded_at: '2026-09-07T02:00:00Z',
  is_active: true,
}

const reportProgress = {
  report_id: ids.report,
  report_type: 'REPORT_COMPARISON_COMMERCIAL',
  version_no: 4,
  completion_rate: '100.00',
  sections: [],
  blocking_errors: [],
}

describe('valuation F02 authority mapper', () => {
  it('selects a compatible CHECKED commercial F02 as a resumable formal package', () => {
    const selection = selectAuthoritativeF02(
      [mapFormResponse(checkedFormDto)],
      [mapDocumentResponse(documentDto)],
      reportProgress,
    )

    expect(selection.form?.status).toBe('CHECKED')
    expect(selection.completeReport?.documentId).toBe(ids.document)
    expect(selection.reportPackageId).toBe(ids.report)
  })

  it('keeps a CHECKED package resumable when formal output has not been bound yet', () => {
    const selection = selectAuthoritativeF02(
      [mapFormResponse({ ...checkedFormDto, output_document_id: null })],
      [],
      reportProgress,
    )

    expect(selection.form?.status).toBe('CHECKED')
    expect(selection.completeReport).toBeNull()
    expect(selection.reportPackageId).toBe(ids.report)
  })

  it('rejects a final F02 whose report type is not the supported commercial report', () => {
    const selection = selectAuthoritativeF02(
      [mapFormResponse(formDto('REPORT_UNSUPPORTED'))],
      [mapDocumentResponse(documentDto)],
      reportProgress,
    )

    expect(selection.form).toBeNull()
    expect(selection.completeReport).toBeNull()
    expect(selection.reportPackageId).toBeNull()
  })

  it('preserves the formal PDF provenance returned by the server', () => {
    const report = mapFormalReportResponse({
      document_id: ids.document,
      case_id: ids.case,
      report_id: ids.report,
      validation_run_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      filename: 'complete-report-v5.pdf',
      mime_type: 'application/pdf',
      version_no: 5,
      bucket_name: 'internal',
      object_key: 'cases/formal-report.pdf',
      checksum_sha256: 'checksum-v5',
      file_size_bytes: 4096,
      download_path: `/valuation/cases/${ids.case}/complete-reports/${ids.document}/download`,
      request_id: null,
    })

    expect(report).toEqual({
      documentId: ids.document,
      caseId: ids.case,
      reportId: ids.report,
      validationRunId: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      filename: 'complete-report-v5.pdf',
      mimeType: 'application/pdf',
      versionNo: 5,
      fileSizeBytes: 4096,
      downloadPath: `/valuation/cases/${ids.case}/complete-reports/${ids.document}/download`,
    })
  })
})
