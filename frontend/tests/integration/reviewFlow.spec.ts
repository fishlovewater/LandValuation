import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import AppLayout from '../../src/layouts/AppLayout.vue'
import { http, tokenService } from '../../src/api/http'
import { createAppRouter } from '../../src/router'
import type { AuthUser } from '../../src/modules/auth/auth.types'
import { useAuthStore } from '../../src/stores/auth.store'

const ids = {
  review: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  case: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
}

const reviewer: AuthUser = {
  id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  username: 'reviewer.demo',
  email: 'reviewer@example.test',
  displayName: '示範審查人員',
  roles: ['REVIEWER'],
  permissions: ['case.read', 'review.execute', 'review.decide'],
}

const summaryDto = {
  status_counts: { in_progress: 1 },
  high_risk_count: 1,
  open_finding_count: 1,
  missing_item_count: 0,
}

const queueItemDto = {
  review_id: ids.review,
  case_id: ids.case,
  case_no: 'NB-2026-0008',
  case_title: '新店區安康段土地估價',
  district_code: '新店區',
  review_status: 'REVIEW_REQUIRED',
  current_risk_level: 'HIGH',
  missing_item_count: 0,
  high_count: 1,
  medium_count: 0,
  low_count: 0,
  received_at: '2026-09-07T01:00:00Z',
  due_at: null,
  assigned_reviewer_display_name: '示範審查人員',
  latest_run: {
    validation_run_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    run_no: 1,
    run_status: 'COMPLETED',
  },
  urgency_level: 'NORMAL',
  remaining_days: null,
  correction_round: 0,
  latest_correction_status: null,
}

const idsWithDetail = {
  review: ids.review,
  case: ids.case,
  run: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  finding: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
  document: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
  decision: '11111111-1111-4111-8111-111111111111',
}

const detailBase = {
  case: {
    case_id: idsWithDetail.case,
    case_no: 'NB-2026-0008',
    case_title: '新店區安康段土地估價',
    district_code: '新店區',
    valuation_base_date: '2026-08-01',
    case_status: 'IN_REVIEW',
  },
  review: {
    review_id: idsWithDetail.review,
    case_id: idsWithDetail.case,
    review_type: 'FORMAL',
    review_status: 'REVIEW_REQUIRED',
    started_by_user_id: null,
    started_at: '2026-09-07T01:00:00Z',
    completed_at: null,
    received_at: '2026-09-07T01:00:00Z',
    due_at: null,
    assigned_reviewer_id: reviewer.id,
    manual_priority: 0,
    manual_priority_reason: null,
    current_risk_level: 'HIGH',
    high_count: 1,
    medium_count: 0,
    low_count: 0,
    missing_item_count: 0,
    latest_validation_run_id: idsWithDetail.run,
    latest_submission_id: null,
  },
  submission_id: null,
  submission_no: null,
  submitted_at: '2026-09-07T01:00:00Z',
  input_fingerprint: null,
  documents: [
    {
      document_id: idsWithDetail.document,
      document_type: 'original',
      original_filename: 'complete-report.pdf',
      mime_type: 'application/pdf',
      version_no: 1,
      is_active: true,
      uploaded_at: '2026-09-07T00:59:00Z',
    },
  ],
  missing_items: [],
  runs: [
    {
      validation_run_id: idsWithDetail.run,
      case_id: idsWithDetail.case,
      review_id: idsWithDetail.review,
      run_no: 1,
      run_status: 'COMPLETED',
      passed_count: 8,
      warning_count: 1,
      failed_count: 0,
      started_at: '2026-09-07T01:00:00Z',
      completed_at: '2026-09-07T01:01:00Z',
      triggered_by_user_id: reviewer.id,
      rule_version_id: null,
      model_id: null,
      prompt_version: null,
      error_code: null,
      error_message: null,
    },
  ],
  findings: [
    {
      finding_id: idsWithDetail.finding,
      review_id: idsWithDetail.review,
      validation_run_id: idsWithDetail.run,
      finding_code: 'ADJUSTMENT_RATE',
      finding_type: 'RULE',
      severity: 'ERROR',
      title: '調整率需要覆核',
      description: '報告值與系統規則結果不同，請確認依據。',
      status: 'OPEN',
      document_id: idsWithDetail.document,
      document_version: 1,
      page_number: 3,
      field_path: 'comparison.adjustment_rate',
      source_evidence: [],
      reported_text: '報告記載 10%',
      reported_value: '0.10',
      legal_basis: [],
      reported_grade: null,
      system_grade: null,
      reported_adjustment_rate: '0.10',
      system_adjustment_rate: '0.08',
      comparison_result: { system_value: '0.08' },
      recommended_action: { label: '請確認調整依據' },
      ai_reasoning_summary: '系統發現調整率超過目前規則容許範圍。',
      ai_confidence: '0.91',
      ai_status: 'READY',
      supersedes_finding_id: null,
      rule_version_id: null,
      created_at: '2026-09-07T01:01:00Z',
    },
  ],
  risk_summary: {
    risk_summary_id: '22222222-2222-4222-8222-222222222222',
    review_id: idsWithDetail.review,
    validation_run_id: idsWithDetail.run,
    overall_risk_level: 'HIGH',
    risk_score: '0.80',
    summary: '有一項高風險疑點。',
    high_count: 1,
    medium_count: 0,
    low_count: 0,
    missing_item_count: 0,
    risk_reasons: [],
    generated_at: '2026-09-07T01:02:00Z',
  },
  decisions: [],
  version_diffs: [],
  report_document: null,
  generated_reports: [],
  correction_requests: [],
}

