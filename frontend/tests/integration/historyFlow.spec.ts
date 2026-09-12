import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import AppLayout from '../../src/layouts/AppLayout.vue'
import { http, tokenService } from '../../src/api/http'
import { createAppRouter } from '../../src/router'
import type { AuthUser } from '../../src/modules/auth/auth.types'
import { historyApi } from '../../src/modules/history/history.api'
import { caseTypeLabel, formCodeLabel, mapHistoryDocument } from '../../src/modules/history/history.mappers'
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
    await router.push('/app/history/search?keyword=HIST-VAL-001&city_code=31&district_code=3101&sort=updated_at&order=asc&offset=20&limit=20')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('HIST-VAL-001'))

    expect(wrapper.get('[data-testid="history-advanced-toggle"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-testid="history-advanced-filters"]').isVisible()).toBe(true)
    expect(wrapper.find('[data-testid="history-city-code"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="history-district-code"]').findAll('option')).toHaveLength(30)
    expect((wrapper.get('[data-testid="history-district-code"]').element as HTMLSelectElement).value).toBe('65000010')
    expect(requests[0]?.params).toEqual({
      keyword: 'HIST-VAL-001',
      city_code: '65000000',
      district_code: '65000010',
      sort: 'updated_at',
      order: 'asc',
      offset: 20,
      limit: 20,
    })
    const caseRow = wrapper.get('[data-testid="history-case-row-71000000-0000-4000-8000-000000000001"]')
    expect(caseRow.text()).toContain('新北市 板橋區')
    expect(caseRow.text()).not.toContain('3101')
    expect(caseRow.text()).toContain('有案件資料')
    expect(caseRow.text()).toContain('尚無附件')

    await wrapper.get('[data-testid="history-keyword"]').setValue('HIST-REV-001')
    expect((wrapper.get('[data-testid="history-keyword"]').element as HTMLInputElement).value).toBe('HIST-REV-001')
    await wrapper.get('[data-testid="history-search-submit"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.keyword).toBe('HIST-REV-001')
    expect(router.currentRoute.value.query.offset).toBeUndefined()
    expect(requests.at(-1)?.params).toEqual({
      keyword: 'HIST-REV-001',
      city_code: '65000000',
      district_code: '65000010',
      order: 'asc',
      offset: 0,
      limit: 20,
    })
    wrapper.unmount()
  })

  it('keeps an invalid date range on the client instead of sending a bad history query', async () => {
    useAuthStore().user = appraiser
    const requests: Array<{ params?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ params: config.params })
      return response({
        items: [structuredCase],
        total: 1,
        offset: 0,
        limit: 20,
        permissions: { can_view_valuation: true, can_view_review: false },
      }, config)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/history/search')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('HIST-VAL-001'))
    expect(requests).toHaveLength(1)

    await wrapper.get('[data-testid="history-advanced-toggle"]').trigger('click')
    await wrapper.get('[data-testid="history-date-from"]').setValue('2026-09-10')
    await wrapper.get('[data-testid="history-date-to"]').setValue('2026-09-01')
    await wrapper.get('[data-testid="history-search-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('日期起日不可晚於日期迄日')
    expect(requests).toHaveLength(1)
    expect(router.currentRoute.value.query.dateFrom).toBeUndefined()
    expect(router.currentRoute.value.query.dateTo).toBeUndefined()
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
      city_code: '65000000',
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
            case_type: 'LAND',
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
              { decision_id: '75000000-0000-4000-8000-000000000003', decision: 'ACCEPTED', before_value: { review_status: 'RECEIVED' }, after_value: { review_status: 'REVIEW_COMPLETED' }, decided_at: '2026-08-20T11:30:00+08:00' },
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
      if (config.url === `/history/documents/${ids.missingDocument}/text-preview`) {
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
    expect(wrapper.text()).toContain('土地徵收補償市價查估案件')
    expect(wrapper.text()).not.toContain('LAND')
    expect(wrapper.get('[data-testid="history-tab-review"]').text()).toContain('11')
    expect(wrapper.text()).not.toContain('估價資料')
    expect(wrapper.text()).not.toContain('object_key')
    expect(wrapper.text()).not.toContain('cases/')

    await wrapper.get('[data-testid="history-tab-timeline"]').trigger('click')
    const timelineSection = wrapper.get('[data-testid="history-timeline-section"]')
    expect(timelineSection.get('[data-testid="history-timeline-filter-all"]').text()).toContain('全部')
    expect(timelineSection.find('[data-testid="history-timeline-filter-review"]').exists()).toBe(true)
    await timelineSection.get('[data-testid="history-timeline-filter-review"]').trigger('click')
    expect(timelineSection.text()).toContain('風險等級：高風險')
    expect(timelineSection.text()).toContain('決定：接受系統結果')
    expect(timelineSection.text()).not.toContain('風險等級：HIGH')
    expect(timelineSection.text()).not.toContain('決定：ACCEPTED')
    expect(timelineSection.text()).not.toContain('history-demo-missing.docx')

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
    expect(reviewSection.text()).toContain('修改前內容')
    expect(reviewSection.text()).toContain('審查狀態：已收件')
    expect(reviewSection.text()).toContain('修改後內容')
    expect(reviewSection.text()).toContain('審查狀態：審查完成')
    expect(reviewSection.text()).not.toContain('RECEIVED')
    expect(reviewSection.text()).not.toContain('REVIEW_COMPLETED')

    expect(reviewSection.text()).not.toContain('FUTURE_REVIEW_KIND')
    expect(reviewSection.text()).not.toContain('FUTURE_REVIEW_STATUS')
    expect(reviewSection.text()).not.toContain('FUTURE_FINDING_CODE')
    expect(reviewSection.text()).not.toContain('FUTURE_FINDING_TYPE')
    expect(reviewSection.text()).not.toContain('FUTURE_SEVERITY')
    expect(reviewSection.text()).not.toContain('FUTURE_FINDING_STATUS')
    expect(reviewSection.text()).not.toContain('FUTURE_RISK_LEVEL')
    expect(reviewSection.text()).not.toContain('FUTURE_DECISION')
    expect(reviewSection.findAll('details')).toHaveLength(0)

    await wrapper.get('[data-testid="history-tab-overview"]').trigger('click')
    expect(wrapper.text()).toContain('智慧審查文件')
    expect(wrapper.text()).toContain('1 份目前文件')
    expect(wrapper.text()).toContain('目前版本')
    await wrapper.get(`[data-testid="history-preview-${ids.missingDocument}"]`).trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="history-document-preview"]').exists()).toBe(true))
    await vi.waitFor(() => expect(wrapper.text()).toContain('文件目前無法下載'))
    expect(requests).toContain(`get /history/documents/${ids.missingDocument}/text-preview`)

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
    expect(mapHistoryDocument({ ...base, document_id: ids.candidateExport, document_type: 'candidate-confirmation-export' }).documentTypeLabel).toBe('辨識結果確認匯出')
    expect(mapHistoryDocument({ ...base, document_id: ids.draftReport, document_type: 'generated-draft-report' }).documentTypeLabel).toBe('草稿報告')
    expect(mapHistoryDocument({ ...base, document_id: ids.generatedReport, document_type: 'generated-report' }).documentTypeLabel).toBe('正式報告')
    expect(mapHistoryDocument({ ...base, document_id: ids.unknownDocument, document_type: 'future-document-kind' }).documentTypeLabel).toBe('其他文件')
  })

  it('maps internal case and form codes to user-facing official names', () => {
    expect(caseTypeLabel('LAND')).toBe('土地徵收補償市價查估案件')
    expect(caseTypeLabel('FUTURE_CASE_KIND')).toBe('其他案件類型')
    expect(formCodeLabel('F03')).toBe('比準地地價估計表')
    expect(formCodeLabel('F02-RF')).toBe('影響地價區域因素分析明細表')
    expect(formCodeLabel('FUTURE_FORM')).toBe('查估書表')
  })
})

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}
