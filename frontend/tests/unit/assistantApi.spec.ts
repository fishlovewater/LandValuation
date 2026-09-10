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
})
