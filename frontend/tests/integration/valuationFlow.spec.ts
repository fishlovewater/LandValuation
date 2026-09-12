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
    'case.create',
    'case.update',
    'valuation.read',
    'valuation.update',
    'valuation.submit_review',
    'document.upload',
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
  valuation_due_date: '2026-09-30',
  city_code: '65000',
  district_code: '65000030',
  land_use_type: '住宅區',
  case_status: 'PROCESSING',
  basic_info_confirmed_at: '2026-09-07T01:30:00Z',
  basic_info_confirmed_by_user_id: appraiser.id,
  last_workspace_stage: 'case',
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

const parcelDto = {
  parcel_id: ids.parcel,
  case_id: ids.case,
  district_code: '65000030',
  section_name: '安康段',
  subsection_name: '',
  land_no: '123-4',
  area_sqm: '100.5000',
  land_use_zone: '住宅區',
  designated_use: null,
  ownership_numerator: null,
  ownership_denominator: null,
  source_document_id: ids.sourceDocument,
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
      message: '市場條件目前被標示為警示，請確認來源。',
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

  it('requires first-time case confirmation, persists it, and then opens document intake', async () => {
    const unconfirmedCase = {
      ...caseDto,
      basic_info_confirmed_at: null,
      basic_info_confirmed_by_user_id: null,
      last_workspace_stage: 'case',
    }
    const workspaceBodies: Array<Record<string, unknown>> = []
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(unconfirmedCase, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/workspace`) {
        const body = requestBody(config.data)
        workspaceBodies.push(body)
        return response({
          ...unconfirmedCase,
          basic_info_confirmed_at: '2026-09-12T05:00:00Z',
          basic_info_confirmed_by_user_id: appraiser.id,
          last_workspace_stage: 'documents',
          updated_at: '2026-09-12T05:00:00Z',
        }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="valuation-workflow-guide"]').text()).toContain('案件基本資料'))

    expect(wrapper.get('[data-testid="wizard-next"]').text()).toContain('確認並開始估價')
    expect(wrapper.find('[data-testid="valuation-issue-drawer"]').exists()).toBe(false)

    await wrapper.get('[data-testid="valuation-step-3"]').trigger('click')
    expect(wrapper.get('[data-testid="valuation-workflow-guide"]').text()).toContain('案件基本資料')
    expect(wrapper.text()).toContain('請先確認案件基本資料')
    expect(workspaceBodies).toHaveLength(0)

    await wrapper.get('[data-testid="wizard-next"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[data-workspace-stage="documents"]').attributes('aria-current')).toBe('step'))
    expect(workspaceBodies).toEqual([{
      confirm_basic_info: true,
      last_workspace_stage: 'documents',
    }])
    expect(wrapper.text()).toContain('案件基本資料已確認')
    expect(wrapper.find('#valuation-document-workspace').exists()).toBe(true)
    wrapper.unmount()
  }, 10_000)

  it('restores the last persisted valuation workspace stage when reopening a confirmed case', async () => {
    const resumedCase = {
      ...caseDto,
      last_workspace_stage: 'documents',
    }
    const workspaceRequests: string[] = []
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(resumedCase, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/workspace`) {
        workspaceRequests.push(String(config.url))
        return response(resumedCase, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })

    await vi.waitFor(() => expect(wrapper.get('[data-workspace-stage="documents"]').attributes('aria-current')).toBe('step'))
    expect(wrapper.get('[data-testid="valuation-workflow-guide"]').text()).toContain('文件與辨識')
    expect(wrapper.find('#valuation-document-workspace').exists()).toBe(true)
    expect(workspaceRequests).toHaveLength(0)
    wrapper.unmount()
  })

  it('uses the canonical documents deep link as the active stage and persists that explicit navigation', async () => {
    const storedCase = {
      ...caseDto,
      last_workspace_stage: 'data',
    }
    const workspaceBodies: Array<Record<string, unknown>> = []
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(storedCase, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/workspace`) {
        const body = requestBody(config.data)
        workspaceBodies.push(body)
        return response({ ...storedCase, last_workspace_stage: body.last_workspace_stage }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/documents`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })

    await vi.waitFor(() => expect(wrapper.get('[data-workspace-stage="documents"]').attributes('aria-current')).toBe('step'))
    expect(router.currentRoute.value.path).toBe(`/app/valuation/cases/${ids.case}/documents`)
    expect(wrapper.find('#valuation-document-workspace').exists()).toBe(true)
    await vi.waitFor(() => expect(workspaceBodies).toContainEqual({ last_workspace_stage: 'documents' }))
    wrapper.unmount()
  })

  it('returns an unconfirmed canonical deep link to the case confirmation route without persisting a later stage', async () => {
    const unconfirmedCase = {
      ...caseDto,
      basic_info_confirmed_at: null,
      basic_info_confirmed_by_user_id: null,
      last_workspace_stage: 'case',
    }
    const workspaceRequests: string[] = []
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(unconfirmedCase, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response(reportProgressDto, config)
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/workspace`) {
        workspaceRequests.push(String(config.url))
        return response(unconfirmedCase, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/documents`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })

    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe(`/app/valuation/cases/${ids.case}`))
    expect(wrapper.get('[data-testid="valuation-workflow-guide"]').text()).toContain('案件基本資料')
    expect(wrapper.get('[data-testid="wizard-next"]').text()).toContain('確認並開始估價')
    expect(workspaceRequests).toHaveLength(0)
    wrapper.unmount()
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
        return response([
          { ...authoritativeFormDto, form_instance_id: '61616161-6161-4616-8161-616161616161', form_code: 'S01' },
          { ...authoritativeFormDto, form_instance_id: '62626262-6262-4626-8262-626262626262', form_code: 'F02-RF' },
          authoritativeFormDto,
          f03,
        ], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([parcelDto], config)
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
    expect(wrapper.text()).toContain('作業期限')
    expect(wrapper.text()).toContain('繼續估價')
    expect(wrapper.get('[data-testid="valuation-dashboard-header"]').text()).toContain('估價案件')
    const dashboardSummary = wrapper.get('[data-testid="valuation-dashboard-summary"]')
    expect(dashboardSummary.text()).toContain('目前 1 件案件')
    expect(dashboardSummary.text()).toContain('1 件已設定作業期限')
    expect(dashboardSummary.text()).toContain('預設依作業期限由近到遠排列')
    expect(wrapper.get('[data-testid="valuation-case-list"]').text()).toContain('案件列表')
    await wrapper.get('[data-testid="create-case"]').trigger('click')
    const fixedCaseType = wrapper.get('[data-testid="create-case-type-fixed"]')
    expect(fixedCaseType.text()).toContain('土地徵收補償市價查估')
    expect(fixedCaseType.find('input').exists()).toBe(false)
    await wrapper.get('.create-case-actions button').trigger('click')
    expect(wrapper.get(`[data-testid="case-open-${ids.case}"]`).exists()).toBe(true)
    await wrapper.get(`[data-testid="case-open-${ids.case}"]`).trigger('click')
    await vi.waitFor(
      () => expect(router.currentRoute.value.path).toBe(`/app/valuation/cases/${ids.case}`),
      { timeout: 3000 },
    )
    expect(wrapper.text()).toContain('來源：案件原始資料')
    expect(wrapper.get('[data-testid="case-context"]').text()).toContain('NB-2026-0001')
    expect(wrapper.text()).toContain('比準地地價估計表')
    expect(wrapper.text()).toContain('比較法調查估價表')
    expect(wrapper.text()).toContain('影響地價區域因素分析明細表')
    expect(wrapper.text()).toContain('地價區段勘查表')

    await wrapper.get('[data-testid="valuation-step-3"]').trigger('click')
    await wrapper.get('[data-testid="data-section-f03"]').trigger('click')
    expect(wrapper.text()).toContain('正式採用值')
    expect(wrapper.text()).toContain('人工確認欄位')
    await wrapper.get('[data-testid="f03-comparison-price"]').setValue('125001.00')
    await wrapper.get('[data-testid="save-confirmed-fields"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="valuation-step-4"]').trigger('click')
    await wrapper.get('[data-testid="run-valuation"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('仍有待修正項目')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('阻擋')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('實際值')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('必填')
    expect(wrapper.get('[data-testid="validation-results"]').text()).not.toContain('required')
    expect(reportCount).toBe(0)
    expect(submitCount).toBe(0)
    expect(valuationFlowState.forms.find((form) => form.formInstanceId === ids.f03)?.status).toBe('DRAFT')

    await wrapper.get('[data-testid="valuation-step-3"]').trigger('click')
    await wrapper.get('[data-testid="data-section-f03"]').trigger('click')
    await wrapper.get('[data-testid="f03-comparison-price"]').setValue('125002.00')
    await wrapper.get('[data-testid="valuation-step-4"]').trigger('click')
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
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('可產生比準地地價估計表單表')
    expect(wrapper.get('[data-testid="validation-results"]').text()).toContain('警示')
    expect(wrapper.get('[data-testid="calculation-result"]').text()).toContain('123456.00')
    expect(wrapper.text()).not.toContain('internal-bucket-must-not-render')
    expect(wrapper.text()).not.toContain('object-key-must-not-render')

    await wrapper.get('[data-testid="go-to-submit"]').trigger('click')
    await vi.waitFor(
      () => expect(router.currentRoute.value.path).toBe(`/app/valuation/cases/${ids.case}/report`),
      { timeout: 5000 },
    )
    const reportStage = wrapper.get('[data-workspace-stage="report"]')
    expect(reportStage.attributes('aria-current')).toBe('step')
    expect(reportStage.text()).toContain('查估書與送審')
    const submitReadiness = wrapper.get('[data-testid="submit-readiness-steps"]')
    expect(submitReadiness.text()).toContain('送審進度')
    expect(submitReadiness.text()).toContain('確認完整查估書')
    expect(submitReadiness.text()).toContain('完成正式檢核')
    expect(submitReadiness.text()).toContain('產生完整送審 PDF')
    expect(submitReadiness.text()).toContain('送出審查')
    expect(wrapper.get('[data-testid="submit-next-action"]').text()).toContain('完成正式檢核')
    const submitButton = wrapper.get('[data-testid="submit-for-review"]')
    expect(submitButton.attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="run-formal-validation"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="formal-validation-result"]').text()).toContain('F02 尚未填寫比較價格決定說明')
    expect(wrapper.get('[data-testid="formal-validation-result"]').text()).not.toContain('F02_BENCHMARK_NOTES_MISSING')
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
    expect(wrapper.get('[data-testid="submit-readiness-steps"]').text()).toContain('所有送審條件已完成')
    expect(wrapper.get('[data-testid="submit-next-action"]').text()).toContain('送出審查')
    await wrapper.get('[data-testid="submit-for-review"]').trigger('click')
    await flushPromises()

    expect(submitCount).toBe(1)
    expect(wrapper.get('[data-testid="submission-result"]').text()).toContain('審查中')
    expect(wrapper.get('[data-testid="submission-result"]').text()).toContain('第 1 次送審')
    expect(wrapper.get('[data-testid="submit-readiness-steps"]').text()).toContain('完成 4 / 4')
    expect(wrapper.find('[data-testid="submit-for-review"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="submit-next-action"]').exists()).toBe(false)
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
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-status`) {
        return response({
          validation: formalValidationNoWarningsDto,
          report: formalReportDto,
          requires_revalidation_for_submission: false,
        }, config)
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
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-status`) {
        return response({
          validation: formalValidationNoWarningsDto,
          report: null,
          requires_revalidation_for_submission: false,
        }, config)
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
      `get /valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-status`,
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
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-status`) {
        return response({
          validation: blockedFormalValidationDto,
          report: null,
          requires_revalidation_for_submission: false,
        }, config)
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
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-status`) {
        return response({
          validation: formalValidationNoWarningsDto,
          report: null,
          requires_revalidation_for_submission: false,
        }, config)
      }
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
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-status`) {
        return response({
          validation: formalValidationNoWarningsDto,
          report: null,
          requires_revalidation_for_submission: false,
        }, config)
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
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.reportPackage}/formal-status`) {
        return response({
          validation: formalValidationNoWarningsDto,
          report: formalReportDto,
          requires_revalidation_for_submission: false,
        }, config)
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
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([{ ...parcelDto }], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${caseBId}/parcels`) return response([{ ...parcelDto, case_id: caseBId }], config)
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

  it('shows a review correction handoff and creates newer editable F03 and report-package drafts', async () => {
    const newF03Id = '13131313-1313-4131-8131-131313131313'
    const newReportId = '14141414-1414-4141-8141-141414141414'
    const correctionId = '15151515-1515-4151-8151-151515151515'
    const revisionCase = { ...caseDto, case_status: 'REVISION_REQUIRED' }
    const oldF03 = { ...formDto, form_status: 'READY' }
    const oldS01 = {
      ...authoritativeFormDto,
      form_instance_id: '16161616-1616-4161-8161-161616161616',
      form_code: 'S01',
      output_document_id: null,
    }
    const oldF02Rf = {
      ...authoritativeFormDto,
      form_instance_id: '17171717-1717-4171-8171-171717171717',
      form_code: 'F02-RF',
      output_document_id: null,
    }
    const newF03Form = {
      ...formDto,
      form_instance_id: newF03Id,
      version_no: 5,
      form_status: 'DRAFT',
      source_document_id: ids.sourceDocument,
    }
    const newF03Dto = {
      ...f03Dto,
      form_instance_id: newF03Id,
      benchmark_valuation_id: '18181818-1818-4181-8181-181818181818',
      version_no: 5,
      benchmark_land_price: null,
    }
    const newReportForms = (['S01', 'F02-RF', 'F02'] as const).map((code, index) => ({
      ...authoritativeFormDto,
      form_instance_id: `19191919-1919-4191-8191-19191919191${index}`,
      form_code: code,
      version_no: 5,
      form_status: 'DRAFT',
      form_content: {
        report_type: 'REPORT_COMPARISON_COMMERCIAL',
        report_id: newReportId,
      },
      output_document_id: null,
    }))
    const handoff = {
      case_id: ids.case,
      case_status: 'REVISION_REQUIRED',
      display_status: '退回補正',
      review_id: ids.review,
      review_status: 'RETURNED_FOR_REVISION',
      latest_submission: {
        submission_id: ids.submission,
        submission_no: 1,
        submitted_at: '2026-09-07T03:05:00Z',
      },
      correction: {
        correction_request_id: correctionId,
        request_no: 1,
        status: 'SENT',
        due_at: '2099-09-20T04:00:00Z',
        message: '請修正調整率並重新送審。',
        items: [{
          finding_code: 'ADJUSTMENT_RATE',
          severity: 'ERROR',
          document_id: null,
          page_number: 3,
          issue_summary: '調整率與正式規則不一致',
          requested_correction: '修正調整率後重新計算。',
        }],
      },
      missing_items: [],
    }
    const sourcePages = {
      S01: { page_code: 'S01', data: { district_name: '新店區', notes: '前版現勘資料' } },
      'F02-RF': {
        page_code: 'F02-RF',
        data: {
          benchmark_land_id: ids.benchmarkLand,
          comparison_analysis_id: null,
          rule_version_id: null,
          factor_rows: [],
          other_influences: [],
          notes: '前版區域因素',
        },
      },
      F02: {
        page_code: 'F02',
        data: {
          benchmark_land_id: ids.benchmarkLand,
          comparison_analysis_id: null,
          comparison_targets: [],
          benchmark_notes: '前版比較說明',
          notes: null,
        },
      },
    } as const
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    let revisionReady = false

    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(revisionCase, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response(
          revisionReady
            ? [oldS01, oldF02Rf, authoritativeFormDto, oldF03, ...newReportForms, newF03Form]
            : [oldS01, oldF02Rf, authoritativeFormDto, oldF03],
          config,
        )
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${newF03Id}/f03`) return response(newF03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([parcelDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([benchmarkDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response(documentsDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/review-handoff`) return response(handoff, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response(
          revisionReady
            ? { ...reportProgressDto, report_id: newReportId, version_no: 5, completion_rate: '0.00' }
            : reportProgressDto,
          config,
        )
      }
      if (config.method === 'get' && config.url?.startsWith(`/valuation/cases/${ids.case}/reports/${ids.reportPackage}/pages/`)) {
        const code = config.url.split('/').at(-1) as keyof typeof sourcePages
        return response(sourcePages[code], config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/forms`) {
        expect(requestBody(config.data)).toEqual(expect.objectContaining({
          form_code: 'F03',
          form_content: {},
        }))
        return response(newF03Form, config, 201)
      }
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/forms/${newF03Id}/f03`) {
        expect(requestBody(config.data)).toEqual(expect.objectContaining({
          benchmark_land_id: ids.benchmarkLand,
          valuation_base_date: '2026-08-01',
          comparison_price: '125000.00',
        }))
        return response(newF03Dto, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/report-packages`) {
        expect(requestBody(config.data)).toEqual({
          report_type: 'REPORT_COMPARISON_COMMERCIAL',
          prepared_date: '2026-09-07',
        })
        revisionReady = true
        return response({
          report_id: newReportId,
          case_id: ids.case,
          report_type: 'REPORT_COMPARISON_COMMERCIAL',
          version_no: 5,
          prepared_date: '2026-09-07',
          components: newReportForms.map((form) => ({
            code: form.form_code,
            form_instance_id: form.form_instance_id,
            form_status: form.form_status,
          })),
          created_at: '2026-09-10T12:00:00Z',
          updated_at: '2026-09-10T12:00:00Z',
        }, config, 201)
      }
      if (config.method === 'patch' && config.url?.startsWith(`/valuation/cases/${ids.case}/reports/${newReportId}/pages/`)) {
        return response({}, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="valuation-correction-request"]').text()).toContain('第 1 次補正要求'))

    expect(wrapper.get('[data-testid="valuation-correction-request"]').text()).toContain('修正調整率後重新計算')
    expect(wrapper.find('[data-testid="save-confirmed-fields"]').exists()).toBe(false)
    await wrapper.get('[data-testid="prepare-revision-draft"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="open-revision-fields"]').exists()).toBe(true))
    await wrapper.get('[data-testid="open-revision-fields"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="save-confirmed-fields"]').exists()).toBe(true))

    expect(wrapper.get('[data-testid="save-confirmed-fields"]').attributes('disabled')).toBeUndefined()
    expect(requests.some((request) => request.url === `/valuation/cases/${ids.case}/forms` && request.method === 'post')).toBe(true)
    expect(requests.some((request) => request.url === `/valuation/cases/${ids.case}/report-packages` && request.method === 'post')).toBe(true)
    expect(requests.filter((request) => request.url?.startsWith(`/valuation/cases/${ids.case}/reports/${newReportId}/pages/`) && request.method === 'patch')).toHaveLength(3)
    wrapper.unmount()
  })

  it('reviews an extracted candidate, preserves its evidence, and sends only the explicit human decision', async () => {
    const extractionId = '22222222-2222-4222-8222-222222222222'
    const candidateId = '23232323-2323-4232-8232-232323232323'
    const sourceDocument = {
      ...documentsDto[0],
      document_id: ids.sourceDocument,
      document_group_id: '24242424-2424-4242-8242-242424242424',
      document_type: 'original',
      original_filename: 'source-valuation.pdf',
      object_key: 'cases/internal/source-valuation.pdf',
      checksum_sha256: 'source-not-rendered',
      version_no: 1,
    }
    const candidate = {
      extracted_field_id: candidateId,
      extraction_id: extractionId,
      document_id: ids.sourceDocument,
      form_code: 'F03',
      field_name: 'valuation_base_date',
      extracted_value: '2026-08-02',
      confidence: '0.96',
      source_page: 2,
      source_text: 'valuation base date: 2026-08-02',
      analysis_provider: 'PDF_TEXT',
      model_id: null,
      prompt_version: null,
      field_status: 'NEEDS_CONFIRMATION',
      confirmed_value: null,
      confirmed_by_user_id: null,
      confirmed_at: null,
      applied_form_instance_id: null,
      applied_at: null,
    }
    let candidatePending = false
    const confirmationBodies: Array<Record<string, any>> = []
    const workflow = () => ({
      status: candidatePending ? 'NEEDS_CONFIRMATION' : 'READY',
      case: caseDto,
      parcel_ids: [ids.parcel],
      benchmark_land_ids: [ids.benchmarkLand],
      f03_form_instance_id: ids.f03,
      report_id: null,
      documents: [],
      candidates: candidatePending ? [candidate] : [{ ...candidate, field_status: 'APPLIED', confirmed_value: '2026-08-03' }],
      pending_candidate_count: candidatePending ? 1 : 0,
      blank_fields_remain: false,
      missing_items: [],
      warnings: [],
      next_action: candidatePending ? 'REVIEW_CANDIDATES' : 'RUN_FORM_CALCULATION',
      draft_pages_1_3_url: null,
      draft_pages_1_6_url: null,
      form_guidance: [],
      automatic_pdf_generation_enabled: false,
      automatic_confirmation_export_enabled: false,
      confirmation_export: null,
    })

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([formDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([parcelDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([benchmarkDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([sourceDocument], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents/${ids.sourceDocument}/download`) {
        return response(new Blob(['%PDF-1.4 test'], { type: 'application/pdf' }), config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/auto-workflow/review`) return response(workflow(), config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/review-handoff`) {
        return response({
          case_id: ids.case,
          case_status: 'PROCESSING',
          display_status: 'PROCESSING',
          review_id: null,
          review_status: null,
          latest_submission: null,
          correction: null,
          missing_items: [],
        }, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/documents/${ids.sourceDocument}/extract`) {
        candidatePending = true
        return response({
          extraction_id: extractionId,
          case_id: ids.case,
          document_id: ids.sourceDocument,
          provider: 'PDF_TEXT',
          extraction_status: 'COMPLETED',
          page_count: 3,
          extracted_text: null,
          error_message: null,
          started_at: '2026-09-11T00:00:00Z',
          completed_at: '2026-09-11T00:00:01Z',
          candidates: [candidate],
        }, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/auto-workflow/confirm`) {
        confirmationBodies.push(requestBody(config.data))
        candidatePending = false
        return response(workflow(), config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.find('[data-testid="valuation-step-2"]').exists()).toBe(true))
    await wrapper.get('[data-testid="valuation-step-2"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find(`[data-testid="extract-document-${ids.sourceDocument}"]`).exists()).toBe(true))
    const processGuide = wrapper.get('[data-testid="document-ai-process-guide"]')
    expect(processGuide.text()).toContain('先確認來源文件並執行辨識')
    expect(processGuide.text()).toContain('再人工確認辨識結果')
    expect(processGuide.text()).toContain('目前沒有待確認的辨識結果')

    await wrapper.get(`[data-testid="extract-document-${ids.sourceDocument}"]`).trigger('click')
    await vi.waitFor(() => expect(wrapper.find(`[data-testid="candidate-${candidateId}"]`).exists()).toBe(true))
    expect(wrapper.find('[data-testid="document-ai-process-guide"]').exists()).toBe(false)
    const aiReviewStage = wrapper.get('[data-workspace-stage="ai-review"]')
    expect(aiReviewStage.attributes('aria-current')).toBe('step')
    expect(aiReviewStage.text()).toContain('AI 結果確認')
    expect(aiReviewStage.text()).toContain('1')
    const candidateCard = wrapper.get(`[data-testid="candidate-${candidateId}"]`)
    expect(candidateCard.text()).toContain('source-valuation.pdf')
    expect(candidateCard.text()).toContain('96%')
    expect(candidateCard.text()).toContain('valuation base date: 2026-08-02')

    await wrapper.get(`[data-testid="candidate-source-${candidateId}"]`).trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="candidate-source-preview"]').exists()).toBe(true))
    expect(wrapper.get('[data-workspace-stage="ai-review"]').attributes('aria-current')).toBe('step')
    expect(wrapper.get('[data-testid="candidate-source-preview"]').text()).toContain('source-valuation.pdf')

    await wrapper.get(`[data-testid="candidate-value-${candidateId}"]`).setValue('2026-08-03')
    await wrapper.get(`[data-testid="candidate-confirm-${candidateId}"]`).trigger('click')
    await wrapper.get('[data-testid="submit-candidate-decisions"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find(`[data-testid="candidate-${candidateId}"]`).exists()).toBe(false))

    expect(confirmationBodies[0]).toEqual({
      confirmations: [{
        document_id: ids.sourceDocument,
        extracted_field_id: candidateId,
        decision: 'CONFIRM',
        corrected_value: '2026-08-03',
      }],
      confirm_apply: true,
    })
    expect(wrapper.get('[data-testid="valuation-candidate-workspace"]').text()).toContain('0')
    await vi.waitFor(() => expect(wrapper.find(`[data-testid="reopen-candidate-${candidateId}"]`).exists()).toBe(true))

    await wrapper.get(`[data-testid="reopen-candidate-${candidateId}"]`).trigger('click')
    await vi.waitFor(() => expect(wrapper.find(`[data-testid="candidate-${candidateId}"]`).exists()).toBe(true))
    await wrapper.get(`[data-testid="candidate-value-${candidateId}"]`).setValue('2026-08-04')
    await wrapper.get('[data-testid="submit-candidate-decisions"]').trigger('click')
    await vi.waitFor(() => expect(confirmationBodies).toHaveLength(2))

    expect(confirmationBodies[1]).toEqual({
      confirmations: [{
        document_id: ids.sourceDocument,
        extracted_field_id: candidateId,
        decision: 'CONFIRM',
        corrected_value: '2026-08-04',
      }],
      confirm_apply: true,
    })
    wrapper.unmount()
  })

  it('saves non-empty manual fallback fields through the server workflow instead of inventing local values', async () => {
    let savedReason = ''
    let manualBody: Record<string, any> | null = null
    const workflow = () => ({
      status: savedReason ? 'READY' : 'COMPLETE_WORKFLOW_REQUIREMENTS',
      case: caseDto,
      parcel_ids: [ids.parcel],
      benchmark_land_ids: [ids.benchmarkLand],
      f03_form_instance_id: ids.f03,
      report_id: null,
      documents: [],
      candidates: [],
      pending_candidate_count: 0,
      blank_fields_remain: !savedReason,
      missing_items: [],
      warnings: [],
      ignored_duplicate_files: [],
      next_action: savedReason ? 'RUN_FORM_CALCULATION' : 'FILL_REQUIRED_FIELDS',
      draft_pages_1_3_url: null,
      draft_pages_1_6_url: null,
      form_guidance: [{
        form_code: 'F03',
        form_instance_id: ids.f03,
        required_fields: ['decision_reason'],
        confirmed_or_applied_fields: savedReason ? ['decision_reason'] : [],
        pending_confirmation_fields: [],
        missing_required_fields: savedReason ? [] : ['decision_reason'],
        calculation_ready: Boolean(savedReason),
        next_action: savedReason ? 'RUN_FORM_CALCULATION' : 'FILL_REQUIRED_FIELDS',
        fill_endpoint: null,
        calculate_endpoint: null,
        validate_endpoint: null,
      }],
      automatic_pdf_generation_enabled: false,
      automatic_confirmation_export_enabled: true,
      confirmation_export: null,
      manual_fields_saved: savedReason ? ['F03.decision_reason'] : [],
      manual_fields_ignored: [],
      manual_field_errors: {},
      manual_field_values: savedReason ? { F03: { decision_reason: savedReason } } : {},
    })

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([formDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([parcelDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([benchmarkDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response(documentsDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/auto-workflow/review`) return response(workflow(), config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/review-handoff`) return response({
        case_id: ids.case, case_status: 'PROCESSING', display_status: 'PROCESSING', review_id: null,
        review_status: null, latest_submission: null, correction: null, missing_items: [],
      }, config)
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/auto-workflow/manual-fields`) {
        manualBody = requestBody(config.data)
        savedReason = String(manualBody.values?.F03?.decision_reason ?? '')
        return response(workflow(), config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.find('[data-testid="valuation-step-3"]').exists()).toBe(true))
    await wrapper.get('[data-testid="valuation-step-3"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="data-section-manual"]').exists()).toBe(true))
    await wrapper.get('[data-testid="data-section-manual"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="manual-field-workspace"]').exists()).toBe(true))

    await wrapper.get('[data-testid="manual-field-F03-decision_reason"]').setValue('人工核對附件後採用此值')
    await wrapper.get('[data-testid="save-manual-fields"]').trigger('click')
    await vi.waitFor(() => {
      expect(savedReason).toBe('人工核對附件後採用此值')
      expect(wrapper.find('[data-testid="manual-field-F03-decision_reason"]').exists()).toBe(false)
    })

    expect(manualBody).toEqual({ values: { F03: { decision_reason: '人工核對附件後採用此值' } } })
    expect(wrapper.text()).toContain('已儲存 1 個人工補充欄位')
    wrapper.unmount()
  })

  it('reclassifies and removes an active source document through the server document lifecycle', async () => {
    const originalConfirm = window.confirm
    Object.defineProperty(window, 'confirm', { configurable: true, value: vi.fn(() => true) })
    let documentState = {
      ...documentsDto[0],
      document_id: ids.sourceDocument,
      document_group_id: '31313131-3131-4313-8313-313131313131',
      document_type: 'original',
      original_filename: 'misclassified.pdf',
      is_active: true,
    }
    const writes: Array<{ method?: string; url?: string; body?: Record<string, any> }> = []
    const workflow = () => ({
      status: 'READY', case: caseDto, parcel_ids: [ids.parcel], benchmark_land_ids: [ids.benchmarkLand],
      f03_form_instance_id: ids.f03, report_id: null, documents: [], candidates: [], pending_candidate_count: 0,
      blank_fields_remain: false, missing_items: [], warnings: [], ignored_duplicate_files: [], next_action: 'RUN_FORM_CALCULATION',
      draft_pages_1_3_url: null, draft_pages_1_6_url: null, form_guidance: [], automatic_pdf_generation_enabled: false,
      automatic_confirmation_export_enabled: false, confirmation_export: null, manual_fields_saved: [], manual_fields_ignored: [],
      manual_field_errors: {}, manual_field_values: {},
    })

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([formDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([parcelDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([benchmarkDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([documentState], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/auto-workflow/review`) return response(workflow(), config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/review-handoff`) return response({
        case_id: ids.case, case_status: 'PROCESSING', display_status: 'PROCESSING', review_id: null,
        review_status: null, latest_submission: null, correction: null, missing_items: [],
      }, config)
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/documents/${ids.sourceDocument}/category`) {
        const body = requestBody(config.data)
        writes.push({ method: config.method, url: config.url, body })
        documentState = { ...documentState, document_type: String(body.category) }
        return response(documentState, config)
      }
      if (config.method === 'delete' && config.url === `/valuation/cases/${ids.case}/documents/${ids.sourceDocument}`) {
        writes.push({ method: config.method, url: config.url })
        documentState = { ...documentState, is_active: false }
        return response(null, config, 204)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.find('[data-testid="valuation-step-2"]').exists()).toBe(true))
    await wrapper.get('[data-testid="valuation-step-2"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find(`[data-testid="document-category-${ids.sourceDocument}"]`).exists()).toBe(true))

    await wrapper.get(`[data-testid="document-category-${ids.sourceDocument}"]`).setValue('land-register')
    await wrapper.get(`[data-testid="reclassify-document-${ids.sourceDocument}"]`).trigger('click')
    await vi.waitFor(() => {
      expect(documentState.document_type).toBe('land-register')
      expect(wrapper.get(`[data-testid="remove-document-${ids.sourceDocument}"]`).attributes('disabled')).toBeUndefined()
    })
    await wrapper.get(`[data-testid="remove-document-${ids.sourceDocument}"]`).trigger('click')
    await vi.waitFor(() => {
      expect(documentState.is_active).toBe(false)
      expect(wrapper.find(`[data-testid="remove-document-${ids.sourceDocument}"]`).exists()).toBe(false)
    })

    expect(writes).toEqual([
      {
        method: 'patch',
        url: `/valuation/cases/${ids.case}/documents/${ids.sourceDocument}/category`,
        body: { category: 'land-register' },
      },
      { method: 'delete', url: `/valuation/cases/${ids.case}/documents/${ids.sourceDocument}` },
    ])
    wrapper.unmount()
    Object.defineProperty(window, 'confirm', { configurable: true, value: originalConfirm })
  })

  it('keeps the land context read-only and allows blank parcel data', async () => {
    const newParcelId = '25252525-2525-4252-8252-252525252525'
    const newBenchmarkId = '26262626-2626-4262-8262-262626262626'
    let parcelState: typeof parcelDto | null = null
    let benchmarkState: typeof benchmarkDto | null = null
    const writes: Array<{ method?: string; url?: string; body: Record<string, any> }> = []
    const workflow = () => ({
      status: 'COMPLETE_WORKFLOW_REQUIREMENTS',
      case: caseDto,
      parcel_ids: parcelState ? [parcelState.parcel_id] : [],
      benchmark_land_ids: benchmarkState ? [benchmarkState.benchmark_land_id] : [],
      f03_form_instance_id: ids.f03,
      report_id: null,
      documents: [],
      candidates: [],
      pending_candidate_count: 0,
      blank_fields_remain: true,
      missing_items: [
        ...(parcelState ? [] : ['parcel']),
        ...(benchmarkState ? [] : ['benchmark_land']),
      ],
      warnings: [],
      next_action: 'COMPLETE_WORKFLOW_REQUIREMENTS',
      draft_pages_1_3_url: null,
      draft_pages_1_6_url: null,
      form_guidance: [],
      automatic_pdf_generation_enabled: false,
      automatic_confirmation_export_enabled: false,
      confirmation_export: null,
    })

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response(parcelState ? [parcelState] : [], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response(benchmarkState ? [benchmarkState] : [], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/auto-workflow/review`) return response(workflow(), config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/review-handoff`) {
        return response({
          case_id: ids.case,
          case_status: 'PROCESSING',
          display_status: 'PROCESSING',
          review_id: null,
          review_status: null,
          latest_submission: null,
          correction: null,
          missing_items: [],
        }, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/parcels`) {
        const body = requestBody(config.data)
        writes.push({ method: config.method, url: config.url, body })
        parcelState = {
          ...parcelDto,
          parcel_id: newParcelId,
          section_name: String(body.section_name),
          land_no: String(body.land_no),
          area_sqm: String(body.area_sqm),
          source_document_id: null,
        }
        return response(parcelState, config, 201)
      }
      if (config.method === 'patch' && config.url === `/valuation/cases/${ids.case}/parcels/${newParcelId}`) {
        const body = requestBody(config.data)
        writes.push({ method: config.method, url: config.url, body })
        parcelState = { ...parcelState!, area_sqm: String(body.area_sqm) }
        return response(parcelState, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) {
        const body = requestBody(config.data)
        writes.push({ method: config.method, url: config.url, body })
        benchmarkState = {
          ...benchmarkDto,
          benchmark_land_id: newBenchmarkId,
          parcel_id: String(body.parcel_id),
          benchmark_land_no: String(body.benchmark_land_no),
          price_zone_no: String(body.price_zone_no),
        }
        return response(benchmarkState, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.find('[data-testid="valuation-step-3"]').exists()).toBe(true))
    await wrapper.get('[data-testid="valuation-step-3"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="data-section-land"]').exists()).toBe(true))
    await wrapper.get('[data-testid="data-section-land"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="valuation-land-context"]').exists()).toBe(true))

    expect(wrapper.find('[data-testid="parcel-editor"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="benchmark-parcel"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="save-parcel"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="save-benchmark"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="valuation-land-context"]').text()).toContain('可直接保留空白並繼續')
    wrapper.unmount()
  })

  it('shows only formally requested Review missing items to the appraiser', async () => {
    const handoff = {
      case_id: ids.case,
      case_status: 'IN_REVIEW',
      display_status: '審查中',
      review_id: ids.review,
      review_status: 'UNDER_REVIEW',
      latest_submission: {
        submission_id: ids.submission,
        submission_no: 1,
        submitted_at: '2026-09-11T00:00:00Z',
      },
      correction: null,
      missing_items: [
        {
          item_code: 'DOC_LAND_REGISTER',
          item_name: '土地登記謄本',
          document_type: 'land-register',
          severity: 'HIGH',
          status: 'OPEN',
          reason: '請補上最新謄本。',
          due_at: '2026-09-20T04:00:00Z',
          notification_status: 'PENDING',
          notified_at: null,
        },
        {
          item_code: 'INTERNAL_NOT_REQUESTED',
          item_name: '尚未正式通知的內部缺件',
          document_type: null,
          severity: 'MEDIUM',
          status: 'OPEN',
          reason: 'Reviewer 尚未送出補件要求。',
          due_at: null,
          notification_status: null,
          notified_at: null,
        },
      ],
    }

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) return response([formDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms/${ids.f03}/f03`) return response(f03Dto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/parcels`) return response([parcelDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/benchmark-lands`) return response([benchmarkDto], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response(documentsDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response({ ...reportProgressDto, report_id: null, version_no: null }, config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/auto-workflow/review`) {
        return response({
          status: 'READY',
          case: caseDto,
          parcel_ids: [ids.parcel],
          benchmark_land_ids: [ids.benchmarkLand],
          f03_form_instance_id: ids.f03,
          report_id: null,
          documents: [],
          candidates: [],
          pending_candidate_count: 0,
          blank_fields_remain: false,
          missing_items: [],
          warnings: [],
          next_action: 'RUN_FORM_CALCULATION',
          draft_pages_1_3_url: null,
          draft_pages_1_6_url: null,
          form_guidance: [],
          automatic_pdf_generation_enabled: false,
          automatic_confirmation_export_enabled: false,
          confirmation_export: null,
        }, config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/review-handoff`) return response(handoff, config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/prepare`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.find('[data-testid="valuation-supplement-request"]').exists()).toBe(true))

    const panel = wrapper.get('[data-testid="valuation-supplement-request"]')
    expect(panel.text()).toContain('土地登記謄本')
    expect(panel.text()).toContain('請補上最新謄本')
    expect(panel.text()).not.toContain('尚未正式通知的內部缺件')
    expect(panel.findAll('button').some((button) => button.text().includes('前往文件補件'))).toBe(true)
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
