import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import AppLayout from '../../src/layouts/AppLayout.vue'
import { http, tokenService } from '../../src/api/http'
import { createAppRouter } from '../../src/router'
import type { AuthUser } from '../../src/modules/auth/auth.types'
import { useAuthStore } from '../../src/stores/auth.store'
import AnswerMessage from '../../src/modules/assistant/components/AnswerMessage.vue'
import { mapAssistantQuestion } from '../../src/modules/assistant/assistant.mappers'

const ids = {
  case: '11111111-1111-4111-8111-111111111111',
  form: '22222222-2222-4222-8222-222222222222',
  session: '33333333-3333-4333-8333-333333333333',
  secondSession: '88888888-8888-4888-8888-888888888888',
  document: '44444444-4444-4444-8444-444444444444',
  chunk: '55555555-5555-4555-8555-555555555555',
  generalConversation: '99999999-9999-4999-8999-999999999999',
  caseConversation: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  reviewConversation: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  review: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
}

const assistantUser: AuthUser = {
  id: '66666666-6666-4666-8666-666666666666',
  username: 'assistant.appraiser',
  email: 'assistant.appraiser@example.test',
  displayName: '示範估價人員',
  roles: ['REVIEWER'],
  permissions: [
    'assistant.use',
    'case.read',
    'knowledge.read',
    'valuation.read',
    'valuation.update',
  ],
}

const sessionDto = (sessionId = ids.session) => ({
  assistant_session_id: sessionId,
  case_id: ids.case,
  user_id: assistantUser.id,
  form_instance_id: ids.form,
  current_step: 'READY_TO_SUBMIT',
  selected_form_type: 'F03',
  missing_fields: [],
  missing_documents: [],
  last_tool_name: null,
  last_tool_status: null,
  provider: 'MOCK',
  model_id: 'mock-f03-v1',
  prompt_version: 'v1',
  session_status: 'ACTIVE',
  created_at: '2026-09-07T02:00:00Z',
  updated_at: '2026-09-07T02:00:00Z',
})

const citationDto = (citationId = ids.chunk) => ({
  citation_id: citationId,
  document_id: ids.document,
  document_title: '回傳來源文件',
  document_code: 'DOC-001',
  version_no: 2,
  effective_from: '2026-01-01',
  effective_to: null,
  page_start: 14,
  page_end: 15,
  section_title: '適用條件',
  article_no: '第 3 條',
  quoted_text: '本條文內容由後端回傳。',
  supporting_quote: null,
  supported_claim: '本案應以正式來源核對適用條件。',
})

const supportedQuestionDto = (sessionId = ids.session) => ({
  assistant_session_id: sessionId,
  answer_status: 'SUPPORTED',
  answer: '本案應以正式來源核對適用條件。',
  answer_route: 'KNOWLEDGE',
  generation_mode: 'MOCK',
  next_action: 'REVIEW_SOURCE',
  clarification_question: null,
  claims: [{
    text: '本案應以正式來源核對適用條件。',
    citation_ids: [ids.chunk],
  }],
  citations: [citationDto()],
  unreadable_sources: [],
})

const knowledgeConversationDto = (
  conversationId: string,
  context: {
    case_id?: string | null
    review_id?: string | null
    finding_id?: string | null
    workspace?: string | null
  } = {},
) => ({
  conversation_id: conversationId,
  case_id: context.case_id ?? null,
  review_id: context.review_id ?? null,
  finding_id: context.finding_id ?? null,
  workspace: context.workspace ?? null,
  title: context.case_id ? '案件對話' : '一般對話',
  provider: 'mock',
  model_id: 'mock-assistant-router-v1',
  status: 'ACTIVE',
  created_at: '2026-09-12T04:00:00Z',
  updated_at: '2026-09-12T04:00:00Z',
})

const caseConversationAnswerDto = () => ({
  answer_status: 'SUPPORTED',
  answer: '目前案件資料已依授權範圍讀取。',
  answer_route: 'CASE',
  generation_mode: 'STRUCTURED_CASE_DATA',
  next_action: 'CONTINUE_CONVERSATION',
  clarification_question: null,
  citations: [],
  unreadable_sources: [],
})