describe('review demo flow', () => {
  const originalAdapter = http.defaults.adapter

  beforeEach(() => {
    setActivePinia(createPinia())
    tokenService.clear()
    const store = useAuthStore()
    store.user = reviewer
    tokenService.set('review-test-token', 1800)
  })

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    tokenService.clear()
    vi.restoreAllMocks()
  })

  it('reloads the queue from KPI filters, keeps the selected review id, and preserves queue query state on return', async () => {
    const requests: Array<{ method?: string; url?: string; params?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, params: config.params })
      if (config.method === 'get' && config.url === '/review/workbench/summary') {
        return response(summaryDto, config)
      }
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        return response({ items: [queueItemDto], total: 1, limit: 20, offset: 20 }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/review/dashboard?sortBy=caseNo&sortDirection=asc&page=2&pageSize=20')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('NB-2026-0008'))

    await wrapper.get('[data-testid="kpi-in-progress"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.statusGroup).toBe('in_progress')
    expect(requests.filter((request) => request.url === '/review/workbench/cases')).toHaveLength(2)

    await wrapper.get(`[data-testid="review-case-row-${ids.review}"]`).trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('review-workbench'))
    expect(router.currentRoute.value.params.reviewId).toBe(ids.review)

    await wrapper.get('[data-testid="review-back-to-queue"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('review-dashboard'))
    expect(router.currentRoute.value.query).toMatchObject({
      sortBy: 'caseNo',
      sortDirection: 'asc',
      page: '2',
      pageSize: '20',
      statusGroup: 'in_progress',
    })
    wrapper.unmount()
  })

  it('merges partial table queries and ignores an older queue response after a newer refresh', async () => {
    const pendingQueueResponses: Array<{
      config: Parameters<NonNullable<typeof http.defaults.adapter>>[0]
      resolve: (value: ReturnType<typeof response>) => void
    }> = []
    let queueCall = 0
    const initialItem = { ...queueItemDto, case_no: 'NB-2026-OLD-INITIAL' }
    const olderItem = { ...queueItemDto, review_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01', case_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb01', case_no: 'NB-2026-OLDER' }
    const newerItem = { ...queueItemDto, review_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02', case_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb02', case_no: 'NB-2026-NEWER' }

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        queueCall += 1
        if (queueCall === 1) return response({ items: [initialItem], total: 1, limit: 20, offset: 20 }, config)
        const deferred = new Promise<ReturnType<typeof response>>((resolve) => {
          pendingQueueResponses.push({ config, resolve })
        })
        return deferred
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/review/dashboard?status=REVIEW_REQUIRED&riskLevel=HIGH&statusGroup=in_progress&sortBy=caseNo&sortDirection=asc&page=2&pageSize=20')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('NB-2026-OLD-INITIAL'))

    await wrapper.get('[data-sort="name"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.query.sortBy).toBe('name'))
    await vi.waitFor(() => expect(pendingQueueResponses).toHaveLength(1))
    expect(router.currentRoute.value.query).toMatchObject({
      status: 'REVIEW_REQUIRED',
      riskLevel: 'HIGH',
      statusGroup: 'in_progress',
      sortBy: 'name',
      sortDirection: 'asc',
      page: '2',
      pageSize: '20',
    })
    expect(pendingQueueResponses[0].config.params).toMatchObject({
      status: 'REVIEW_REQUIRED',
      risk_level: 'HIGH',
      status_group: 'in_progress',
      limit: 20,
      offset: 20,
    })

    await wrapper.get('[data-testid="refresh-review-queue"]').trigger('click')
    await vi.waitFor(() => expect(pendingQueueResponses).toHaveLength(2))

    pendingQueueResponses[1].resolve(response({ items: [newerItem], total: 1, limit: 20, offset: 20 }, pendingQueueResponses[1].config))
    await vi.waitFor(() => expect(wrapper.text()).toContain('NB-2026-NEWER'))
    pendingQueueResponses[0].resolve(response({ items: [olderItem], total: 1, limit: 20, offset: 20 }, pendingQueueResponses[0].config))
    await flushPromises()
    expect(wrapper.text()).toContain('NB-2026-NEWER')
    expect(wrapper.text()).not.toContain('NB-2026-OLDER')
    wrapper.unmount()
  })

  it('keeps a finding visible, synchronizes its evidence, saves one exact decision, and refreshes summary and queue after each transition', async () => {
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    let detailDto = structuredClone(detailBase)
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        return response({ items: [queueItemDto], total: 1, limit: 20, offset: 0 }, config)
      }
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(detailDto, config)
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}/documents/${idsWithDetail.document}/content`) {
        return response(new Blob(['%PDF-1.7 evidence']), config)
      }
      if (config.method === 'post' && config.url === `/review/findings/${idsWithDetail.finding}/triage`) {
        expect(requestBody(config.data)).toEqual({
          review_id: idsWithDetail.review,
          decision: 'DISMISSED_FALSE_POSITIVE',
          reason: '依據報告與伺服器規則結果確認。',
        })
        detailDto = {
          ...detailDto,
          findings: detailDto.findings.map((finding) => ({ ...finding, status: 'DISMISSED_FALSE_POSITIVE' })),
          decisions: [{
            decision_id: idsWithDetail.decision,
            review_id: idsWithDetail.review,
            finding_id: idsWithDetail.finding,
            decision: 'DISMISSED_FALSE_POSITIVE',
            reason: '依據報告與伺服器規則結果確認。',
            decided_by_user_id: reviewer.id,
            decided_at: '2026-09-07T01:03:00Z',
            request_id: null,
            before_value: null,
            after_value: null,
          }],
        }
        return response(detailDto.decisions[0], config, 201)
      }
      if (config.method === 'post' && config.url === `/review/cases/${idsWithDetail.review}/complete-review`) {
        expect(requestBody(config.data)).toEqual({ reason: '依審查工作台確認結果完成審查。' })
        detailDto = { ...detailDto, review: { ...detailDto.review, review_status: 'REVIEW_COMPLETED' } }
        return response(detailDto.decisions[0], config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}?sortBy=caseNo&page=2&pageSize=20`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('調整率需要覆核'))

    expect(wrapper.get('[data-testid="report-value"]').text()).toContain('0.10')
    expect(wrapper.get('[data-testid="system-value"]').text()).toContain('0.08')
    expect(wrapper.get('[data-testid="ai-explanation"]').text()).toContain('系統發現')
    await wrapper.get('#finding-decision').setValue('DISMISSED_FALSE_POSITIVE')
    await wrapper.get('[data-testid="save-finding-decision"]').trigger('click')
    expect(wrapper.text()).toContain('請填寫審查理由')
    expect(requests.filter((request) => request.url?.includes('/triage'))).toHaveLength(0)

    await wrapper.get('[data-testid="finding-reason"]').setValue('依據報告與伺服器規則結果確認。')
    await wrapper.get('[data-testid="save-finding-decision"]').trigger('click')
    await vi.waitFor(() => expect(requests.filter((request) => request.url?.includes('/triage'))).toHaveLength(1))
    await vi.waitFor(() => expect(requests.filter((request) => request.url === '/review/workbench/summary')).toHaveLength(1))
    await flushPromises()
    expect(wrapper.get('[data-testid="finding-panel"]').text()).toContain('已保存')
    expect(requests.filter((request) => request.url === '/review/workbench/summary')).toHaveLength(1)
    expect(requests.filter((request) => request.url === '/review/workbench/cases')).toHaveLength(1)

    await wrapper.get('[data-testid="finalize-review"]').trigger('click')
    expect(wrapper.get('[data-testid="finalize-review"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('目前有 0 個尚未處理的疑點')
    await wrapper.get('[data-confirm]').trigger('click')
    await vi.waitFor(() => expect(requests.filter((request) => request.url?.includes('/complete-review'))).toHaveLength(1))
    await vi.waitFor(() => expect(requests.filter((request) => request.url === '/review/workbench/summary')).toHaveLength(2))
    await flushPromises()
    expect(wrapper.text()).toContain('已完成審查')
    expect(requests.filter((request) => request.url === '/review/workbench/summary')).toHaveLength(2)
    expect(requests.filter((request) => request.url === '/review/workbench/cases')).toHaveLength(2)
    wrapper.unmount()
  })

  it('starts a received Review through preflight and a completed run before finalization', async () => {
    const requests: string[] = []
    const receivedDetail = {
      ...structuredClone(detailBase),
      review: {
        ...structuredClone(detailBase.review),
        review_status: 'RECEIVED',
        latest_validation_run_id: null,
      },
      runs: [],
      findings: [],
      risk_summary: null,
    }
    let detailDto = receivedDetail
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push(`${config.method} ${config.url}`)
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(detailDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') return response({ items: [queueItemDto], total: 1, limit: 20, offset: 0 }, config)
      if (config.method === 'post' && config.url === `/review/workbench/cases/${idsWithDetail.review}/start/preflight`) {
        return response({
          outcome: 'READY',
          completeness: {
            ready: true,
            review_status: 'READY_FOR_REVIEW',
            missing_item_count: 0,
            blocked_rule_codes: [],
            items: [],
          },
        }, config)
      }
      if (config.method === 'post' && config.url === `/review/workbench/cases/${idsWithDetail.review}/start`) {
        detailDto = {
          ...receivedDetail,
          review: {
            ...receivedDetail.review,
            review_status: 'REVIEW_REQUIRED',
            latest_validation_run_id: idsWithDetail.run,
          },
          runs: structuredClone(detailBase.runs),
          findings: [],
          risk_summary: null,
        }
        return response({
          outcome: 'COMPLETED',
          completeness: {
            ready: true,
            review_status: 'READY_FOR_REVIEW',
            missing_item_count: 0,
            blocked_rule_codes: [],
            items: [],
          },
          run: detailDto.runs[0],
          findings: [],
          risk_summary: null,
        }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="start-review"]').isVisible()).toBe(true))

    await wrapper.get('[data-testid="start-review"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="start-review"]').exists()).toBe(false))
    expect(requests.filter((request) => request.includes('/start'))).toEqual([
      `post /review/workbench/cases/${idsWithDetail.review}/start/preflight`,
      `post /review/workbench/cases/${idsWithDetail.review}/start`,
    ])
    expect(wrapper.get('[data-testid="finalize-review"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('renders an empty queue and a recoverable error without exposing transport details', async () => {
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.url === '/review/workbench/cases') return response({ items: [], total: 0, limit: 20, offset: 0 }, config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter
    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/review/dashboard')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('目前沒有符合條件的審查案件'))
    wrapper.unmount()

    http.defaults.adapter = vi.fn(async (config) => {
      throw new Error(`Transport detail must not render: ${config.url}`)
    }) as unknown as typeof originalAdapter
    const errorRouter = createAppRouter(createMemoryHistory())
    await errorRouter.push('/app/review/dashboard')
    const errorWrapper = mount(AppLayout, { global: { plugins: [errorRouter] } })
    await vi.waitFor(() => expect(errorWrapper.text()).toContain('審查服務目前無法完成此操作'))
    expect(errorWrapper.text()).not.toContain('Transport detail')
    errorWrapper.unmount()
  })

  it('keeps a confirmed issue unresolved and blocks completion before the server can reject it', async () => {
    const requests: string[] = []
    const confirmedDetail = structuredClone(detailBase)
    confirmedDetail.findings[0].status = 'CONFIRMED_ISSUE'
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push(`${config.method} ${config.url}`)
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        return response({ items: [queueItemDto], total: 1, limit: 20, offset: 0 }, config)
      }
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(confirmedDetail, config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('調整率需要覆核'))

    expect(wrapper.get('[data-testid="finding-panel"]').text()).toContain('已確認問題')
    expect(wrapper.get('[data-testid="finding-panel"]').text()).toContain('目前案件狀態或疑點狀態不允許再次判定')
    expect(wrapper.get('[data-testid="save-finding-decision"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="finalize-review"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('目前有 1 個尚未處理的疑點')
    expect(requests.some((request) => request.includes('/triage'))).toBe(false)
    expect(requests.some((request) => request.includes('/complete-review'))).toBe(false)
    wrapper.unmount()
  })

  it('fails closed for a pre-review case and maps a stale-state 409 to an actionable message', async () => {
    const blockedDetail = structuredClone(detailBase)
    blockedDetail.review.review_status = 'READY_FOR_REVIEW'
    blockedDetail.runs[0].run_status = 'RUNNING'
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') return response({ items: [queueItemDto], total: 1, limit: 20, offset: 0 }, config)
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(blockedDetail, config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('調整率需要覆核'))
    expect(wrapper.get('[data-testid="save-finding-decision"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="finalize-review"]').attributes('disabled')).toBeDefined()

    wrapper.unmount()
  })

  it('keeps report actions disabled before review completion when the report endpoint would return 409', async () => {
    const incompleteDetail = structuredClone(detailBase)
    incompleteDetail.review.review_status = 'REVIEW_REQUIRED'
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(incompleteDetail, config)
      if (config.method === 'get' && config.url === `/review/runs/${idsWithDetail.run}/report`) {
        throw { isAxiosError: true, response: { status: 409, data: { error: { code: 'REVIEW_REPORT_NOT_AVAILABLE' } } } }
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/result/${idsWithDetail.review}?runId=${idsWithDetail.run}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('審查結果'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('案件完成且最新檢核完成後'))

    for (const testId of ['generate-review-pdf', 'generate-review-xlsx', 'generate-review-docx', 'download-review-report']) {
      expect(wrapper.get(`[data-testid="${testId}"]`).attributes('disabled')).toBeDefined()
    }
    expect(wrapper.text()).not.toContain('REVIEW_REPORT_NOT_AVAILABLE')
    wrapper.unmount()
  })

  it.each([
    ['application/pdf', 'PDF 文件'],
    ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Excel 文件'],
    ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'Word 文件'],
    ['application/x-unrecognized-report', '其他檔案格式'],
  ])('renders a safe Chinese label instead of raw report MIME type (%s)', async (mimeType, expectedLabel) => {
    const completedDetail = structuredClone(detailBase)
    completedDetail.review.review_status = 'REVIEW_COMPLETED'
    completedDetail.report_document = {
      document_id: idsWithDetail.document,
      case_id: idsWithDetail.case,
      document_type: 'review-report',
      original_filename: 'review-risk-report.bin',
      mime_type: mimeType,
      checksum_sha256: 'report-checksum',
      file_size_bytes: 10,
      version_no: 1,
    }
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(completedDetail, config)
      if (config.method === 'get' && config.url === `/review/runs/${idsWithDetail.run}/report`) {
        return response({
          case: { case_no: completedDetail.case.case_no, case_title: completedDetail.case.case_title },
          run: {},
          review_status: 'REVIEW_COMPLETED',
          missing_item_count: 0,
          findings: [],
          risk_summary: {},
          case_decisions: [],
        }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/result/${idsWithDetail.review}?runId=${idsWithDetail.run}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('審查結果'))
    await vi.waitFor(() => expect(wrapper.get('.review-result__card--file').text()).toContain(expectedLabel))
    const fileCard = wrapper.get('.review-result__card--file')
    expect(fileCard.text()).not.toContain(mimeType)
    wrapper.unmount()
  })

  it('provides keyboard-safe narrow workbench drawers with focus restoration and backdrop close', async () => {
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(detailBase, config)
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}/documents/${idsWithDetail.document}/content`) return response(new Blob(['%PDF-1.7']), config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { attachTo: document.body, global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('調整率需要覆核'))

    const contextTrigger = wrapper.get('[data-testid="open-review-context"]')
    expect(contextTrigger.attributes('aria-controls')).toBe('review-context-drawer')
    await contextTrigger.trigger('click')
    await flushPromises()
    const contextDrawer = wrapper.get('#review-context-drawer')
    expect(contextDrawer.attributes('role')).toBe('dialog')
    expect(contextDrawer.attributes('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(contextDrawer.get('button[aria-label="關閉案件脈絡"]').element)
    const contextClose = contextDrawer.get('button[aria-label="關閉案件脈絡"]')
    const contextFinding = contextDrawer.get(`[data-testid="finding-select-${idsWithDetail.finding}"]`)
    contextClose.element.focus()
    await contextDrawer.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(contextFinding.element)
    contextFinding.element.focus()
    await contextDrawer.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(contextClose.element)
    await contextDrawer.trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(wrapper.get('#review-context-drawer').attributes('role')).toBeUndefined()
    expect(document.activeElement).toBe(contextTrigger.element)

    const findingTrigger = wrapper.get('[data-testid="open-review-finding"]')
    await findingTrigger.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="review-drawer-backdrop"]').attributes('aria-label')).toBe('關閉疑點內容')
    await wrapper.get('[data-testid="review-drawer-backdrop"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('#review-finding-drawer').attributes('role')).toBeUndefined()
    expect(document.activeElement).toBe(findingTrigger.element)
    wrapper.unmount()
  })
})

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}

function requestBody(data: unknown): Record<string, any> {
  if (typeof data === 'string') return JSON.parse(data) as Record<string, any>
  return (data ?? {}) as Record<string, any>
}
