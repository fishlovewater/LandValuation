import { describe, expect, it } from 'vitest'
import {
  assistantConversationRouteQuery,
  assistantRouteContext,
  assistantWorkspace,
  conversationMatchesAssistantContext,
} from '../../src/modules/assistant/assistant.context'
import type { KnowledgeConversationDto } from '../../src/modules/assistant/assistant.types'

function route(name: string, params: Record<string, string> = {}, query: Record<string, string> = {}) {
  return { name, params, query }
}

function conversation(overrides: Partial<KnowledgeConversationDto> = {}): KnowledgeConversationDto {
  return {
    conversation_id: 'conversation-1',
    case_id: null,
    review_id: null,
    finding_id: null,
    workspace: null,
    title: '測試對話',
    provider: 'ollama',
    model_id: 'qwen3.5:latest',
    status: 'ACTIVE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
    ...overrides,
  }
}

describe('assistant shared context', () => {
  it('uses one workspace resolver for valuation, review, and history', () => {
    expect(assistantWorkspace('valuation-prepare')).toBe('valuation')
    expect(assistantWorkspace('review-workbench')).toBe('review')
    expect(assistantWorkspace('history-case')).toBe('history')
    expect(assistantWorkspace('assistant', 'history')).toBe('history')
  })

  it('binds the history subsystem case id into the same assistant context contract', () => {
    expect(assistantRouteContext(route('history-case', { caseId: 'case-1' }))).toEqual({
      case_id: 'case-1',
      review_id: null,
      finding_id: null,
      workspace: 'history',
    })
  })

  it('binds review subcontext after the review case id has been resolved', () => {
    expect(assistantRouteContext(
      route('review-workbench', { reviewId: 'review-1' }, { findingId: 'finding-1' }),
      'case-1',
    )).toEqual({
      case_id: 'case-1',
      review_id: 'review-1',
      finding_id: 'finding-1',
      workspace: 'review',
    })
  })

  it('keeps a conversation scoped to the exact subsystem context', () => {
    const context = assistantRouteContext(route('history-case', { caseId: 'case-1' }))
    expect(conversationMatchesAssistantContext(
      conversation({ case_id: 'case-1', workspace: 'history' }),
      context,
    )).toBe(true)
    expect(conversationMatchesAssistantContext(
      conversation({ case_id: 'case-1', workspace: 'valuation' }),
      context,
    )).toBe(false)
  })

  it('preserves subsystem context when opening the full assistant page', () => {
    expect(assistantConversationRouteQuery(conversation({
      case_id: 'case-1',
      review_id: 'review-1',
      finding_id: 'finding-1',
      workspace: 'review',
    }))).toEqual({
      conversationId: 'conversation-1',
      caseId: 'case-1',
      reviewId: 'review-1',
      findingId: 'finding-1',
      workspace: 'review',
    })
  })
})
