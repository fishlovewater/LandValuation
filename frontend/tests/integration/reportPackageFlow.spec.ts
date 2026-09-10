import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import AppLayout from '../../src/layouts/AppLayout.vue'
import { http, tokenService } from '../../src/api/http'
import { createAppRouter } from '../../src/router'
import { useAuthStore } from '../../src/stores/auth.store'

const ids = {
  case: '11111111-1111-4111-8111-111111111111',
  report: '12121212-1212-4121-8121-121212121212',
  s01: '13131313-1313-4131-8131-131313131313',
  regional: '14141414-1414-4141-8141-141414141414',
  f02: '15151515-1515-4151-8151-151515151515',
  f03: '16161616-1616-4161-8161-161616161616',
  benchmark: '17171717-1717-4171-8171-171717171717',
  analysis: '18181818-1818-4181-8181-181818181818',
  target: '19191919-1919-4191-8191-191919191919',
  rule: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  validation: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
}

const appraiser = {
  id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  username: 'appraiser.demo',
  email: 'appraiser@example.test',
  displayName: '示範估價人員',
  roles: ['APPRAISER'],
  permissions: ['case.read', 'valuation.read', 'valuation.update', 'valuation.submit_review', 'document.download'],
}

const caseDto = {
  case_id: ids.case,
  case_no: 'NB-2026-0001',
  case_title: '板橋區示範案件',
  case_type: 'LAND_VALUATION',
  requesting_agency: '示範機關',
  valuation_base_date: '2026-09-08',
  city_code: '65000',
  district_code: '65000010',
  land_use_type: 'COMMERCIAL',
  case_status: 'PROCESSING',
  created_by_user_id: appraiser.id,
  updated_by_user_id: appraiser.id,
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
}

const f03Form = {
  form_instance_id: ids.f03,
  case_id: ids.case,
  form_code: 'F03',
  version_no: 1,
  form_status: 'READY',
  form_content: {},
  prepared_date: '2026-09-08',
  source_document_id: null,
  output_document_id: null,
  created_by_user_id: appraiser.id,
  updated_by_user_id: appraiser.id,
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
}

const packageContent = (code: string, formId: string, status = 'DRAFT') => ({
  form_instance_id: formId,
  case_id: ids.case,
  form_code: code,
  version_no: 1,
  form_status: status,
  form_content: {
    report_type: 'REPORT_COMPARISON_COMMERCIAL',
    report_id: ids.report,
  },
  prepared_date: '2026-09-08',
  source_document_id: null,
  output_document_id: null,
  created_by_user_id: appraiser.id,
  updated_by_user_id: appraiser.id,
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
})

const s01Data = {
  district_name: '板橋區',
  district_boundary: '示範段及周邊道路',
  survey_date: '2026-09-08',
  urban_plan_status: '商業區',
  land_use_zone: 'COMMERCIAL',
  observations: [{ item_code: 'urban_plan_status', raw_value: '商業區', source_type: 'MANUAL_CONFIRMED', source_notes: '現勘資料', confirmed_by_user: true }],
  notes: '三頁確認測試',
  site_opinion: '現況可供比較。',
}

const regionalData = {
  benchmark_land_id: ids.benchmark,
  comparison_analysis_id: ids.analysis,
  rule_version_id: ids.rule,
  factor_rows: [{ factor_code: 'LAND_USE_CONTROL', benchmark_confirmed_level: 'L1', source_notes: '正式來源', confirmed_by_user: true, targets: [{ comparison_target_id: ids.target, display_order: 1, confirmed_level: 'L1', source_notes: '正式來源', confirmed_by_user: true }] }],
  other_influences: '無',
  notes: '因素確認完成。',
  calculation_status: 'NOT_CALCULATED',
  calculation_snapshot: {},
}

const f02Data = {
  benchmark_land_id: ids.benchmark,
  comparison_analysis_id: ids.analysis,
  comparison_targets: [{ comparison_target_id: ids.target, display_order: 1, individual_condition_notes: '同質性高', time_adjustment_rate: '0', time_adjustment_confirmed_by_user: false, individual_factors: [], weight: '1', weight_reason: '單一標的', weight_confirmed_by_user: true }],
  benchmark_notes: '正式比較價格說明。',
  notes: '比較標的確認完成。',
  calculation_status: 'NOT_CALCULATED',
  calculation_snapshot: {},
}

