import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { assistantApi, AssistantContextError } from '../../src/modules/assistant/assistant.api'
import { http } from '../../src/api/http'

const sessionId = '33333333-3333-4333-8333-333333333333'

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0]) {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

describe('Assistant API transport', () => {
  const originalAdapter = http.defaults.adapter

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    http.defaults.adapter = originalAdapter
  })

  it('sends only the real AssistantMessageRequest action fields', async () => {
    const requests: Array<{ url?: string; data?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
      })
      return response({} as never, config)
    }) as unknown as typeof originalAdapter

    await assistantApi.sendMessage(sessionId, {
      content: '請執行正式計算',
      run_calculation: true,
      confirm_action: true,
    })

    expect(requests).toEqual([{
      url: `/ai-assistant/sessions/${sessionId}/messages`,
      data: {
        content: '請執行正式計算',
        run_calculation: true,
        confirm_action: true,
      },
    }])
  })

  it('preserves the optional cited-question filters without adding case context', async () => {
    const requests: Array<{ url?: string; data?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
      })
      return response({} as never, config)
    }) as unknown as typeof originalAdapter

    await assistantApi.askQuestion(sessionId, {
      question: '  請核對適用條件  ',
      as_of_date: '2026-09-01',
      document_types: ['LAW', 'GUIDE'],
      limit: 7,
    })

    expect(requests).toEqual([{
      url: `/ai-assistant/sessions/${sessionId}/questions`,
      data: {
        question: '請核對適用條件',
        as_of_date: '2026-09-01',
        document_types: ['LAW', 'GUIDE'],
        limit: 7,
      },
    }])
    expect(JSON.stringify(requests[0]?.data)).not.toContain('case_id')
  })

  it('rejects a one-character cited question with a specific validation error', async () => {
    const adapter = vi.fn()
    http.defaults.adapter = adapter as unknown as typeof originalAdapter

    await expect(assistantApi.askQuestion(sessionId, { question: '？' })).rejects.toThrow('問題至少需要 2 個字元')
    await expect(assistantApi.askQuestion(sessionId, { question: '？' })).rejects.not.toBeInstanceOf(AssistantContextError)
    expect(adapter).not.toHaveBeenCalled()
  })

  it('sends context-free knowledge questions without case or session context', async () => {
    const chunkId = '44444444-4444-4444-8444-444444444444'
    const requests: Array<{ url?: string; data?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
      })
      return response({
        answer_status: 'SUPPORTED',
        answer: '此條文有直接來源支持。',
        generation_mode: 'ollama',
        next_action: 'NONE',
        clarification_question: null,
        citations: [{
          chunk_id: chunkId,
          document_id: '55555555-5555-4555-8555-555555555555',
          document_title: '測試法規',
          document_code: 'LAW-001',
          version_no: 1,
          effective_from: null,
          effective_to: null,
          page_start: 1,
          page_end: 1,
          section_title: '第一條',
          article_no: '1',
          quoted_text: '此條文有直接來源支持。',
          supporting_quote: '此條文有直接來源支持。',
          supported_claim: '此條文有直接來源支持。',
        }],
        unreadable_sources: [],
      }, config)
    }) as unknown as typeof originalAdapter

    const result = await assistantApi.askGeneralQuestion({ question: '  請問第一條內容？  ' })

    expect(requests).toEqual([{
      url: '/knowledge/ask',
      data: { question: '請問第一條內容？' },
    }])
    expect(JSON.stringify(requests[0]?.data)).not.toContain('case_id')
    expect(result.citations[0]?.citation_id).toBe(chunkId)
    expect(result.claims).toEqual([{ text: '此條文有直接來源支持。', citation_ids: [chunkId] }])
  })

  it('keeps evidence-only knowledge candidates renderable without presenting them as an AI legal conclusion', async () => {
    const chunkId = '66666666-6666-4666-8666-666666666666'
    http.defaults.adapter = vi.fn(async (config) => response({
      answer_status: 'EVIDENCE_ONLY',
      answer: '已找到可供查核的資料；此階段不產生正式規則結論。',
      generation_mode: 'EVIDENCE_ONLY',
      next_action: 'REVIEW_CITED_SOURCES',
      clarification_question: null,
      citations: [{
        chunk_id: chunkId,
        document_id: '77777777-7777-4777-8777-777777777777',
        document_title: '土地估價規範',
        document_code: 'LAW-002',
        version_no: 1,
        effective_from: null,
        effective_to: null,
        page_start: 3,
        page_end: 3,
        section_title: '適用規定',
        article_no: '第 2 條',
        quoted_text: '候選來源內容。',
        supporting_quote: null,
        supported_claim: null,
      }],
      unreadable_sources: [],
    }, config)) as unknown as typeof originalAdapter

    const result = await assistantApi.askGeneralQuestion({ question: '查一下土地估價規定' })

    expect(result.answer_status).toBe('EVIDENCE_ONLY')
    expect(result.claims).toEqual([{
      text: '以下為可供人工查核的候選來源，尚未經 AI 驗證為正式規則結論。',
      citation_ids: [chunkId],
    }])
  })
})
