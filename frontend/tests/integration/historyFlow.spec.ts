import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import AppLayout from '../../src/layouts/AppLayout.vue'
import { http, tokenService } from '../../src/api/http'
import { createAppRouter } from '../../src/router'
import type { AuthUser } from '../../src/modules/auth/auth.types'
import { historyApi } from '../../src/modules/history/history.api'
import { mapHistoryDocument } from '../../src/modules/history/history.mappers'
import { useAuthStore } from '../../src/stores/auth.store'

const ids = {
  structuredCase: '71000000-0000-4000-8000-000000000001',
  missingObjectCase: '71000000-0000-4000-8000-000000000002',
  missingDocument: '77000000-0000-4000-8000-000000000002',
  candidateExport: '77000000-0000-4000-8000-000000000003',
  draftReport: '77000000-0000-4000-8000-000000000004',
  generatedReport: '77000000-0000-4000-8000-000000000005',
  unknownDocument: '77000000-0000-4000-8000-000000000006',
}

const appraiser: AuthUser = {
  id: '78000000-0000-4000-8000-000000000001',
  username: 'history_appraiser',
  email: 'history_appraiser@example.test',
  displayName: 'History 測試估價人員',
  roles: ['APPRAISER'],
  permissions: [],
}

const reviewer: AuthUser = {
  id: '78000000-0000-4000-8000-000000000002',
  username: 'history_reviewer',
  email: 'history_reviewer@example.test',
  displayName: 'History 測試審查人員',
  roles: ['REVIEWER'],
  permissions: [],
}

const structuredCase = {
  case_id: ids.structuredCase,
  case_no: 'HIST-VAL-001',
  case_title: 'History 測試－只有估價結構化資料',
  case_type: 'LAND',
  valuation_base_date: '2026-08-01',
  city_code: '31',
  district_code: '3101',
  case_status: 'CORRECTION',
  updated_at: '2026-08-22T09:00:00+08:00',
  review_status: null,
  received_at: null,
  completed_at: null,
  current_risk_level: null,
  history_result: 'CORRECTION',
  visible_modules: ['valuation'],
  has_structured_data: true,
  has_document_metadata: false,
}

const missingDocument = {
  document_id: ids.missingDocument,
  case_id: ids.missingObjectCase,
  document_type: 'review-report',
  source_module: 'review',
  file_name: 'history-demo-missing.docx',
  content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  created_at: '2026-08-20T12:00:00+08:00',
  updated_at: null,
  document_group_id: ids.missingDocument,
  version_no: 1,
  is_active: true,
  file_size_bytes: 128,
  checksum_sha256: 'missing-checksum',
  download_available: null,
}