describe('cited assistant demo flow', () => {
  const originalAdapter = http.defaults.adapter

  beforeEach(() => {
    setActivePinia(createPinia())
    tokenService.clear()
    tokenService.set('assistant-test-token', 1800)
  })

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    tokenService.clear()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('sends a cited question DTO without case_id and opens the returned citation', async () => {
    useAuthStore().user = assistantUser
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({
        method: config.method,
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
      })
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') {
        return response(sessionDto(), config, 201)
      }
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) {
        return response(sessionDto(), config)
      }
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) {
        return response([], config)
      }
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) {
        return response(supportedQuestionDto(), config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { attachTo: document.body, global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    const assistantContext = wrapper.get('[data-testid="assistant-context"]')
    expect(assistantContext.text()).toContain('已連結目前案件')
    expect(assistantContext.text()).toContain('目前案件資料已載入')
    expect(assistantContext.text()).toContain('必要資料已齊，可進行後續估價作業')
    expect(assistantContext.text()).not.toContain('READY_TO_SUBMIT')
    expect(wrapper.find('[data-testid="assistant-mode-guide"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('案件模式')
    expect(wrapper.text()).not.toContain('知識模式')
    expect(wrapper.get('[data-testid="assistant-return-case"]').attributes('href')).toContain(`/app/valuation/cases/${ids.case}`)
    expect(wrapper.get('[data-testid="assistant-suggestion-0"]').text()).toContain('目前這筆案件')

    expect(requests.some((request) => request.method === 'post' && request.url === '/ai-assistant/sessions')).toBe(false)

    await wrapper.get('[data-testid="assistant-question"]').setValue('請說明目前狀態')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('本案應以正式來源核對適用條件'))

    expect(requests.at(-1)).toEqual({
      method: 'post',
      url: `/ai-assistant/sessions/${ids.session}/questions`,
      data: { question: '請說明目前狀態' },
    })
    expect(requests.at(-1)?.data).not.toHaveProperty('case_id')
    expect(wrapper.text()).toContain('AI 建議僅供輔助，最終由專業人員判斷。')

    await wrapper.get('[data-testid="assistant-citation-1"]').trigger('click')
    expect(wrapper.text()).toContain('回傳來源文件')
    expect(wrapper.text()).toContain('第 3 條')
    expect(wrapper.text()).toContain('第 14–15 頁')
    expect(wrapper.text()).toContain('適用條件')
    expect(wrapper.text()).toContain('本條文內容由後端回傳。')
    expect(wrapper.text()).not.toContain('localhost')
    wrapper.unmount()
  })

  it('shows only the fixed insufficiency copy when the response has no usable citation graph', async () => {
    useAuthStore().user = assistantUser
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') return response(sessionDto(), config, 201)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return response(sessionDto(), config)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) return response([], config)
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) {
        return response({
          ...supportedQuestionDto(),
          answer_status: 'EVIDENCE_ONLY',
          answer: '這段回答不可直接呈現。',
          claims: [],
          citations: [],
        }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))
    await wrapper.get('[data-testid="assistant-question"]').setValue('請確認來源')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="assistant-insufficient"]').exists()).toBe(true))

    expect(wrapper.text()).toContain('目前沒有足夠的可讀適用來源，無法支持這項回答。')
    expect(wrapper.text()).not.toContain('這段回答不可直接呈現。')
    expect(wrapper.find('[data-testid^="assistant-citation-"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('fails closed when any claim points at an unknown citation', async () => {
    useAuthStore().user = assistantUser
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') return response(sessionDto(), config, 201)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return response(sessionDto(), config)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) return response([], config)
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) {
        return response({
          ...supportedQuestionDto(),
          claims: [
            supportedQuestionDto().claims[0],
            { text: '這個主張沒有可用來源。', citation_ids: ['unknown-citation-id'] },
          ],
        }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))
    await wrapper.get('[data-testid="assistant-question"]').setValue('請確認主張')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="assistant-insufficient"]').exists()).toBe(true))

    expect(wrapper.text()).not.toContain('本案應以正式來源核對適用條件。')
    expect(wrapper.find('[data-testid^="assistant-citation-"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps chat and case questions available without knowledge.read while leaving RAG authorization to the backend route', async () => {
    useAuthStore().user = {
      ...assistantUser,
      permissions: ['assistant.use', 'valuation.read'],
    }
    const requests: string[] = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push(`${config.method} ${config.url}`)
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') return response(sessionDto(), config, 201)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return response(sessionDto(), config)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) return response([], config)
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) {
        return response({
          assistant_session_id: ids.session,
          answer_status: 'SUPPORTED',
          answer: '你好。一般對話不需要查詢知識庫。',
          answer_route: 'CHAT',
          generation_mode: 'CHAT',
          next_action: 'CONTINUE_CONVERSATION',
          clarification_question: null,
          claims: [],
          citations: [],
          unreadable_sources: [],
        }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    expect(wrapper.get('[data-testid="assistant-question"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="assistant-permission-required"]').exists()).toBe(false)
    await wrapper.get('[data-testid="assistant-question"]').setValue('你好')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('一般對話不需要查詢知識庫'))
    expect(requests.some((request) => request.endsWith('/questions'))).toBe(true)
    wrapper.unmount()
  })

  it('uses a persistent case conversation without creating a legacy assistant session', async () => {
    useAuthStore().user = assistantUser
    const requests: Array<{ method?: string; url?: string; data?: Record<string, unknown> }> = []
    const generalConversation = knowledgeConversationDto(ids.generalConversation)
    const caseConversation = knowledgeConversationDto(ids.caseConversation, {
      case_id: ids.case,
      workspace: 'valuation',
    })
    http.defaults.adapter = vi.fn(async (config) => {
      const data = config.data ? JSON.parse(String(config.data)) as Record<string, unknown> : undefined
      requests.push({ method: config.method, url: config.url, data })
      if (config.method === 'get' && config.url === '/knowledge/conversations') {
        return response([generalConversation, caseConversation], config)
      }
      if (config.method === 'get' && config.url === `/knowledge/conversations/${ids.caseConversation}/messages`) {
        return response([], config)
      }
      if (config.method === 'post' && config.url === `/knowledge/conversations/${ids.caseConversation}/messages`) {
        return response(caseConversationAnswerDto(), config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant?caseId=${ids.case}&workspace=valuation`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    expect(wrapper.text()).toContain('已連結目前案件')
    expect(requests.some((request) => request.url === '/ai-assistant/sessions')).toBe(false)
    expect(wrapper.find('[data-testid="assistant-workflow-actions"]').exists()).toBe(false)
    await wrapper.get('[data-testid="assistant-question"]').setValue('目前案件狀態如何？')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('目前案件資料已依授權範圍讀取。'))

    expect(requests.find((request) => request.url === `/knowledge/conversations/${ids.caseConversation}/messages` && request.method === 'post')).toMatchObject({
      data: {
        question: '目前案件狀態如何？',
        case_id: ids.case,
        review_id: null,
        finding_id: null,
        workspace: 'valuation',
      },
    })
    wrapper.unmount()
  })

  it('creates a new exact-context conversation instead of reusing another context for the same case', async () => {
    useAuthStore().user = assistantUser
    const requests: Array<{ method?: string; url?: string; data?: Record<string, unknown> }> = []
    const reviewConversation = knowledgeConversationDto(ids.reviewConversation, {
      case_id: ids.case,
      review_id: ids.review,
      workspace: 'review',
    })
    const createdConversation = knowledgeConversationDto(ids.caseConversation, {
      case_id: ids.case,
      workspace: 'valuation',
    })
    let created = false
    http.defaults.adapter = vi.fn(async (config) => {
      const data = config.data ? JSON.parse(String(config.data)) as Record<string, unknown> : undefined
      requests.push({ method: config.method, url: config.url, data })
      if (config.method === 'get' && config.url === '/knowledge/conversations') {
        return response(created ? [createdConversation, reviewConversation] : [reviewConversation], config)
      }
      if (config.method === 'post' && config.url === '/knowledge/conversations') {
        created = true
        return response(createdConversation, config, 201)
      }
      if (config.method === 'get' && config.url === `/knowledge/conversations/${ids.caseConversation}/messages`) {
        return response([], config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant?caseId=${ids.case}&workspace=valuation`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(router.currentRoute.value.query.conversationId).toBe(ids.caseConversation))

    const createRequests = requests.filter((request) => request.method === 'post' && request.url === '/knowledge/conversations')
    expect(createRequests).toHaveLength(1)
    expect(createRequests[0]?.data).toEqual({
      case_id: ids.case,
      review_id: null,
      finding_id: null,
      workspace: 'valuation',
    })
    expect(requests.some((request) => request.url === '/ai-assistant/sessions')).toBe(false)
    expect(wrapper.text()).toContain('已連結目前案件')
    wrapper.unmount()
  })

  it('renders routed chat answers without inventing citations while keeping RAG fail-closed', () => {
    const direct = mapAssistantQuestion({
      assistant_session_id: ids.session,
      answer_status: 'SUPPORTED',
      answer: '你好，可以直接輸入問題。',
      answer_route: 'CHAT',
      generation_mode: 'CHAT',
      next_action: 'CONTINUE_CONVERSATION',
      clarification_question: null,
      claims: [],
      citations: [],
      unreadable_sources: [],
    })
    expect(direct).toMatchObject({
      supported: true,
      answerRoute: 'CHAT',
      text: '你好，可以直接輸入問題。',
      citations: [],
    })
    const chatAnswer = mount(AnswerMessage, { props: { answer: direct } })
    expect(chatAnswer.find('[data-testid="assistant-case-source"]').exists()).toBe(false)
    chatAnswer.unmount()

    const caseAnswer = mapAssistantQuestion({
      assistant_session_id: ids.session,
      answer_status: 'SUPPORTED',
      answer: '案件目前狀態為估價作業中。',
      answer_route: 'CASE',
      generation_mode: 'STRUCTURED_CASE_DATA',
      next_action: 'REVIEW_CASE',
      clarification_question: null,
      claims: [],
      citations: [],
      unreadable_sources: [],
    })
    const caseMessage = mount(AnswerMessage, { props: { answer: caseAnswer } })
    expect(caseMessage.get('[data-testid="assistant-case-source"]').text()).toContain('目前案件中已授權的結構化資料')
    expect(caseMessage.find('[data-testid^="assistant-citation-"]').exists()).toBe(false)
    caseMessage.unmount()

    const uncitedKnowledge = mapAssistantQuestion({
      assistant_session_id: ids.session,
      answer_status: 'SUPPORTED',
      answer: '這段正式知識回答沒有來源，不應直接顯示。',
      answer_route: 'KNOWLEDGE',
      generation_mode: 'RAG',
      next_action: 'REVIEW_SOURCE',
      clarification_question: null,
      claims: [],
      citations: [],
      unreadable_sources: [],
    })
    expect(uncitedKnowledge.supported).toBe(false)
    expect(uncitedKnowledge.answerRoute).toBe('KNOWLEDGE')
    expect(uncitedKnowledge.text).toContain('目前沒有足夠的可讀適用來源')
  })

  it('clears submitting state on session change, ignores stale answers, and permits the new session', async () => {
    useAuthStore().user = assistantUser
    let resolveFirstQuestion: ((value: ReturnType<typeof response>) => void) | undefined
    let resolveSecondQuestion: ((value: ReturnType<typeof response>) => void) | undefined
    const requests: string[] = []
    http.defaults.adapter = vi.fn((config) => {
      requests.push(`${config.method} ${config.url}`)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return Promise.resolve(response(sessionDto(), config))
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.secondSession}`) return Promise.resolve(response(sessionDto(ids.secondSession), config))
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) {
        return new Promise((resolve) => { resolveFirstQuestion = resolve })
      }
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.secondSession}/questions`) {
        return new Promise((resolve) => { resolveSecondQuestion = resolve })
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    await wrapper.get('[data-testid="assistant-question"]').setValue('舊工作階段問題')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    expect(wrapper.get('[data-testid="assistant-submit"]').attributes('disabled')).toBeDefined()

    await router.push(`/app/assistant/sessions/${ids.secondSession}?caseId=${ids.case}&formId=${ids.form}`)
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    await wrapper.get('[data-testid="assistant-question"]').setValue('新工作階段問題')
    expect(wrapper.get('[data-testid="assistant-submit"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    expect(requests.filter((request) => request.endsWith('/questions'))).toHaveLength(2)

    resolveFirstQuestion?.(response({
      ...supportedQuestionDto(ids.session),
      answer: '舊工作階段不應顯示。',
    }, {} as never))
    await flushPromises()
    expect(wrapper.text()).not.toContain('舊工作階段不應顯示。')

    resolveSecondQuestion?.(response({
      ...supportedQuestionDto(ids.secondSession),
      answer: '新工作階段已回應。',
      claims: [{ text: '新工作階段已回應。', citation_ids: [ids.chunk] }],
    }, {} as never))
    await vi.waitFor(() => expect(wrapper.text()).toContain('新工作階段已回應。'))
    wrapper.unmount()
  })

  it('blocks duplicate cited submissions and exposes truthful drawer ARIA with focus restoration', async () => {
    useAuthStore().user = assistantUser
    let resolveQuestion: ((value: ReturnType<typeof response>) => void) | undefined
    http.defaults.adapter = vi.fn((config) => {
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') return Promise.resolve(response(sessionDto(), config, 201))
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return Promise.resolve(response(sessionDto(), config))
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) return Promise.resolve(response([], config))
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) {
        return new Promise((resolve) => { resolveQuestion = resolve })
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { attachTo: document.body, global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    const drawerTrigger = wrapper.get('[data-testid="assistant-open-drawer"]')
    expect(drawerTrigger.attributes('aria-controls')).toBe('assistant-drawer')
    expect(drawerTrigger.attributes('aria-expanded')).toBe('false')
    await drawerTrigger.trigger('click')
    await flushPromises()
    expect(drawerTrigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('#assistant-drawer').attributes('aria-hidden')).toBe('false')
    await wrapper.get('#assistant-drawer .lg-modal__close').trigger('click')
    await flushPromises()
    expect(drawerTrigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(drawerTrigger.element)

    await wrapper.get('[data-testid="assistant-question"]').setValue('重複測試')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    expect(resolveQuestion).toBeDefined()
    resolveQuestion?.(response(supportedQuestionDto(), {} as never))
    await flushPromises()
    wrapper.unmount()
  })

  it('exposes only update-authorized server workflow actions and renders safe backend summaries', async () => {
    useAuthStore().user = assistantUser
    const requests: Array<{ url?: string; data?: Record<string, unknown> }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      const data = config.data ? JSON.parse(String(config.data)) as Record<string, unknown> : undefined
      requests.push({ url: config.url, data })
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') return response(sessionDto(), config, 201)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return response(sessionDto(), config)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) return response([], config)
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) {
        const toolName = data?.run_calculation
          ? 'run_calculation'
          : data?.run_validation
            ? 'run_validation'
            : 'generate_report_pdf'
        return response({
          session: sessionDto(),
          reply: '後端回覆含有不應顯示的 storage/path metadata。',
          progress: {
            assistant_session_id: ids.session,
            current_step: 'READY_TO_SUBMIT',
            missing_fields: [],
            missing_documents: [],
            confirmed_candidate_count: 2,
            pending_candidate_count: 0,
            completed_items: 5,
            total_items: 5,
          },
          tools: [{
            tool_name: toolName,
            status: 'SUCCESS',
            result: {
              status: 'SUCCESS',
              result: '123.45',
              failed_count: 0,
              warning_count: 1,
              bucket_name: 'private-bucket',
              object_key: 'cases/secret/report.pdf',
              download_path: '/api/v1/secret/download',
            },
          }],
        }, config)
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    expect(wrapper.get('[data-testid="assistant-workflow-actions"]')).toBeTruthy()
    await wrapper.get('[data-testid="assistant-workflow-action-calculation"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="assistant-workflow-result"]').exists()).toBe(true))
    expect(requests.at(-1)).toMatchObject({
      url: `/ai-assistant/sessions/${ids.session}/messages`,
      data: { content: '執行正式計算', run_calculation: true, confirm_action: true },
    })
    expect(wrapper.text()).toContain('目前進度：必要資料已齊，可進行後續估價作業')
    expect(wrapper.text()).not.toContain('READY_TO_SUBMIT')
    expect(wrapper.text()).toContain('計算結果：123.45')
    expect(wrapper.text()).not.toContain('private-bucket')
    expect(wrapper.text()).not.toContain('cases/secret/report.pdf')
    expect(wrapper.text()).not.toContain('/api/v1/secret/download')

    await vi.waitFor(() => expect(wrapper.get('[data-testid="assistant-workflow-action-validation"]').attributes('disabled')).toBeUndefined())
    await wrapper.get('[data-testid="assistant-workflow-action-validation"]').trigger('click')
    await vi.waitFor(() => expect(requests.at(-1)?.data).toMatchObject({
      content: '執行製作前檢核',
      run_validation: true,
    }))
    expect(requests.at(-1)?.data).not.toHaveProperty('confirm_action')

    await vi.waitFor(() => expect(wrapper.get('[data-testid="assistant-workflow-action-report"]').attributes('disabled')).toBeUndefined())
    await wrapper.get('[data-testid="assistant-workflow-action-report"]').trigger('click')
    await vi.waitFor(() => expect(requests.at(-1)?.data).toMatchObject({
      content: '產生正式報告 PDF',
      generate_report_pdf: true,
      confirm_action: true,
    }))
    wrapper.unmount()
  })

  it('keeps cited questions usable but hides workflow actions without valuation.update', async () => {
    useAuthStore().user = { ...assistantUser, permissions: ['assistant.use', 'case.read', 'knowledge.read', 'valuation.read'] }
    const requests: string[] = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push(`${config.method} ${config.url}`)
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') return response(sessionDto(), config, 201)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return response(sessionDto(), config)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) return response([], config)
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) return response(supportedQuestionDto(), config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    expect(wrapper.find('[data-testid="assistant-workflow-actions"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="assistant-question"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="assistant-question"]').setValue('請說明來源')
    await wrapper.get('[data-testid="assistant-submit"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('本案應以正式來源核對適用條件'))
    expect(requests.some((request) => request.startsWith('post ') && request.endsWith('/messages'))).toBe(false)
    expect(requests.some((request) => request.endsWith('/questions'))).toBe(true)
    wrapper.unmount()
  })

  it('requires at least two trimmed characters in both full-page and drawer question controls', async () => {
    useAuthStore().user = assistantUser
    http.defaults.adapter = vi.fn(async (config) => {
      if (config.method === 'post' && config.url === '/ai-assistant/sessions') return response(sessionDto(), config, 201)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}`) return response(sessionDto(), config)
      if (config.method === 'get' && config.url === `/ai-assistant/sessions/${ids.session}/messages`) return response([], config)
      if (config.method === 'post' && config.url === `/ai-assistant/sessions/${ids.session}/questions`) return response(supportedQuestionDto(), config)
      throw new Error(`Unexpected request ${config.method} ${config.url}`)
    }) as unknown as typeof originalAdapter

    const router = createAppRouter(createMemoryHistory())
    await router.push(`/app/assistant/sessions/${ids.session}?caseId=${ids.case}&formId=${ids.form}`)
    const wrapper = mount(AppLayout, { attachTo: document.body, global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('請輸入問題'))

    const question = wrapper.get('[data-testid="assistant-question"]')
    await question.setValue(' a ')
    expect(wrapper.get('[data-testid="assistant-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="assistant-question-validation"]').text()).toContain('至少需要 2 個字元')
    await wrapper.get('form.assistant-composer').trigger('submit')
    expect(wrapper.get('[data-testid="assistant-question-validation"]').text()).toContain('至少需要 2 個字元')

    await wrapper.get('[data-testid="assistant-open-drawer"]').trigger('click')
    const drawerQuestion = wrapper.get('[data-testid="assistant-drawer-question"]')
    await drawerQuestion.setValue(' b ')
    expect(wrapper.get('[data-testid="assistant-drawer-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="assistant-drawer-question-validation"]').text()).toContain('至少需要 2 個字元')
    await wrapper.get('#assistant-drawer form').trigger('submit')
    expect(wrapper.get('[data-testid="assistant-drawer-question-validation"]').text()).toContain('至少需要 2 個字元')
    wrapper.unmount()
  })
})

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}
