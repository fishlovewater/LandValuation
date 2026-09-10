import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { http } from '../../src/api/http'
import ComparisonSetupPanel from '../../src/modules/valuation/components/ComparisonSetupPanel.vue'
import type { ReportPageResponseDto } from '../../src/modules/valuation/valuation.types'

const caseId = '11111111-1111-4111-8111-111111111111'
const reportId = '22222222-2222-4222-8222-222222222222'
const benchmarkId = '33333333-3333-4333-8333-333333333333'

const page: ReportPageResponseDto = {
  report_id: reportId,
  form_instance_id: '44444444-4444-4444-8444-444444444444',
  case_id: caseId,
  page_code: 'F02',
  version_no: 1,
  form_status: 'DRAFT',
  page_schema_version: 'v1',
  context: {},
  warnings: [],
  data: {
    comparison_workflow_enabled: true,
    benchmark_land_id: null,
    comparison_analysis_id: null,
  },
}

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}

describe('ComparisonSetupPanel', () => {
  const originalAdapter = http.defaults.adapter

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    vi.restoreAllMocks()
  })

  it('creates one traceable comparison target and never asks the user for a raw analysis id', async () => {
    const writes: Array<Record<string, unknown>> = []
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${caseId}/comparison-setup`) {
        return response({
          parcels: [],
          benchmark_lands: [{ benchmark_land_id: benchmarkId, label: 'B-001｜Z-01' }],
          analyses: [],
        }, config)
      }
      if (config.method === 'post' && config.url === `/valuation/cases/${caseId}/comparison-setup`) {
        writes.push(JSON.parse(String(config.data)) as Record<string, unknown>)
        return response({
          comparison_analysis_id: '55555555-5555-4555-8555-555555555555',
          benchmark_land_id: benchmarkId,
          report_id: reportId,
          targets: [{
            comparison_target_id: '66666666-6666-4666-8666-666666666666',
            transaction_id: '77777777-7777-4777-8777-777777777777',
            transaction_no: 'TX-001',
            transaction_date: '2026-08-01',
            normal_land_unit_price: '125000',
            weight: '1',
          }],
        }, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const wrapper = mount(ComparisonSetupPanel, { props: { caseId, reportId, page } })
    await flushPromises()

    expect(wrapper.find('input[data-report-field="comparison_analysis_id"]').exists()).toBe(false)
    await wrapper.get('[data-testid="comparison-transaction-no-0"]').setValue('TX-001')
    await wrapper.get('[data-testid="comparison-transaction-date-0"]').setValue('2026-08-01')
    await wrapper.get('[data-testid="comparison-total-price-0"]').setValue('5000000')
    await wrapper.get('[data-testid="comparison-unit-price-0"]').setValue('125000')
    await wrapper.get('[data-testid="comparison-weight-0"]').setValue('1')
    await wrapper.get('[data-testid="comparison-source-notes-0"]').setValue('實價登錄第 1 筆，人工確認')
    await wrapper.get('[data-testid="create-comparison-setup"]').trigger('submit')
    await flushPromises()

    expect(writes).toHaveLength(1)
    expect(writes[0]).toEqual({
      report_id: reportId,
      benchmark_land_id: benchmarkId,
      targets: [{
        transaction_no: 'TX-001',
        transaction_date: '2026-08-01',
        transaction_total_price: '5000000',
        normal_land_unit_price: '125000',
        weight: '1',
        source_notes: '實價登錄第 1 筆，人工確認',
        subject_address: null,
        land_area_sqm: null,
      }],
      notes: null,
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('persists the no-comparison workflow explicitly on the F02 draft', async () => {
    let patchBody: Record<string, unknown> | null = null
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/valuation/cases/${caseId}/comparison-setup`) {
        return response({ parcels: [], benchmark_lands: [], analyses: [] }, config)
      }
      if (config.method === 'patch' && config.url === `/valuation/cases/${caseId}/reports/${reportId}/pages/F02`) {
        patchBody = JSON.parse(String(config.data)) as Record<string, unknown>
        return response({ ...page, data: { ...page.data, comparison_workflow_enabled: false } }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const wrapper = mount(ComparisonSetupPanel, { props: { caseId, reportId, page } })
    await flushPromises()
    await wrapper.get('[data-testid="comparison-workflow-enabled"]').setValue(false)
    await flushPromises()

    expect(patchBody).toEqual({ comparison_workflow_enabled: false })
    expect(wrapper.get('[data-testid="comparison-disabled-note"]').text()).toContain('不使用比較標的')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
})