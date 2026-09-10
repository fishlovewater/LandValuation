import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { AxiosError } from 'axios'
import AppLayout from '../../src/layouts/AppLayout.vue'
import { http, tokenService } from '../../src/api/http'
import { createAppRouter } from '../../src/router'
import type { AuthUser } from '../../src/modules/auth/auth.types'
import { useAuthStore } from '../../src/stores/auth.store'
import { resetValuationFlow, valuationFlowState } from '../../src/modules/valuation/valuation.types'
import {
  mapCaseResponse,
  mapDocumentResponse,
  mapFormalReportResponse,
  mapFormalValidationResponse,
  mapFormResponse,
  mapReportResponse,
  mapValidationResponse,
} from '../../src/modules/valuation/valuation.mappers'

const ids = {
  case: '11111111-1111-4111-8111-111111111111',
  f02: '12121212-1212-4121-8121-121212121212',
  f03: '22222222-2222-4222-8222-222222222222',
  benchmarkValuation: '33333333-3333-4333-8333-333333333333',
  benchmarkLand: '44444444-4444-4444-8444-444444444444',
  parcel: '55555555-5555-4555-8555-555555555555',
  sourceDocument: '66666666-6666-4666-8666-666666666666',
  calculation: '77777777-7777-4777-8777-777777777777',
  validationRun: '88888888-8888-4888-8888-888888888888',
  formalValidationRun: '88888888-8888-4888-8888-888888888889',
  finding: '99999999-9999-4999-8999-999999999999',
  f03Report: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  completeReport: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab',
  formalReport: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaf',
  reportPackage: '12121212-1212-4121-8121-121212121212',
  submission: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  review: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
}

const appraiser: AuthUser = {
  id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  username: 'appraiser.demo',
  email: 'appraiser@example.test',
  displayName: '示範估價人員',
  roles: ['APPRAISER'],
  permissions: [
    'case.read',
    'valuation.read',
    'valuation.update',
    'valuation.submit_review',
    'document.download',
  ],
}

const caseDto = {
  case_id: ids.case,
  case_no: 'NB-2026-0001',
  case_title: '新店區安康段土地估價',
  case_type: 'LAND_VALUATION',
  requesting_agency: '新北市政府',
  valuation_base_date: '2026-08-01',
  city_code: '65000',
  district_code: '65000030',
  land_use_type: '住宅區',
  case_status: 'PROCESSING',
  created_by_user_id: appraiser.id,
  updated_by_user_id: appraiser.id,
  created_at: '2026-09-07T01:00:00Z',
  updated_at: '2026-09-07T02:00:00Z',
}

const formDto = {
  form_instance_id: ids.f03,
  case_id: ids.case,
  form_code: 'F03',
  version_no: 4,
  form_status: 'DRAFT',
  form_content: {},
  prepared_date: '2026-09-07',
  source_document_id: ids.sourceDocument,
  output_document_id: null,
  created_by_user_id: appraiser.id,
  updated_by_user_id: appraiser.id,
  created_at: '2026-09-07T01:10:00Z',
  updated_at: '2026-09-07T02:00:00Z',
}

const submittedF03FormDto = {
  ...formDto,
  form_status: 'READY',
  updated_at: '2026-09-07T03:00:10Z',
}

const authoritativeFormDto = {
  form_instance_id: ids.f02,
  case_id: ids.case,
  form_code: 'F02',
  version_no: 4,
  form_status: 'FINAL',
  form_content: {
    report_type: 'REPORT_COMPARISON_COMMERCIAL',
    report_id: ids.reportPackage,
  },
  prepared_date: '2026-09-07',
  source_document_id: ids.sourceDocument,
  output_document_id: ids.completeReport,
  created_by_user_id: appraiser.id,
  updated_by_user_id: appraiser.id,
  created_at: '2026-09-07T01:10:00Z',
  updated_at: '2026-09-07T02:00:00Z',
}

const f03Dto = {
  benchmark_valuation_id: ids.benchmarkValuation,
  case_id: ids.case,
  benchmark_land_id: ids.benchmarkLand,
  comparison_analysis_id: null,
  form_instance_id: ids.f03,
  valuation_base_date: '2026-08-01',
  comparison_price: '125000.00',
  comparison_weight: '0.60',
  income_price: '118000.00',
  income_weight: '0.40',
  benchmark_land_price: '122200.00',
  market_period_start: '2025-01-01',
  market_period_end: '2026-08-01',
  market_condition: '市場平穩',
  selection_scope_reason: '同區段近鄰案例',
  decision_reason: '依現勘與市場資料確認',
  version_no: 4,
  valuation_status: 'DRAFT',
  created_at: '2026-09-07T01:10:00Z',
  updated_at: '2026-09-07T02:00:00Z',
}

