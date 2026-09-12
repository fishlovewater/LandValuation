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
  case_source: 'PLATFORM',
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
  documentGroup: '89898989-8989-4989-8989-898989898989',
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
  case_source: 'PLATFORM',
  submission_id: null,
  submission_no: null,
  submitted_at: '2026-09-07T01:00:00Z',
  input_fingerprint: null,
  documents: [
    {
      document_id: idsWithDetail.document,
      document_group_id: idsWithDetail.documentGroup,
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
    expect(router.currentRoute.value.query.page).toBeUndefined()
    expect(requests.filter((request) => request.url === '/review/workbench/cases')).toHaveLength(2)
    expect(requests.filter((request) => request.url === '/review/workbench/cases').at(-1)?.params).toMatchObject({
      status_group: 'in_progress',
      limit: 20,
      offset: 0,
    })

    await wrapper.get(`[data-testid="review-case-row-${ids.review}"]`).trigger('click')
    await vi.waitFor(
      () => expect(router.currentRoute.value.name).toBe('review-workbench'),
      { timeout: 5_000 },
    )
    expect(router.currentRoute.value.params.reviewId).toBe(ids.review)

    await wrapper.get('[data-testid="review-back-to-queue"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('review-dashboard'))
    expect(router.currentRoute.value.query).toMatchObject({
      sortBy: 'caseNo',
      sortDirection: 'asc',
      pageSize: '20',
      statusGroup: 'in_progress',
    })
    expect(router.currentRoute.value.query.page).toBeUndefined()
    wrapper.unmount()
  }, 10_000)

  it('can reset all review filters, KPI scope, sorting, and pagination to show the full queue', async () => {
    const queueRequests: unknown[] = []
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === '/review/workbench/summary') {
        return response(summaryDto, config)
      }
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        queueRequests.push(config.params)
        return response({ items: [queueItemDto], total: 6, limit: 20, offset: 0 }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push('/app/review/dashboard?status=REVIEW_REQUIRED&riskLevel=HIGH&statusGroup=in_progress&sortBy=caseNo&sortDirection=asc&page=3&pageSize=20')
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('NB-2026-0008'))

    expect(wrapper.get('select[name="status"]').find('option[value=""]').text()).toBe('全部狀態')
    expect(wrapper.get('select[name="riskLevel"]').find('option[value=""]').text()).toBe('全部風險')
    expect(wrapper.get('[data-testid="reset-review-queue"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="reset-review-queue"]').trigger('click')
    await vi.waitFor(() => expect(queueRequests).toHaveLength(2))

    expect(router.currentRoute.value.query).toEqual({})
    expect(queueRequests.at(-1)).toMatchObject({
      q: undefined,
      status: undefined,
      risk_level: undefined,
      status_group: undefined,
      limit: 20,
      offset: 0,
    })
    expect(wrapper.get('select[name="status"]').element.value).toBe('')
    expect(wrapper.get('select[name="riskLevel"]').element.value).toBe('')
    expect(wrapper.get('[data-testid="reset-review-queue"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('merges partial queue queries and ignores an older queue response after a newer refresh', async () => {
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

    await wrapper.get('[data-testid="review-sort"]').setValue('name:asc')
    await vi.waitFor(() => expect(router.currentRoute.value.query.sortBy).toBe('name'))
    await vi.waitFor(() => expect(pendingQueueResponses).toHaveLength(1))
    expect(router.currentRoute.value.query).toMatchObject({
      status: 'REVIEW_REQUIRED',
      riskLevel: 'HIGH',
      statusGroup: 'in_progress',
      sortBy: 'name',
      sortDirection: 'asc',
      pageSize: '20',
    })
    expect(pendingQueueResponses[0].config.params).toMatchObject({
      status: 'REVIEW_REQUIRED',
      risk_level: 'HIGH',
      status_group: 'in_progress',
      sort_by: 'case_title',
      sort_direction: 'asc',
      limit: 20,
      offset: 0,
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
    detailDto.submission_id = 'abababab-abab-4bab-8bab-abababababab'
    detailDto.submission_no = 3
    detailDto.input_fingerprint = 'c'.repeat(64)
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
          reason: '依據報告與檢核規則結果確認。',
        })
        detailDto = {
          ...detailDto,
          findings: detailDto.findings.map((finding) => ({ ...finding, status: 'DISMISSED_FALSE_POSITIVE' })),
          decisions: [{
            decision_id: idsWithDetail.decision,
            review_id: idsWithDetail.review,
            finding_id: idsWithDetail.finding,
            decision: 'DISMISSED_FALSE_POSITIVE',
            reason: '依據報告與檢核規則結果確認。',
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

    const progress = wrapper.get('[data-testid="review-progress"]')
    expect(progress.text()).toContain('接收送審')
    expect(progress.text()).toContain('資料確認')
    expect(progress.get('[data-workflow-step="triage"]').attributes('aria-current')).toBe('step')
    expect(wrapper.get('[data-testid="review-source-strip"]').text()).toContain('平台送審')
    expect(wrapper.get('[data-testid="review-input-provenance"]').text()).toContain('第 3 次送審')
    expect(wrapper.get('[data-testid="review-input-provenance"]').text()).toContain('審查輸入已凍結')
    expect(wrapper.get('[data-testid="review-input-provenance"]').attributes('title')).toContain('c'.repeat(64))
    await wrapper.get('[data-testid="open-review-context"]').trigger('click')
    await flushPromises()
    const provenance = wrapper.get('[data-testid="review-input-context"]')
    expect(provenance.text()).toContain('審查依據版本')
    expect(provenance.text()).toContain('平台送審')
    expect(provenance.text()).toContain('第 3 次送審')
    expect(provenance.text()).toContain('c'.repeat(64))
    await wrapper.get('#review-context-drawer button[aria-label="關閉案件資料"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="report-value"]').text()).toContain('0.10')
    expect(wrapper.get('[data-testid="system-value"]').text()).toContain('0.08')
    expect(wrapper.get('[data-testid="ai-explanation"]').text()).toContain('系統發現')
    expect(wrapper.get('[data-testid="review-action-bar"]').text()).toContain('疑點已處理 0 / 1')
    await wrapper.get('#finding-decision').setValue('DISMISSED_FALSE_POSITIVE')
    await wrapper.get('[data-testid="save-finding-decision"]').trigger('click')
    expect(wrapper.text()).toContain('請填寫審查理由')
    expect(requests.filter((request) => request.url?.includes('/triage'))).toHaveLength(0)

    await wrapper.get('[data-testid="finding-reason"]').setValue('依據報告與檢核規則結果確認。')
    await wrapper.get('[data-testid="save-finding-decision"]').trigger('click')
    await vi.waitFor(() => expect(requests.filter((request) => request.url?.includes('/triage'))).toHaveLength(1))
    await vi.waitFor(() => expect(requests.filter((request) => request.url === '/review/workbench/summary')).toHaveLength(1))
    await flushPromises()
    expect(wrapper.get('[data-testid="finding-panel"]').text()).toContain('已儲存')
    expect(wrapper.get('[data-testid="review-action-bar"]').text()).toContain('疑點已處理 1 / 1')
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

  it('advances to the next open finding after a triage refresh and keeps the URL selection in sync', async () => {
    const nextFindingId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeef'
    let detailDto = structuredClone(detailBase)
    detailDto.findings.push({
      ...structuredClone(detailBase.findings[0]),
      finding_id: nextFindingId,
      finding_code: 'EXPERT_GRADE',
      title: '級距需要覆核',
      field_path: 'comparison.expert_grade',
      reported_text: '報告記載 B',
      reported_value: 'B',
      reported_adjustment_rate: null,
      system_adjustment_rate: null,
      reported_grade: 'B',
      system_grade: 'A',
      comparison_result: { system_value: 'A' },
    })

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        return response({ items: [queueItemDto], total: 1, limit: 20, offset: 0 }, config)
      }
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(detailDto, config)
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}/documents/${idsWithDetail.document}/content`) {
        return response(new Blob(['%PDF-1.7 evidence']), config)
      }
      if (config.method === 'post' && config.url === `/review/findings/${idsWithDetail.finding}/triage`) {
        detailDto = {
          ...detailDto,
          findings: detailDto.findings.map((finding) => finding.finding_id === idsWithDetail.finding
            ? { ...finding, status: 'CONFIRMED_ISSUE' }
            : finding),
          decisions: [{
            decision_id: idsWithDetail.decision,
            review_id: idsWithDetail.review,
            finding_id: idsWithDetail.finding,
            decision: 'CONFIRMED_ISSUE',
            reason: '第一筆確認需要補正。',
            decided_by_user_id: reviewer.id,
            decided_at: '2026-09-07T01:03:00Z',
            request_id: null,
            before_value: null,
            after_value: null,
          }],
        }
        return response(detailDto.decisions[0], config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="finding-panel"]').text()).toContain('調整率需要覆核'))

    await wrapper.get('[data-testid="finding-reason"]').setValue('第一筆確認需要補正。')
    await wrapper.get('[data-testid="save-finding-decision"]').trigger('click')

    await vi.waitFor(() => expect(router.currentRoute.value.query.finding).toBe(nextFindingId))
    await vi.waitFor(() => expect(wrapper.get('[data-testid="finding-panel"]').text()).toContain('級距需要覆核'))
    expect(wrapper.get('#finding-decision').attributes('disabled')).toBeUndefined()
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
      if (config.method === 'post' && config.url === `/review/cases/${idsWithDetail.review}/complete-review`) {
        expect(requestBody(config.data)).toEqual({ reason: '依審查工作台確認結果完成審查。' })
        detailDto = {
          ...detailDto,
          review: { ...detailDto.review, review_status: 'REVIEW_COMPLETED' },
        }
        return response({ review_id: idsWithDetail.review, status: 'REVIEW_COMPLETED' }, config, 201)
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
    await wrapper.get('[data-testid="finalize-review"]').trigger('click')
    await wrapper.get('[data-confirm]').trigger('click')
    await vi.waitFor(() => expect(requests).toContain(`post /review/cases/${idsWithDetail.review}/complete-review`))
    await vi.waitFor(() => expect(wrapper.text()).toContain('已完成審查'))
    wrapper.unmount()
  })

  it('turns completeness gaps into a formal supplement request and renders backend version diffs', async () => {
    const missingItemId = '19191919-1919-4191-8191-191919191919'
    const documentGroupId = '20202020-2020-4202-8202-202020202020'
    const detailDto: any = structuredClone(detailBase)
    detailDto.review.review_status = 'PENDING_MATERIALS'
    detailDto.review.missing_item_count = 1
    detailDto.findings = []
    detailDto.missing_items = [{
      missing_item_id: missingItemId,
      review_id: idsWithDetail.review,
      item_code: 'LAND_REGISTER_REQUIRED',
      item_name: '土地登記謄本',
      document_type: 'land-register',
      severity: 'ERROR',
      status: 'OPEN',
      field_path: 'documents.land_register',
      reason: '正式審查缺少必要土地登記資料。',
      affected_rule_codes: ['COMPLETENESS-LAND-REGISTER'],
      due_at: null,
      notified_at: null,
      notification_status: null,
      created_at: '2026-09-07T01:01:00Z',
    }]
    detailDto.version_diffs = [{
      document_group_id: documentGroupId,
      field_code: 'ADJUSTMENT_RATE',
      field_path: 'comparison.adjustment_rate',
      previous: {
        document_id: idsWithDetail.document,
        document_group_id: documentGroupId,
        document_version: 1,
        field_code: 'ADJUSTMENT_RATE',
        field_path: 'comparison.adjustment_rate',
        normalized_value: '-12',
        raw_text: '調整率 -12%',
        page_number: 3,
      },
      current: {
        document_id: '21212121-2121-4212-8212-212121212121',
        document_group_id: documentGroupId,
        document_version: 2,
        field_code: 'ADJUSTMENT_RATE',
        field_path: 'comparison.adjustment_rate',
        normalized_value: '-5',
        raw_text: '調整率 -5%',
        page_number: 3,
      },
    }]
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []

    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) {
        return response(detailDto, config)
      }
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response({ ...summaryDto, missing_item_count: 1 }, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        return response({ items: [{ ...queueItemDto, missing_item_count: 1 }], total: 1, limit: 20, offset: 0 }, config)
      }
      if (config.method === 'post' && config.url === `/review/cases/${idsWithDetail.review}/supplement-request`) {
        const body = requestBody(config.data)
        expect(new Date(String(body.due_at)).getTime()).toBeGreaterThan(Date.now())
        detailDto.missing_items = detailDto.missing_items.map((item: any) => ({
          ...item,
          status: 'OPEN',
          due_at: body.due_at,
          notification_status: 'PENDING',
        }))
        return response(detailDto.missing_items, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="review-missing-items"]').text()).toContain('土地登記謄本'))

    const diffPanel = wrapper.get('[data-testid="review-version-diffs"]')
    expect(diffPanel.text()).toContain('補正前後欄位差異')
    expect(diffPanel.text()).toContain('-12')
    expect(diffPanel.text()).toContain('-5')

    expect(wrapper.get('[data-testid="finalize-review"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="request-supplement"]').trigger('click')
    expect(wrapper.get('[data-testid="supplement-request-form"]').text()).toContain('土地登記謄本')
    await wrapper.get('[data-testid="supplement-request-form"]').trigger('submit')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="review-missing-items"]').text()).toContain('已要求補件'))

    expect(requests.filter((request) => request.url?.endsWith('/supplement-request'))).toHaveLength(1)
    expect(wrapper.get('[data-testid="finalize-review"]').attributes('disabled')).toBeDefined()
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

  it('creates and sends a correction request, then exposes the waiting-for-resubmission state', async () => {
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    let detailDto = structuredClone(detailBase)
    detailDto.findings[0].status = 'CONFIRMED_ISSUE'
    const correctionId = '33333333-3333-4333-8333-333333333333'

    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) {
        return response(detailDto, config)
      }
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        return response({ items: [queueItemDto], total: 1, limit: 20, offset: 0 }, config)
      }
      if (config.method === 'post' && config.url === `/review/cases/${idsWithDetail.review}/correction-requests`) {
        const body = requestBody(config.data)
        expect(body.message).toBe('請修正調整率並重新送審。')
        expect(new Date(String(body.due_at)).getTime()).toBeGreaterThan(Date.now())
        return response({
          correction_request_id: correctionId,
          review_id: idsWithDetail.review,
          request_no: 1,
          based_on_validation_run_id: idsWithDetail.run,
          status: 'DRAFT',
          due_at: body.due_at,
          message: body.message,
          base_document_id: idsWithDetail.document,
          base_document_version: 1,
          response_document_id: null,
          response_document_version: null,
          sent_at: null,
          resubmitted_by_user_id: null,
          resubmitted_at: null,
          rechecked_at: null,
          items: [],
        }, config, 201)
      }
      if (config.method === 'post' && config.url === `/review/correction-requests/${correctionId}/send`) {
        const sent = {
          correction_request_id: correctionId,
          review_id: idsWithDetail.review,
          request_no: 1,
          based_on_validation_run_id: idsWithDetail.run,
          status: 'SENT',
          due_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
          message: '請修正調整率並重新送審。',
          base_document_id: idsWithDetail.document,
          base_document_version: 1,
          response_document_id: null,
          response_document_version: null,
          sent_at: new Date().toISOString(),
          resubmitted_by_user_id: null,
          resubmitted_at: null,
          rechecked_at: null,
          items: [{
            correction_request_item_id: '44444444-4444-4444-8444-444444444444',
            finding_id: idsWithDetail.finding,
            finding_code: 'ADJUSTMENT_RATE',
            finding_type: 'RULE',
            severity: 'ERROR',
            document_id: idsWithDetail.document,
            document_version: 1,
            page_number: 3,
            reported_text: '報告記載 10%',
            reported_value: '0.10',
            legal_basis_snapshot: [],
            source_evidence_snapshot: [],
            issue_summary: '調整率需要覆核',
            requested_correction: '請修正調整率並附上依據。',
            recheck_outcome: 'NOT_EVALUATED',
            resulting_finding_id: null,
            rechecked_at: null,
          }],
        }
        detailDto = {
          ...detailDto,
          review: { ...detailDto.review, review_status: 'RETURNED_FOR_REVISION' },
          correction_requests: [sent],
        }
        return response(sent, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="request-correction"]').attributes('disabled')).toBeUndefined())

    await wrapper.get('[data-testid="request-correction"]').trigger('click')
    await wrapper.get('#review-correction-message').setValue('請修正調整率並重新送審。')
    await wrapper.get('[data-testid="correction-request-form"]').trigger('submit')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="correction-status-panel"]').text()).toContain('已送出'))

    expect(wrapper.get('[data-testid="awaiting-correction"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="correction-status-panel"]').text()).toContain('請修正調整率並附上依據')
    expect(requests.filter((request) => request.url?.includes('/correction-requests'))
      .map((request) => `${request.method} ${request.url}`))
      .toEqual([
        `post /review/cases/${idsWithDetail.review}/correction-requests`,
        `post /review/correction-requests/${correctionId}/send`,
      ])
    wrapper.unmount()
  })

  it('keeps an external correction as a draft until the reviewer confirms the manual notification', async () => {
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    let detailDto: any = structuredClone(detailBase)
    detailDto.case_source = 'EXTERNAL'
    detailDto.findings[0].status = 'CONFIRMED_ISSUE'
    const correctionId = '34343434-3434-4434-8434-343434343434'

    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) {
        return response(detailDto, config)
      }
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') {
        return response({ items: [{ ...queueItemDto, case_source: 'EXTERNAL' }], total: 1, limit: 20, offset: 0 }, config)
      }
      if (config.method === 'post' && config.url === `/review/cases/${idsWithDetail.review}/correction-requests`) {
        const body = requestBody(config.data)
        const draft = {
          correction_request_id: correctionId,
          review_id: idsWithDetail.review,
          request_no: 1,
          based_on_validation_run_id: idsWithDetail.run,
          status: 'DRAFT',
          due_at: body.due_at,
          message: body.message,
          base_document_id: idsWithDetail.document,
          base_document_version: 1,
          response_document_id: null,
          response_document_version: null,
          sent_at: null,
          resubmitted_by_user_id: null,
          resubmitted_at: null,
          rechecked_at: null,
          items: [],
        }
        detailDto = { ...detailDto, correction_requests: [draft] }
        return response(draft, config, 201)
      }
      if (config.method === 'post' && config.url === `/review/correction-requests/${correctionId}/send`) {
        const sent = {
          ...detailDto.correction_requests[0],
          status: 'SENT',
          sent_at: new Date().toISOString(),
        }
        detailDto = {
          ...detailDto,
          review: { ...detailDto.review, review_status: 'RETURNED_FOR_REVISION' },
          correction_requests: [sent],
        }
        return response(sent, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="review-source-strip"]').text()).toContain('外部案件'))

    const progress = wrapper.get('[data-testid="review-progress"]')
    expect(progress.text()).toContain('建立案件')
    expect(progress.text()).toContain('文件匯入')
    expect(progress.text()).toContain('欄位確認')
    expect(progress.get('[data-workflow-step="triage"]').attributes('aria-current')).toBe('step')

    await wrapper.get('[data-testid="request-correction"]').trigger('click')
    expect(wrapper.get('#review-correction-request').text()).toContain('既有外部管道')
    await wrapper.get('#review-correction-message').setValue('請外部廠商修正調整率並回傳新版文件。')
    await wrapper.get('[data-testid="correction-request-form"]').trigger('submit')

    await vi.waitFor(() => expect(wrapper.get('[data-testid="send-correction"]').text()).toContain('確認已對外通知'))
    expect(requests.filter((request) => request.url === `/review/correction-requests/${correctionId}/send`)).toHaveLength(0)
    expect(wrapper.get('[data-testid="review-progress"]').get('[data-workflow-step="recheck"]').attributes('aria-current')).toBe('step')

    await wrapper.get('[data-testid="send-correction"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="awaiting-correction"]').text()).toContain('等待外部回件'))
    expect(requests.filter((request) => request.url === `/review/correction-requests/${correctionId}/send`)).toHaveLength(1)
    wrapper.unmount()
  })

  it('keeps an external corrected report in the same lineage and registers it only after OCR fields are resolved', async () => {
    const correctionId = '34343434-3434-4434-8434-343434343434'
    const revisedDocumentId = '45454545-4545-4454-8454-454545454545'
    const extractionId = '56565656-5656-4565-8565-565656565656'
    const fieldId = '67676767-6767-4676-8676-676767676767'
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    let detailDto: any = structuredClone(detailBase)
    detailDto.case_source = 'EXTERNAL'
    detailDto.review.review_status = 'RETURNED_FOR_REVISION'
    detailDto.runs[0] = {
      ...detailDto.runs[0],
      external_input_snapshot_id: '89898989-8989-4898-8989-898989898989',
      external_input_snapshot_no: 1,
      external_input_snapshot_created_at: '2026-09-12T07:05:00Z',
      external_input_fingerprint: 'b'.repeat(64),
    }
    detailDto.correction_requests = [{
      correction_request_id: correctionId,
      review_id: idsWithDetail.review,
      request_no: 1,
      based_on_validation_run_id: idsWithDetail.run,
      status: 'SENT',
      due_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
      message: '請修正調整率並回傳新版估價報告。',
      base_document_id: idsWithDetail.document,
      base_document_version: 1,
      response_document_id: null,
      response_document_version: null,
      sent_at: new Date().toISOString(),
      resubmitted_by_user_id: null,
      resubmitted_at: null,
      rechecked_at: null,
      items: [],
    }]

    const revisedDocument = {
      document_id: revisedDocumentId,
      document_group_id: idsWithDetail.documentGroup,
      document_type: 'original',
      original_filename: 'external-appraisal-revised.pdf',
      mime_type: 'application/pdf',
      version_no: 2,
      is_active: true,
      uploaded_at: '2026-09-12T07:15:00Z',
    }
    const pendingCandidate = {
      extracted_field_id: fieldId,
      extraction_id: extractionId,
      document_id: revisedDocumentId,
      form_code: 'F01',
      field_name: 'parcel_area',
      field_label: '宗地面積',
      field_guidance: '請核對來源文件所載面積。',
      extracted_value: '126.00',
      confidence: '0.94',
      source_page: 3,
      source_text: '宗地面積 126.00 平方公尺',
      analysis_provider: 'LOCAL_OCR',
      model_id: null,
      prompt_version: null,
      field_status: 'NEEDS_CONFIRMATION',
      confirmed_value: null,
      confirmed_by_user_id: null,
      confirmed_at: null,
      applied_form_instance_id: null,
      applied_at: null,
    }
    const extractionBase = {
      extraction_id: extractionId,
      case_id: idsWithDetail.case,
      document_id: revisedDocumentId,
      provider: 'local_pdf',
      extraction_status: 'COMPLETED',
      page_count: 6,
      extracted_text: '宗地面積 126.00 平方公尺',
      error_message: null,
      started_at: '2026-09-12T07:16:00Z',
      completed_at: '2026-09-12T07:16:02Z',
    }

    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) {
        return response(detailDto, config)
      }
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}/external-documents/${idsWithDetail.document}/extraction`) {
        return response({
          ...extractionBase,
          extraction_id: '78787878-7878-4787-8787-787878787878',
          document_id: idsWithDetail.document,
          extracted_text: '舊版報告',
          candidates: [],
        }, config)
      }
      if (config.method === 'post' && config.url === `/review/workbench/cases/${idsWithDetail.review}/external-documents`) {
        expect(config.data).toBeInstanceOf(FormData)
        const body = config.data as FormData
        expect(body.get('category')).toBe('original')
        expect(body.get('document_group_id')).toBe(idsWithDetail.documentGroup)
        detailDto = {
          ...detailDto,
          documents: [
            { ...detailDto.documents[0], is_active: false },
            revisedDocument,
          ],
        }
        return response(revisedDocument, config, 201)
      }
      if (config.method === 'post' && config.url === `/review/workbench/cases/${idsWithDetail.review}/external-documents/${revisedDocumentId}/extract`) {
        return response({ ...extractionBase, candidates: [pendingCandidate] }, config)
      }
      if (config.method === 'post' && config.url === `/review/workbench/cases/${idsWithDetail.review}/external-documents/${revisedDocumentId}/extraction/confirm`) {
        expect(requestBody(config.data).confirmations).toEqual([{
          extracted_field_id: fieldId,
          decision: 'CONFIRM',
        }])
        return response({
          ...extractionBase,
          candidates: [{
            ...pendingCandidate,
            field_status: 'APPLIED',
            confirmed_value: '126.00',
            confirmed_by_user_id: reviewer.id,
            confirmed_at: '2026-09-12T07:17:00Z',
            applied_at: '2026-09-12T07:17:00Z',
          }],
        }, config)
      }
      if (config.method === 'post' && config.url === `/review/correction-requests/${correctionId}/resubmissions`) {
        expect(requestBody(config.data)).toEqual({
          document_id: revisedDocumentId,
          document_version: 2,
        })
        const resubmitted = {
          ...detailDto.correction_requests[0],
          status: 'RESUBMITTED',
          response_document_id: revisedDocumentId,
          response_document_version: 2,
          resubmitted_by_user_id: reviewer.id,
          resubmitted_at: '2026-09-12T07:18:00Z',
        }
        detailDto = { ...detailDto, correction_requests: [resubmitted] }
        return response(resubmitted, config, 201)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="external-correction-return"]').text()).toContain('等待回件'))
    expect(wrapper.get('[data-testid="review-input-provenance"]').text()).toContain('v1')
    expect(wrapper.get('[data-testid="review-input-provenance"]').text()).toContain('審查輸入已凍結')

    const correctionFileInput = wrapper.get('[data-testid="external-correction-file"]')
    const revisedFile = new File(['%PDF-1.7 revised appraisal'], 'external-appraisal-revised.pdf', { type: 'application/pdf' })
    Object.defineProperty(correctionFileInput.element, 'files', { value: [revisedFile], configurable: true })
    await correctionFileInput.trigger('change')
    await wrapper.get('[data-testid="upload-external-correction-version"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('第 2 版'))
    expect(wrapper.get('[data-testid="review-input-provenance"]').text()).toContain('v1')
    expect(wrapper.get(`[data-testid="external-document-${idsWithDetail.document}"]`).text()).toContain('歷史版本')
    expect(wrapper.get(`[data-testid="external-document-${revisedDocumentId}"]`).text()).toContain('目前版本')

    await wrapper.get('[data-testid="start-external-extraction"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('宗地面積'))
    expect(wrapper.get('[data-testid="register-external-resubmission"]').attributes('disabled')).toBeDefined()

    await wrapper.get(`[data-testid="confirm-external-field-${fieldId}"]`).trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="register-external-resubmission"]').attributes('disabled')).toBeUndefined())
    await wrapper.get('[data-testid="register-external-resubmission"]').trigger('click')

    await vi.waitFor(() => expect(wrapper.get('[data-testid="external-correction-return"]').text()).toContain('已登記回件'))
    expect(wrapper.get('[data-testid="recheck-correction"]').attributes('disabled')).toBeUndefined()
    expect(requests.some((request) => request.url === `/review/correction-requests/${correctionId}/resubmissions`)).toBe(true)
    wrapper.unmount()
  })

  it('rechecks a resubmitted correction instead of offering a second correction request', async () => {
    const correctionId = '55555555-5555-4555-8555-555555555555'
    let recheckCount = 0
    let detailDto = structuredClone(detailBase)
    detailDto.review.review_status = 'RETURNED_FOR_REVISION'
    detailDto.findings[0].status = 'CONFIRMED_ISSUE'
    const resubmitted = {
      correction_request_id: correctionId,
      review_id: idsWithDetail.review,
      request_no: 1,
      based_on_validation_run_id: idsWithDetail.run,
      status: 'RESUBMITTED',
      due_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
      message: '請修正後重送。',
      base_document_id: idsWithDetail.document,
      base_document_version: 1,
      response_document_id: '66666666-6666-4666-8666-666666666666',
      response_document_version: 2,
      sent_at: new Date().toISOString(),
      resubmitted_by_user_id: '77777777-7777-4777-8777-777777777777',
      resubmitted_at: new Date().toISOString(),
      rechecked_at: null,
      items: [],
    }
    detailDto.correction_requests = [resubmitted]

    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'get' && config.url === `/review/workbench/cases/${idsWithDetail.review}`) return response(detailDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/summary') return response(summaryDto, config)
      if (config.method === 'get' && config.url === '/review/workbench/cases') return response({ items: [queueItemDto], total: 1, limit: 20, offset: 0 }, config)
      if (config.method === 'post' && config.url === `/review/correction-requests/${correctionId}/recheck`) {
        recheckCount += 1
        const rechecked = { ...resubmitted, status: 'RECHECKED', rechecked_at: new Date().toISOString() }
        detailDto = {
          ...detailDto,
          review: { ...detailDto.review, review_status: 'REVIEW_REQUIRED' },
          correction_requests: [rechecked],
        }
        return response(rechecked, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/review/workbench/${idsWithDetail.review}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="recheck-correction"]').attributes('disabled')).toBeUndefined())
    expect(wrapper.find('[data-testid="request-correction"]').exists()).toBe(false)

    await wrapper.get('[data-testid="recheck-correction"]').trigger('click')
    await vi.waitFor(() => expect(recheckCount).toBe(1))
    await vi.waitFor(() => expect(wrapper.get('[data-testid="correction-status-panel"]').text()).toContain('已重新檢核'))
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
          input_provenance: {
            source: 'EXTERNAL',
            version_no: 2,
            frozen_at: '2026-09-12T07:05:00Z',
            fingerprint: 'b'.repeat(64),
            schema_version: 'external-review-input-v1',
            submission_id: null,
            external_input_snapshot_id: '89898989-8989-4898-8989-898989898989',
            documents: [],
          },
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
    expect(wrapper.get('[data-testid="review-report-provenance"]').text()).toContain('外部案件 v2')
    expect(wrapper.get('[data-testid="review-report-provenance"]').text()).toContain('b'.repeat(64))
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
    expect(document.activeElement).toBe(contextDrawer.get('button[aria-label="關閉案件資料"]').element)
    const contextClose = contextDrawer.get('button[aria-label="關閉案件資料"]')
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
