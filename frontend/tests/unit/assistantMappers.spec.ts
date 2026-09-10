import { describe, expect, it } from 'vitest'
import { ASSISTANT_UNSUPPORTED_QUESTION_COPY, mapAssistantQuestion } from '../../src/modules/assistant/assistant.mappers'
import type { AssistantQuestionResponseDto } from '../../src/modules/assistant/assistant.types'

const citation = (citationId: string) => ({
  citation_id: citationId,
  document_id: '44444444-4444-4444-8444-444444444444',
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

function supportedQuestion(): AssistantQuestionResponseDto {
  return {
    assistant_session_id: '33333333-3333-4333-8333-333333333333',
    answer_status: 'SUPPORTED',
    answer: '本案應以正式來源核對適用條件。',
    generation_mode: 'MOCK',
    next_action: 'REVIEW_SOURCE',
    clarification_question: null,
    claims: [{
      text: '本案應以正式來源核對適用條件。',
      citation_ids: ['55555555-5555-4555-8555-555555555555'],
    }],
    citations: [citation('55555555-5555-4555-8555-555555555555')],
    unreadable_sources: [],
  }
}

describe('Assistant citation graph mapper', () => {
  it('fails closed when a claim contains a non-string citation id', () => {
    const dto = supportedQuestion()
    dto.claims[0]!.citation_ids = ['55555555-5555-4555-8555-555555555555', 0 as unknown as string]

    const mapped = mapAssistantQuestion(dto)

    expect(mapped).toMatchObject({
      supported: false,
      text: ASSISTANT_UNSUPPORTED_QUESTION_COPY,
      claims: [],
      citations: [],
    })
  })

  it('fails closed when a claim contains a blank citation id', () => {
    const dto = supportedQuestion()
    dto.claims[0]!.citation_ids = ['   ']

    expect(mapAssistantQuestion(dto).supported).toBe(false)
  })

  it('fails closed for duplicate citation ids within one claim', () => {
    const dto = supportedQuestion()
    dto.claims[0]!.citation_ids = [
      '55555555-5555-4555-8555-555555555555',
      '55555555-5555-4555-8555-555555555555',
    ]

    expect(mapAssistantQuestion(dto).supported).toBe(false)
  })

  it('fails closed when a returned citation is unused by every claim', () => {
    const dto = supportedQuestion()
    dto.citations.push(citation('66666666-6666-4666-8666-666666666666'))

    expect(mapAssistantQuestion(dto).supported).toBe(false)
  })
})