const benchmarkDto = {
  benchmark_land_id: ids.benchmarkLand,
  case_id: ids.case,
  parcel_id: ids.parcel,
  benchmark_land_no: '基準地-001',
  price_zone_no: 'Z-01',
  land_consolidation_serial: null,
  latitude: '24.9567',
  longitude: '121.5034',
  is_active: true,
  created_at: '2026-09-07T01:00:00Z',
  updated_at: '2026-09-07T01:00:00Z',
}

const calculationDto = {
  calculation_id: ids.calculation,
  case_id: ids.case,
  form_instance_id: ids.f03,
  benchmark_valuation_id: ids.benchmarkValuation,
  formula_version: 'F03_WEIGHTED_PRICE_V1',
  result: '123456.00',
  currency_code: 'TWD',
  calculation_snapshot: { source: 'server' },
  request_id: null,
  calculated_at: '2026-09-07T03:00:00Z',
}

const validationDto = {
  validation_run_id: ids.validationRun,
  case_id: ids.case,
  form_instance_id: ids.f03,
  run_status: 'COMPLETED',
  passed_count: 8,
  warning_count: 1,
  failed_count: 0,
  can_generate_report: true,
  ruleset_version: 'F03_MVP:v1',
  correction_hints: [],
  findings: [
    {
      finding_id: ids.finding,
      rule_code: 'F03-W-001',
      rule_version: 'F03_MVP:v1',
      field_path: 'market_condition',
      severity: 'WARNING',
      actual_value: '市場平穩',
      expected_value: '人工覆核',
      message: '市場條件已由伺服器標示為警示，請確認來源。',
      request_id: null,
      created_at: '2026-09-07T03:00:00Z',
    },
  ],
  request_id: null,
  started_at: '2026-09-07T02:59:00Z',
  completed_at: '2026-09-07T03:00:00Z',
}

const blockedValidationDto = {
  ...validationDto,
  validation_run_id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
  passed_count: 7,
  warning_count: 0,
  failed_count: 1,
  can_generate_report: false,
  findings: [
    {
      finding_id: ids.finding,
      rule_code: 'F03-E-001',
      rule_version: 'F03_MVP:v1',
      field_path: 'decision_reason',
      severity: 'ERROR',
      actual_value: null,
      expected_value: 'required',
      message: '採用決策理由尚未完成。',
      request_id: null,
      created_at: '2026-09-07T03:00:00Z',
    },
  ],
}

const reportDto = {
  document_id: ids.f03Report,
  case_id: ids.case,
  form_instance_id: ids.f03,
  validation_run_id: ids.validationRun,
  calculation_id: ids.calculation,
  filename: 'F03_NB-2026-0001.pdf',
  mime_type: 'application/pdf',
  version_no: 1,
  bucket_name: 'internal-bucket-must-not-render',
  object_key: 'cases/internal/f03-object-key-must-not-render.pdf',
  checksum_sha256: 'f03-not-rendered',
  file_size_bytes: 2048,
  download_path: `/valuation/cases/${ids.case}/reports/${ids.f03Report}/download`,
  request_id: null,
}

const documentsDto = [
  {
    document_id: ids.f03Report,
    document_group_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaac',
    case_id: ids.case,
    document_type: 'generated-report',
    original_filename: 'F03_NB-2026-0001.pdf',
    mime_type: 'application/pdf',
    bucket_name: 'internal-bucket-must-not-render',
    object_key: 'cases/internal/f03-object-key-must-not-render.pdf',
    checksum_sha256: 'f03-not-rendered',
    file_size_bytes: 2048,
    storage_etag: null,
    version_no: 1,
    uploaded_by_user_id: appraiser.id,
    uploaded_at: '2026-09-07T03:00:00Z',
    is_active: true,
  },
  {
    document_id: ids.completeReport,
    document_group_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaad',
    case_id: ids.case,
    document_type: 'complete-valuation-report',
    original_filename: 'complete_valuation_report_NB-2026-0001_v4.pdf',
    mime_type: 'application/pdf',
    bucket_name: 'internal-bucket-must-not-render',
    object_key: 'cases/internal/complete-object-key-must-not-render.pdf',
    checksum_sha256: 'complete-not-rendered',
    file_size_bytes: 4096,
    storage_etag: null,
    version_no: 4,
    uploaded_by_user_id: appraiser.id,
    uploaded_at: '2026-09-07T02:30:00Z',
    is_active: true,
  },
]