describe('history demo flow', () => {
  const originalAdapter = http.defaults.adapter

  beforeEach(() => {
    setActivePinia(createPinia())
    tokenService.clear()
    tokenService.set('history-test-token', 1800)
  })

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    tokenService.clear()
    vi.restoreAllMocks()
  })

  it('serializes supported search query, restores it from the URL, and keeps structured-only cases visible', async () => {
    useAuthStore().user = appraiser
    const requests: Array<{ url?: string; params?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ url: config.url, params: config.params })
      expect(config.method).toBe('get')
      expect(config.url).toBe('/history/cases')
      return response({
        items: [structuredCase],
        total: 1,
        offset: 20,
        limit: 20,
        permissions: { can_view_valuation: true, can_view_review: false },
      }, config)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/history/search?keyword=HIST-VAL-001&city_code=31&sort=updated_at&order=asc&offset=20&limit=20')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('HIST-VAL-001'))

    expect(requests[0]?.params).toEqual({
      keyword: 'HIST-VAL-001',
      city_code: '31',
      sort: 'updated_at',
      order: 'asc',
      offset: 20,
      limit: 20,
    })
    expect(wrapper.get('[data-testid="history-case-row-71000000-0000-4000-8000-000000000001"]').text()).toContain('有結構化資料')
    expect(wrapper.get('[data-testid="history-case-row-71000000-0000-4000-8000-000000000001"]').text()).toContain('尚無文件 metadata')

    await wrapper.get('[data-testid="history-keyword"]').setValue('HIST-REV-001')
    expect((wrapper.get('[data-testid="history-keyword"]').element as HTMLInputElement).value).toBe('HIST-REV-001')
    await wrapper.get('[data-testid="history-search-submit"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.keyword).toBe('HIST-REV-001')
    expect(requests.at(-1)?.params).toEqual({
      keyword: 'HIST-REV-001',
      city_code: '31',
      order: 'asc',
      offset: 20,
      limit: 20,
    })
    wrapper.unmount()
  })

  it('hides review-only search controls and strips tampered URL filters before transport for an appraiser', async () => {
    useAuthStore().user = appraiser
    const requests: Array<{ params?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ params: config.params })
      return response({
        items: [structuredCase],
        total: 1,
        offset: 20,
        limit: 20,
        permissions: { can_view_valuation: true, can_view_review: false },
      }, config)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/history/search?city_code=31&result=PASSED&date_field=received_at&sort=risk_level&order=asc&offset=20&limit=20')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('HIST-VAL-001'))

    expect(wrapper.get('[data-testid="history-result"]').findAll('option').map((option) => option.element.getAttribute('value'))).toEqual(['', 'CORRECTION', 'IN_PROGRESS'])
    expect(wrapper.get('[data-testid="history-date-field"]').findAll('option').map((option) => option.element.getAttribute('value'))).toEqual(['updated_at'])
    expect(wrapper.get('[data-testid="history-sort"]').findAll('option').map((option) => option.element.getAttribute('value'))).toEqual(['updated_at'])
    expect(requests[0]?.params).toEqual({
      city_code: '31',
      order: 'asc',
      offset: 20,
      limit: 20,
    })
    wrapper.unmount()
  })

  it('drops malformed result values before transport instead of sending an OpenAPI-invalid query', async () => {
    const requests: Array<{ params?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ params: config.params })
      return response({
        items: [],
        total: 0,
        offset: 0,
        limit: 20,
        permissions: { can_view_valuation: false, can_view_review: true },
      }, config)
    }) as unknown as typeof originalAdapter

    await historyApi.listCases(
      { result: 'NOT_A_RESULT' as never, sort: 'risk_level', dateField: 'completed_at', order: 'sideways' as never },
      undefined,
      reviewer.roles,
    )

    expect(requests[0]?.params).toEqual({
      sort: 'risk_level',
      date_field: 'completed_at',
      offset: 0,
      limit: 20,
    })
  })

  it('fails closed when the History API is called with an unknown role', async () => {
    const requests: Array<{ params?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ params: config.params })
      return response({
        items: [],
        total: 0,
        offset: 0,
        limit: 20,
        permissions: { can_view_valuation: false, can_view_review: false },
      }, config)
    }) as unknown as typeof originalAdapter

    await historyApi.listCases(
      { result: 'CORRECTION', sort: 'updated_at', dateField: 'updated_at' },
      undefined,
      ['UNKNOWN_ROLE'],
    )

    expect(requests[0]?.params).toEqual({ offset: 0, limit: 20 })
  })

  it('renders only authorized review data and turns a missing object into a safe download state', async () => {
    useAuthStore().user = reviewer
    const requests: string[] = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push(`${config.method} ${config.url}`)
      if (config.url === `/history/cases/${ids.missingObjectCase}`) {
        return response({
          case: {
            case_id: ids.missingObjectCase,
            case_no: 'HIST-REV-001',
            case_title: 'History 測試－Review metadata 但 MinIO 缺檔',
            case_status: 'REVIEWING',
            valuation_base_date: '2026-08-02',
            city_code: '31',
            district_code: '3102',
            created_at: '2026-08-02T09:00:00+08:00',
            updated_at: '2026-08-20T12:00:00+08:00',
          },
          parcels: [],
          documents: [missingDocument],
          valuation: null,
          review: {
            reviews: [
              { review_id: '75000000-0000-4000-8000-000000000001', review_type: 'SMART_REVIEW', review_status: 'COMPLETED', received_at: '2026-08-19T09:00:00+08:00', started_at: '2026-08-20T10:00:00+08:00', completed_at: '2026-08-20T12:00:00+08:00' },
              { review_id: '75000000-0000-4000-8000-000000000004', review_type: 'FUTURE_REVIEW_KIND', review_status: 'FUTURE_REVIEW_STATUS', received_at: '2026-08-21T09:00:00+08:00' },
            ],
            findings: [
              { finding_id: '75000000-0000-4000-8000-000000000005', finding_code: 'GRADE_MISMATCH', finding_type: 'AI', severity: 'HIGH', status: 'REQUIRES_SUPPLEMENT', title: '比較等級需補件', created_at: '2026-08-20T11:00:00+08:00' },
              { finding_id: '75000000-0000-4000-8000-000000000006', finding_code: 'FUTURE_FINDING_CODE', finding_type: 'FUTURE_FINDING_TYPE', severity: 'FUTURE_SEVERITY', status: 'FUTURE_FINDING_STATUS', title: '未來疑點', created_at: '2026-08-21T11:00:00+08:00' },
            ],
            risk_summaries: [
              { risk_summary_id: '75000000-0000-4000-8000-000000000002', overall_risk_level: 'HIGH', generated_at: '2026-08-20T11:00:00+08:00' },
              { risk_summary_id: '75000000-0000-4000-8000-000000000007', overall_risk_level: 'FUTURE_RISK_LEVEL', summary: '未來風險摘要', generated_at: '2026-08-21T11:00:00+08:00' },
            ],
            decisions: [
              { decision_id: '75000000-0000-4000-8000-000000000003', decision: 'ACCEPTED', decided_at: '2026-08-20T11:30:00+08:00' },
              { decision_id: '75000000-0000-4000-8000-000000000008', decision: 'PARTIALLY_ACCEPTED', decided_at: '2026-08-20T11:40:00+08:00' },
              { decision_id: '75000000-0000-4000-8000-000000000009', decision: 'REQUIRES_SUPPLEMENT', decided_at: '2026-08-20T11:50:00+08:00' },
              { decision_id: '75000000-0000-4000-8000-000000000010', decision: 'EXPERT_REVIEW', decided_at: '2026-08-20T12:00:00+08:00' },
              { decision_id: '75000000-0000-4000-8000-000000000011', decision: 'FUTURE_DECISION', decided_at: '2026-08-21T12:00:00+08:00' },
            ],
          },
          permissions: { can_view_valuation: false, can_view_review: true },
        }, config)
      }
      if (config.url === `/history/documents/${ids.missingDocument}/download`) {
        return Promise.reject({
          isAxiosError: true,
          response: { status: 404, data: { error: { code: 'DOCUMENT_OBJECT_MISSING' } } },
        })
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/history/cases/${ids.missingObjectCase}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('HIST-REV-001'))

    expect(wrapper.text()).toContain('審查資料')
    expect(wrapper.text()).not.toContain('估價資料')
    expect(wrapper.text()).not.toContain('object_key')
    expect(wrapper.text()).not.toContain('cases/')
    expect(wrapper.text()).toContain('風險等級：高風險')
    expect(wrapper.text()).toContain('決定：接受系統結果')
    expect(wrapper.text()).not.toContain('風險等級：HIGH')
    expect(wrapper.text()).not.toContain('決定：ACCEPTED')

    await wrapper.get('[data-testid="history-tab-review"]').trigger('click')
    const reviewSection = wrapper.get('[data-testid="history-review-section"]')
    expect(reviewSection.text()).toContain('智慧審查')
    expect(reviewSection.text()).toContain('部分接受')
    expect(reviewSection.text()).toContain('要求補件')
    expect(reviewSection.text()).toContain('轉交專家審查')
    expect(reviewSection.text()).toContain('智慧分析')
    expect(reviewSection.text()).toContain('待補件')
    expect(reviewSection.text()).toContain('其他檢核項目')
    expect(reviewSection.text()).toContain('其他檢核類型')
    expect(reviewSection.text()).toContain('未定義疑點狀態')
    expect(reviewSection.text()).toContain('一般')
    expect(reviewSection.text()).toContain('其他審查類型')
    expect(reviewSection.text()).toContain('未知狀態')
    expect(reviewSection.text()).toContain('未標示風險')

    const reviewWithoutTechnicalDetails = reviewSection.element.cloneNode(true) as HTMLElement
    reviewWithoutTechnicalDetails.querySelectorAll('details').forEach((details) => details.remove())
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_REVIEW_KIND')
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_REVIEW_STATUS')
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_FINDING_CODE')
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_FINDING_TYPE')
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_SEVERITY')
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_FINDING_STATUS')
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_RISK_LEVEL')
    expect(reviewWithoutTechnicalDetails.textContent).not.toContain('FUTURE_DECISION')
    expect(reviewSection.findAll('details').every((details) => !(details.element as HTMLDetailsElement).open)).toBe(true)
    expect(reviewSection.findAll('details').some((details) => details.text().includes('FUTURE_DECISION'))).toBe(true)

    await wrapper.get('[data-testid="history-tab-overview"]').trigger('click')
    await wrapper.get(`[data-testid="history-download-${ids.missingDocument}"]`).trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('文件目前無法下載'))
    expect(requests).toContain(`get /history/documents/${ids.missingDocument}/download`)
    wrapper.unmount()
  })

  it('maps valuation document types to readable labels and keeps unknown types diagnosable', () => {
    const base = {
      ...missingDocument,
      source_module: 'valuation' as const,
      download_available: false,
    }
    expect(mapHistoryDocument({ ...base, document_id: ids.candidateExport, document_type: 'candidate-confirmation-export' }).documentTypeLabel).toBe('候選確認匯出')
    expect(mapHistoryDocument({ ...base, document_id: ids.draftReport, document_type: 'generated-draft-report' }).documentTypeLabel).toBe('草稿報告')
    expect(mapHistoryDocument({ ...base, document_id: ids.generatedReport, document_type: 'generated-report' }).documentTypeLabel).toBe('正式報告')
    expect(mapHistoryDocument({ ...base, document_id: ids.unknownDocument, document_type: 'future-document-kind' }).documentTypeLabel).toBe('其他文件（future-document-kind）')
  })
})

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}