function pageResponse(code: string, formId: string, data: Record<string, unknown>) {
  return {
    report_id: ids.report,
    form_instance_id: formId,
    case_id: ids.case,
    page_code: code,
    version_no: 1,
    form_status: 'DRAFT',
    page_schema_version: `${code.toLowerCase()}-draft-v1`,
    context: {},
    warnings: [],
    data,
  }
}

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}

function requestBody(data: unknown): Record<string, unknown> {
  return typeof data === 'string' ? JSON.parse(data) as Record<string, unknown> : (data ?? {}) as Record<string, unknown>
}

describe('persistent report-package form transition', () => {
  const originalAdapter = http.defaults.adapter

  beforeEach(() => {
    setActivePinia(createPinia())
    tokenService.set('report-package-test-token', 1800)
    useAuthStore().user = appraiser
  })

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    tokenService.clear()
    vi.restoreAllMocks()
  })

  it('saves all three DRAFT pages, calculates, validates, then exposes the authoritative package', async () => {
    let packageStatus = 'DRAFT'
    const requests: string[] = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push(`${config.method} ${config.url}`)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}`) return response(caseDto, config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/forms`) {
        return response([f03Form, packageContent('S01', ids.s01, packageStatus), packageContent('F02-RF', ids.regional, packageStatus), packageContent('F02', ids.f02, packageStatus)], config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/documents`) return response([], config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/report-progress`) {
        return response({ report_id: ids.report, report_type: 'REPORT_COMPARISON_COMMERCIAL', version_no: 1, completion_rate: '50.00', sections: [], blocking_errors: [] }, config)
      }
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.report}/pages/S01`) return response(pageResponse('S01', ids.s01, s01Data), config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.report}/pages/F02-RF`) return response(pageResponse('F02-RF', ids.regional, regionalData), config)
      if (config.method === 'get' && config.url === `/valuation/cases/${ids.case}/reports/${ids.report}/pages/F02`) return response(pageResponse('F02', ids.f02, f02Data), config)
      if (config.method === 'patch' && config.url?.includes(`/valuation/cases/${ids.case}/reports/${ids.report}/pages/`)) return response({ ...pageResponse('S01', ids.s01, s01Data), data: requestBody(config.data) }, config)
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.report}/formal-calculation`) return response({ case_id: ids.case, report_id: ids.report, comparison_analysis_id: ids.analysis, rule_version_id: ids.rule, formula_code: 'NTPC_COMPARISON_V1', rounding_code: 'NTPC_LAND_PRICE_V1', benchmark_comparison_price: '125000', targets: [], input_fingerprint: 'fingerprint', calculated_at: '2026-09-08T00:00:00Z' }, config)
      if (config.method === 'post' && config.url === `/valuation/cases/${ids.case}/reports/${ids.report}/formal-validation`) {
        packageStatus = 'CHECKED'
        return response({ validation_run_id: ids.validation, case_id: ids.case, report_id: ids.report, run_status: 'COMPLETED', passed_count: 12, warning_count: 0, failed_count: 0, can_generate_formal_report: true, input_fingerprint: 'fingerprint', findings: [], completed_at: '2026-09-08T00:00:00Z' }, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/valuation/cases/${ids.case}/submit`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="report-package-draft-flow"]').exists()).toBe(true))

    await wrapper.get('[data-testid="report-page-s01-confirm"]').setValue(true)
    await wrapper.get('[data-testid="report-page-f02-rf-confirm"]').setValue(true)
    await wrapper.get('[data-testid="report-page-f02-confirm"]').setValue(true)
    await wrapper.get('[data-testid="save-report-pages"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="run-formal-calculation"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="run-report-formal-validation"]').trigger('click')
    await flushPromises()

    await vi.waitFor(() => expect(wrapper.get('[data-testid="report-package-authoritative"]').exists()).toBe(true))
    expect(wrapper.get('[data-testid="formal-validation-result"]').exists()).toBe(true)
    expect(requests.filter((item) => item.includes('/pages/'))).toEqual([
      `get /valuation/cases/${ids.case}/reports/${ids.report}/pages/S01`,
      `get /valuation/cases/${ids.case}/reports/${ids.report}/pages/F02-RF`,
      `get /valuation/cases/${ids.case}/reports/${ids.report}/pages/F02`,
      `patch /valuation/cases/${ids.case}/reports/${ids.report}/pages/S01`,
      `patch /valuation/cases/${ids.case}/reports/${ids.report}/pages/F02-RF`,
      `patch /valuation/cases/${ids.case}/reports/${ids.report}/pages/F02`,
    ])
    expect(wrapper.get('[data-testid="report-package-authoritative"]').text()).toContain(ids.report)
    wrapper.unmount()
  })
})