const formalDocumentDto = {
  ...documentsDto[1],
  document_id: ids.formalReport,
  original_filename: 'complete_valuation_report_NB-2026-0001_v5.pdf',
  object_key: 'cases/internal/formal-object-key-must-not-render.pdf',
  checksum_sha256: 'formal-not-rendered',
  file_size_bytes: 8192,
  version_no: 5,
}

const formalAuthoritativeFormDto = {
  ...authoritativeFormDto,
  output_document_id: ids.formalReport,
}

const checkedAuthoritativeFormDto = {
  ...authoritativeFormDto,
  form_status: 'CHECKED',
  output_document_id: null,
}

const reportProgressDto = {
  report_id: ids.reportPackage,
  report_type: 'REPORT_COMPARISON_COMMERCIAL',
  version_no: 4,
  completion_rate: '100.00',
  sections: [],
  blocking_errors: [],
}

const formalValidationDto = {
  validation_run_id: ids.formalValidationRun,
  case_id: ids.case,
  report_id: ids.reportPackage,
  run_status: 'COMPLETED',
  passed_count: 11,
  warning_count: 1,
  failed_count: 0,
  can_generate_formal_report: true,
  input_fingerprint: 'formal-fingerprint',
  findings: [
    {
      code: 'F02_BENCHMARK_NOTES_MISSING',
      severity: 'WARNING',
      message: 'F02 尚未填寫比較價格決定說明。',
      field_code: 'benchmark_notes',
    },
  ],
  completed_at: '2026-09-07T03:04:00Z',
}

const blockedFormalValidationDto = {
  ...formalValidationDto,
  validation_run_id: '88888888-8888-4888-8888-88888888888a',
  passed_count: 10,
  warning_count: 0,
  failed_count: 1,
  can_generate_formal_report: false,
  findings: [
    {
      code: 'F02_FORMAL_DATA_MISSING',
      severity: 'ERROR',
      message: '正式資料尚未完成。',
      field_code: 'formal_value',
    },
  ],
}

const formalValidationNoWarningsDto = {
  ...formalValidationDto,
  warning_count: 0,
  findings: [],
}

const formalReportDto = {
  document_id: ids.formalReport,
  case_id: ids.case,
  report_id: ids.reportPackage,
  validation_run_id: ids.formalValidationRun,
  filename: 'complete_valuation_report_NB-2026-0001_v5.pdf',
  mime_type: 'application/pdf',
  version_no: 5,
  bucket_name: 'internal-bucket-must-not-render',
  object_key: 'cases/internal/formal-object-key-must-not-render.pdf',
  checksum_sha256: 'formal-not-rendered',
  file_size_bytes: 8192,
  download_path: `/valuation/cases/${ids.case}/complete-reports/${ids.formalReport}/download`,
  request_id: null,
}

const submissionDto = {
  submission_id: ids.submission,
  submission_no: 1,
  review_id: ids.review,
  case_status: 'IN_REVIEW',
  submitted_at: '2026-09-07T03:05:00Z',
}

describe('valuation demo flow', () => {
  const originalAdapter = http.defaults.adapter

  beforeEach(() => {
    setActivePinia(createPinia())
    resetValuationFlow()
    tokenService.clear()
    const store = useAuthStore()
    store.user = appraiser
    tokenService.set('valuation-test-token', 1800)
  })

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    resetValuationFlow()
    tokenService.clear()
    vi.restoreAllMocks()
  })

  it('follows the real F03 state machine and submits the authoritative F02 report', async () => {
    const requests: Array<{ method?: string; url?: string; params?: unknown; data?: unknown }> = []
    const patchBodies: Array<Record<string, any>> = []
    let submitCount = 0
    let validationCount = 0
    let reportCount = 0
    const formalPdfBodies: Array<Record<string, any>> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, params: config.params, data: config.data })

      if (config.method === 'get' && config.url === '/valuation/cases') return response([caseDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        const f03 = requests.some(
          (request) => request.method === 'post' && request.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/submit`,
        )
          ? submittedF03FormDto
          : formDto
        return response([authoritativeFormDto, f03], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([benchmarkDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response(documentsDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) {
        patchBodies.push(requestBody(config.data))
        return response(f03Dto, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/calculations`) {
        expect(requestBody(config.data)).toEqual({ form_instance_id: ids.f03 })
        return response(calculationDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/submit`) {
        expect(config.data).toBeUndefined()
        return response(submittedF03FormDto, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/validations`) {
        expect(requestBody(config.data)).toEqual({ form_instance_id: ids.f03 })
        const validation = validationCount++ === 0 ? blockedValidationDto : validationDto
        return response(validation, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports`) {
        expect(requestBody(config.data)).toEqual({ form_instance_id: ids.f03 })
        reportCount += 1
        return response(reportDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) return response(formalValidationDto, config, 201)
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-pdf`) {
        formalPdfBodies.push(requestBody(config.data))
        expect(formalPdfBodies[0]).toEqual({
          confirm_generate: true,
          acknowledged_warning_codes: ['F02_BENCHMARK_NOTES_MISSING'],
        })
        return response(formalReportDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/submit-for-review`) {
        submitCount += 1
        const body = requestBody(requests.at(-1)?.data)
        expect(body).toEqual({
          request_id: expect.any(String),
          expected_case_version: authoritativeFormDto.version_no,
          source_validation_run_id: ids.formalValidationRun,
          source_report_document_id: ids.formalReport,
        })
        expect(body.source_report_document_id).not.toBe(ids.completeReport)
        expect(body.source_report_document_id).not.toBe(ids.f03Report)
        return response(submissionDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/valuation/dashboard')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('NB-2026-0001')
    expect(wrapper.text()).toContain('繼續處理')
    await wrapper.get('[data-testid="case-open"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe(`/app/valuation/cases/${ids.case}/prepare`))
    expect(wrapper.text()).toContain('來源：案件原始資料')
    expect(wrapper.text()).toContain('正式採用值')
    expect(wrapper.text()).toContain('人工確認欄位')

    await wrapper.get('[data-testid="f03-comparison-price"]').setValue('125001.00')
    await wrapper.get('[data-testid="save-confirmed-fields"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="run-valuation"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('有伺服器阻擋項目')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('阻擋')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('實際值')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('expected')
    expect(reportCount).toBe(0)
    expect(submitCount).toBe(0)
    expect(valuationFlowState.forms.find((form) => form.formInstanceId === ids.f03)?.status).toBe('DRAFT')

    await wrapper.get('[data-testid="f03-comparison-price"]').setValue('125002.00')
    await wrapper.get('[data-testid="run-valuation"]').trigger('click')
    await flushPromises()

    const operationRequests = requests
      .map((request) => `${request.method} ${request.url}`)
      .filter((request) =>
        (request.startsWith(`patch /valuation/cases/${ids.case}/forms/${ids.f03}/f03`) ||
          request.startsWith(`post /valuation/cases/${ids.case}/forms/${ids.f03}/submit`) ||
          request.startsWith(`post /valuation/cases/${ids.case}/calculations`) ||
          request.startsWith(`post /valuation/cases/${ids.case}/validations`) ||
          request.startsWith(`post /valuation/cases/${ids.case}/reports`)),
      )
    expect(operationRequests).toEqual([
      `patch /valuation/cases/${ids.case}/forms/${ids.f03}/f03`,
      `post /valuation/cases/${ids.case}/calculations`,
      `post /valuation/cases/${ids.case}/validations`,
      `patch /valuation/cases/${ids.case}/forms/${ids.f03}/f03`,
      `post /valuation/cases/${ids.case}/calculations`,
      `post /valuation/cases/${ids.case}/validations`,
      `post /valuation/cases/${ids.case}/forms/${ids.f03}/submit`,
      `post /valuation/cases/${ids.case}/reports`,
    ])
    expect(patchBodies).toHaveLength(2)
    expect(patchBodies[0]).toEqual(expect.objectContaining({ comparison_price: '125001.00' }))
    expect(patchBodies[1]).toEqual(expect.objectContaining({ comparison_price: '125002.00' }))
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('伺服器檢核結果')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('警示')
    expect(wrapper.get('[data-testid="official-value"]').text()).toContain('123456.00')
    expect(wrapper.text()).not.toContain('internal-bucket-must-not-render')
    expect(wrapper.text()).not.toContain('object-key-must-not-render')

    await wrapper.get('[data-testid="go-to-submit"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe(`/app/valuation/cases/${ids.case}/submit`))
    expect(wrapper.text()).toContain('送審確認')
    const submitButton = wrapper.get('[data-testid="submit-for-review"]')
    expect(submitButton.attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="run-formal-validation"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="formal-validation-result"]').text()).toContain('F02_BENCHMARK_NOTES_MISSING')
    expect(valuationFlowState.authoritativeF02?.status).toBe('CHECKED')
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeDefined()
    expect(formalPdfBodies).toHaveLength(0)
    await wrapper.get('[data-testid="formal-warning-F02_BENCHMARK_NOTES_MISSING"]').setValue(true)
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="generate-formal-pdf"]').trigger('click')
    await flushPromises()
    expect(formalPdfBodies).toHaveLength(1)
    expect(valuationFlowState.formalReport?.documentId).toBe(ids.formalReport)
    expect(valuationFlowState.authoritativeF02?.status).toBe('FINAL')
    expect(valuationFlowState.authoritativeF02?.outputDocumentId).toBe(ids.formalReport)
    expect(wrapper.get('[data-testid="submit-for-review"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="submit-for-review"]').trigger('click')
    await flushPromises()

    expect(submitCount).toBe(1)
    expect(wrapper.get('[data-testid="submission-result"]').text()).toContain('審查中')
    expect(wrapper.get('[data-testid="submission-result"]').text()).toContain('第 1 次送審')
    expect(wrapper.find('[data-testid="submit-for-review"]').exists()).toBe(false)
    expect(requests.some((request) => request.data?.toString().includes('internal-bucket'))).toBe(false)
    wrapper.unmount()
  })

  it('reuses one submit request id after a network timeout and clears it after success', async () => {
    Object.assign(valuationFlowState, {
      case: mapCaseResponse(caseDto),
      forms: [mapFormResponse(formalAuthoritativeFormDto), mapFormResponse(submittedF03FormDto)],
      documents: [...documentsDto, formalDocumentDto].map(mapDocumentResponse),
      authoritativeF02: mapFormResponse(formalAuthoritativeFormDto),
      completeReport: mapDocumentResponse(formalDocumentDto),
      reportPackageId: ids.reportPackage,
      validation: mapValidationResponse(validationDto),
      report: mapReportResponse(reportDto),
      formalValidation: mapFormalValidationResponse(formalValidationNoWarningsDto),
      formalReport: mapFormalReportResponse(formalReportDto),
    })

    const submitBodies: Array<Record<string, any>> = []
    let submitAttempts = 0
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([formalAuthoritativeFormDto, submittedF03FormDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) {
        return response([...documentsDto, formalDocumentDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response(reportProgressDto, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) {
        return response(formalValidationDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/submit-for-review`) {
        submitAttempts += 1
        submitBodies.push(requestBody(config.data))
        if (submitAttempts === 1) {
          throw new AxiosError('request timed out', 'ECONNABORTED', config)
        }
        return response(submissionDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="submit-for-review"]').exists()).toBe(true))

    await wrapper.get('[data-testid="submit-for-review"]').trigger('click')
    await flushPromises()
    expect(submitAttempts).toBe(1)
    expect(wrapper.get('[data-testid="submit-for-review"]').exists()).toBe(true)

    await wrapper.get('[data-testid="submit-for-review"]').trigger('click')
    await flushPromises()

    expect(submitAttempts).toBe(2)
    expect(submitBodies[0]).toEqual(expect.objectContaining({ request_id: expect.any(String) }))
    expect(submitBodies[1]).toEqual(submitBodies[0])
    expect(wrapper.get('[data-testid="submission-result"]').text()).toContain('審查中')
    wrapper.unmount()
  })

  it('resumes a persisted CHECKED formal package after reload and submits only after FINAL PDF output', async () => {
    const formalPdfRequestIds: string[] = []
    const operationRequests: string[] = []
    Object.assign(valuationFlowState, {
      case: mapCaseResponse(caseDto),
      forms: [mapFormResponse(checkedAuthoritativeFormDto), mapFormResponse(submittedF03FormDto)],
      documents: documentsDto.map(mapDocumentResponse),
      authoritativeF02: mapFormResponse(checkedAuthoritativeFormDto),
      completeReport: mapDocumentResponse(documentsDto[1]),
      reportPackageId: ids.reportPackage,
    })
    http.defaults.adapter = vi.fn(async (config) => {
      operationRequests.push(`${config.method} ${config.url}`)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([checkedAuthoritativeFormDto, submittedF03FormDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) {
        return response(documentsDto, config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response(reportProgressDto, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) {
        return response(formalValidationNoWarningsDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-pdf`) {
        const requestId = config.headers?.get?.('X-Request-ID') ?? config.headers?.['X-Request-ID']
        expect(requestId).toEqual(expect.any(String))
        formalPdfRequestIds.push(String(requestId))
        expect(requestBody(config.data)).toEqual({
          confirm_generate: true,
          acknowledged_warning_codes: [],
        })
        return response(formalReportDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/submit-for-review`) {
        expect(requestBody(config.data)).toEqual({
          request_id: expect.any(String),
          expected_case_version: checkedAuthoritativeFormDto.version_no,
          source_validation_run_id: ids.formalValidationRun,
          source_report_document_id: ids.formalReport,
        })
        return response(submissionDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="formal-validation-result"]').exists()).toBe(true))

    expect(valuationFlowState.authoritativeF02?.status).toBe('CHECKED')
    expect(wrapper.get('[data-testid="submit-for-review"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="generate-formal-pdf"]').trigger('click')
    await flushPromises()

    expect(formalPdfRequestIds).toHaveLength(1)
    expect(valuationFlowState.authoritativeF02?.status).toBe('FINAL')
    expect(valuationFlowState.authoritativeF02?.outputDocumentId).toBe(ids.formalReport)
    expect(wrapper.get('[data-testid="submit-for-review"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="submit-for-review"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="submission-result"]').text()).toContain('審查中')
    expect(operationRequests).toEqual([
      `get /valuation/cases/${ids.case}`,
      `get /valuation/cases/${ids.case}/forms`,
      `get /valuation/cases/${ids.case}/documents`,
      `get /valuation/cases/${ids.case}/report-progress`,
      `post /valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`,
      `post /valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-pdf`,
      `post /valuation/cases/${ids.case}/submit-for-review`,
      `get /valuation/cases/${ids.case}`,
    ])
    wrapper.unmount()
  })

  it('keeps a CHECKED package blocked when no passing persisted formal validation is available', async () => {
    let formalPdfCount = 0
    let submitCount = 0
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([checkedAuthoritativeFormDto, submittedF03FormDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response(documentsDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) {
        return response(blockedFormalValidationDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-pdf`) {
        formalPdfCount += 1
        return response(formalReportDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/submit-for-review`) {
        submitCount += 1
        return response(submissionDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="formal-validation-result"]').exists()).toBe(true))

    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="submit-for-review"]').attributes('disabled')).toBeDefined()
    expect(formalPdfCount).toBe(0)
    expect(submitCount).toBe(0)
    wrapper.unmount()
  })

  it('reuses one formal-PDF request id after a network timeout and clears it after success', async () => {
    const formalPdfRequestIds: string[] = []
    let formalPdfAttempts = 0
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([checkedAuthoritativeFormDto, submittedF03FormDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response(documentsDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) {
        return response(formalValidationNoWarningsDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-pdf`) {
        const requestId = config.headers?.get?.('X-Request-ID') ?? config.headers?.['X-Request-ID']
        formalPdfRequestIds.push(String(requestId))
        formalPdfAttempts += 1
        if (formalPdfAttempts === 1) throw new AxiosError('request timed out', 'ECONNABORTED', config)
        return response(formalReportDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="formal-validation-result"]').exists()).toBe(true))

    await wrapper.get('[data-testid="generate-formal-pdf"]').trigger('click')
    await flushPromises()
    expect(formalPdfRequestIds).toHaveLength(1)
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').exists()).toBe(true)

    await wrapper.get('[data-testid="run-formal-validation"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="generate-formal-pdf"]').trigger('click')
    await flushPromises()
    expect(formalPdfRequestIds).toHaveLength(2)
    expect(formalPdfRequestIds[1]).toBe(formalPdfRequestIds[0])
    expect(valuationFlowState.authoritativeF02?.status).toBe('FINAL')
    wrapper.unmount()
  })

  it('starts a new formal-PDF request id after a definitive server rejection', async () => {
    const formalPdfRequestIds: string[] = []
    let formalPdfAttempts = 0
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([checkedAuthoritativeFormDto, submittedF03FormDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response(documentsDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) {
        return response(formalValidationNoWarningsDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-pdf`) {
        const requestId = config.headers?.get?.('X-Request-ID') ?? config.headers?.['X-Request-ID']
        formalPdfRequestIds.push(String(requestId))
        formalPdfAttempts += 1
        if (formalPdfAttempts === 1) {
          const rejected = new AxiosError('server rejected', 'ERR_BAD_REQUEST', config)
          Object.assign(rejected, { response: { status: 409 } })
          throw rejected
        }
        return response(formalReportDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="formal-validation-result"]').exists()).toBe(true))

    await wrapper.get('[data-testid="generate-formal-pdf"]').trigger('click')
    await flushPromises()
    expect(formalPdfRequestIds).toHaveLength(1)
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="generate-formal-pdf"]').trigger('click')
    await flushPromises()
    expect(formalPdfRequestIds).toHaveLength(2)
    expect(formalPdfRequestIds[1]).not.toBe(formalPdfRequestIds[0])
    expect(valuationFlowState.authoritativeF02?.status).toBe('FINAL')
    wrapper.unmount()
  })

  it('reloads submit data from ErrorState retry', async () => {
    let caseRequests = 0
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) {
        caseRequests += 1
        if (caseRequests === 1) throw new AxiosError('temporary failure', 'ERR_NETWORK', config)
        return response(caseDto, config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([formDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('.page-state--error').exists()).toBe(true))

    await wrapper.get('.page-state__action').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('NB-2026-0001'))
    expect(caseRequests).toBe(2)
    wrapper.unmount()
  })

  it('keeps submit disabled when formal validation is blocked', async () => {
    Object.assign(valuationFlowState, {
      case: mapCaseResponse(caseDto),
      forms: [mapFormResponse(formalAuthoritativeFormDto), mapFormResponse(submittedF03FormDto)],
      documents: [...documentsDto, formalDocumentDto].map(mapDocumentResponse),
      authoritativeF02: mapFormResponse(formalAuthoritativeFormDto),
      completeReport: mapDocumentResponse(formalDocumentDto),
      reportPackageId: ids.reportPackage,
      validation: mapValidationResponse(validationDto),
      report: mapReportResponse(reportDto),
      formalValidation: mapFormalValidationResponse(formalValidationNoWarningsDto),
      formalReport: mapFormalReportResponse(formalReportDto),
    })

    let formalPdfCount = 0
    let submitCount = 0
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([formalAuthoritativeFormDto, submittedF03FormDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) {
        return response([...documentsDto, formalDocumentDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response(reportProgressDto, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) {
        return response(blockedFormalValidationDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-pdf`) {
        formalPdfCount += 1
        return response(formalReportDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/submit-for-review`) {
        submitCount += 1
        return response(submissionDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="submit-for-review"]').exists()).toBe(true))

    await wrapper.get('[data-testid="run-formal-validation"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="formal-validation-result"]').text()).toContain('正式資料尚未完成')
    expect(wrapper.get('[data-testid="submit-for-review"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeDefined()
    expect(formalPdfCount).toBe(0)
    expect(submitCount).toBe(0)
    wrapper.unmount()
  })

  it('starts a new submit request id after a definitive server rejection', async () => {
    Object.assign(valuationFlowState, {
      case: mapCaseResponse(caseDto),
      forms: [mapFormResponse(formalAuthoritativeFormDto), mapFormResponse(submittedF03FormDto)],
      documents: [...documentsDto, formalDocumentDto].map(mapDocumentResponse),
      authoritativeF02: mapFormResponse(formalAuthoritativeFormDto),
      completeReport: mapDocumentResponse(formalDocumentDto),
      reportPackageId: ids.reportPackage,
      validation: mapValidationResponse(validationDto),
      report: mapReportResponse(reportDto),
      formalValidation: mapFormalValidationResponse(formalValidationNoWarningsDto),
      formalReport: mapFormalReportResponse(formalReportDto),
    })

    const submitBodies: Array<Record<string, any>> = []
    let submitAttempts = 0
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([formalAuthoritativeFormDto, submittedF03FormDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) {
        return response([...documentsDto, formalDocumentDto], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response(reportProgressDto, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-validation`) {
        return response(formalValidationDto, config, 201)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/submit-for-review`) {
        submitAttempts += 1
        submitBodies.push(requestBody(config.data))
        if (submitAttempts === 1) {
          const rejected = new AxiosError('server rejected', 'ERR_BAD_REQUEST', config)
          Object.assign(rejected, { response: { status: 409 } })
          throw rejected
        }
        return response(submissionDto, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="submit-for-review"]').exists()).toBe(true))

    await wrapper.get('[data-testid="submit-for-review"]').trigger('click')
    await flushPromises()
    expect(submitAttempts).toBe(1)
    expect(wrapper.get('[data-testid="submit-for-review"]').exists()).toBe(true)

    await wrapper.get('[data-testid="submit-for-review"]').trigger('click')
    await flushPromises()

    expect(submitAttempts).toBe(2)
    expect(submitBodies[0].request_id).not.toBe(submitBodies[1].request_id)
    expect(wrapper.get('[data-testid="submission-result"]').text()).toContain('審查中')
    wrapper.unmount()
  })

  it('reloads a reused prepare route for B and never renders A state', async () => {
    const requests: Array<{ method?: string; url?: string; params?: unknown; data?: unknown }> = []
    const caseBId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaae'
    const f03BId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaf'
    const caseA = { ...caseDto, case_no: 'CASE-A', case_title: '案件 A' }
    const caseB = { ...caseDto, case_id: caseBId, case_no: 'CASE-B', case_title: '案件 B' }
    const formA = { ...formDto }
    const formB = { ...formDto, case_id: caseBId, form_instance_id: f03BId }
    const f03A = { ...f03Dto }
    const f03B = { ...f03Dto, case_id: caseBId, form_instance_id: f03BId, benchmark_valuation_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaba' }
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, params: config.params, data: config.data })
      if (config.method === 'get' && config.url === '/valuation/cases') return response([caseA, caseB], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseA, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}`) return response(caseB, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([formA], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/forms`) return response([formB], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03A, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/forms/${f03BId}/f03`) return response(f03B, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([{ ...benchmarkDto }], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/benchmark-lands`) return response([{ ...benchmarkDto, case_id: caseBId }], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/report-progress`) return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('CASE-A'))

    await router.push(`/app/valuation/cases/${caseBId}/prepare`)
    await vi.waitFor(() => expect(wrapper.text()).toContain('CASE-B'))
    expect(wrapper.text()).not.toContain('CASE-A')
    expect(wrapper.text()).not.toContain(ids.f03)
    wrapper.unmount()
  })

  it('ignores stale submit-view responses when the reused route changes from A to B', async () => {
    const caseBId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaabb'
    const pendingA: Array<() => void> = []
    const caseA = { ...caseDto, case_no: 'CASE-A', case_title: '案件 A' }
    const caseB = { ...caseDto, case_id: caseBId, case_no: 'CASE-B', case_title: '案件 B' }
    const formB = { ...formDto, case_id: caseBId, form_instance_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaabc' }

    http.defaults.adapter = vi.fn((config) => {
      if (config.url?.includes(`/cases/${ids.case}`)) {
        return new Promise((resolve) => {
          pendingA.push(() => {
            if (config.url === `/valuation/cases/${ids.case}`) resolve(response(caseA, config))
            if (config.url === `/valuation/cases/${ids.case}/forms`) {
              resolve(response([authoritativeFormDto, submittedF03FormDto], config))
            }
            if (config.url === `/valuation/cases/${ids.case}/documents`) resolve(response(documentsDto, config))
            if (config.url === `/valuation/cases/${ids.case}/report-progress`) resolve(response(reportProgressDto, config))
          })
        })
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}`) return Promise.resolve(response(caseB, config))
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/forms`) return Promise.resolve(response([formB], config))
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/documents`) return Promise.resolve(response([], config))
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/report-progress`) {
        return Promise.resolve(response({ ...reportProgressDto, report_id: null, version_no: null }, config))
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(pendingA).toHaveLength(4))

    await router.push(`/app/valuation/cases/${caseBId}/submit`)
    await vi.waitFor(() => expect(wrapper.text()).toContain('CASE-B'))
    pendingA.forEach((resolve) => resolve())
    await flushPromises()

    expect(wrapper.text()).not.toContain('CASE-A')
    expect(wrapper.text()).not.toContain('案件 A')
    expect(valuationFlowState.case?.caseId).toBe(caseBId)
    wrapper.unmount()
  })
})

function requestBody(data: unknown): Record<string, any> {
  if (typeof data === 'string') return JSON.parse(data) as Record<string, any>
  return (data ?? {}) as Record<string, any>
}

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}
