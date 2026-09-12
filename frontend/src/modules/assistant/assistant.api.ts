import { isAxiosError } from 'axios'
import { ForbiddenError, http } from '../../api/http'
import { mapAssistantSession } from './assistant.mappers'
import type {
  AssistantConversationContextDto,
  AssistantHistoryMessageDto,
  AssistantMessageResponseDto,
  AssistantMessageRequestDto,
  AssistantQuestionRequestDto,
  AssistantQuestionResponseDto,
  AssistantSessionModel,
  AssistantSessionResponseDto,
  KnowledgeConversationDto,
  KnowledgeConversationMessageDto,
  KnowledgeQuestionResponseDto,
} from './assistant.types'

export const ASSISTANT_QUESTION_MIN_LENGTH = 2
export const ASSISTANT_QUESTION_VALIDATION_MESSAGE = '問題至少需要 2 個字元。'

export class AssistantContextError extends Error {
  constructor() {
    super('請先開啟一筆可查看的比準地地價估計表案件，再使用案件相關功能。')
    this.name = 'AssistantContextError'
  }
}

export class AssistantQuestionValidationError extends Error {
  constructor() {
    super(ASSISTANT_QUESTION_VALIDATION_MESSAGE)
    this.name = 'AssistantQuestionValidationError'
  }
}

export function canUseAssistant(permissions: readonly string[]): boolean {
  return permissions.includes('assistant.use')
}

export function canAccessLegacyAssistantSession(permissions: readonly string[]): boolean {
  return hasPermissions(permissions, ['assistant.use', 'valuation.read'])
}

export function canAskAssistantQuestion(permissions: readonly string[]): boolean {
  return hasPermissions(permissions, [
    'assistant.use',
    'valuation.read',
  ])
}

export function canUpdateAssistantValuation(permissions: readonly string[]): boolean {
  return permissions.includes('valuation.update')
}

function hasPermissions(permissions: readonly string[], required: readonly string[]): boolean {
  const granted = new Set(permissions)
  return required.every((permission) => granted.has(permission))
}

export function mapKnowledgeQuestionResponse(data: KnowledgeQuestionResponseDto): AssistantQuestionResponseDto {
  const citations = (data.citations ?? []).map((citation) => ({
    citation_id: citation.chunk_id,
    document_id: citation.document_id,
    document_title: citation.document_title,
    document_code: citation.document_code,
    version_no: citation.version_no,
    effective_from: citation.effective_from,
    effective_to: citation.effective_to,
    page_start: citation.page_start,
    page_end: citation.page_end,
    section_title: citation.section_title,
    article_no: citation.article_no,
    quoted_text: citation.quoted_text,
    supporting_quote: citation.supporting_quote,
    supported_claim: citation.supported_claim,
  }))
  const citationIdsByClaim = new Map<string, string[]>()
  for (const citation of citations) {
    const claim = citation.supported_claim?.trim()
    if (!claim) continue
    const ids = citationIdsByClaim.get(claim) ?? []
    if (!ids.includes(citation.citation_id)) ids.push(citation.citation_id)
    citationIdsByClaim.set(claim, ids)
  }
  const claims = Array.from(citationIdsByClaim, ([text, citation_ids]) => ({ text, citation_ids }))
  if (data.answer_status === 'EVIDENCE_ONLY' && citations.length && !claims.length) {
    claims.push({
      text: '以下是目前找到的相關來源，請確認內容是否符合你的問題。',
      citation_ids: citations.map((citation) => citation.citation_id),
    })
  }
  return {
    assistant_session_id: '',
    answer_status: data.answer_status,
    answer: data.answer,
    answer_route: data.answer_route ?? 'KNOWLEDGE',
    generation_mode: data.generation_mode,
    next_action: data.next_action,
    clarification_question: data.clarification_question,
    claims,
    citations,
    unreadable_sources: data.unreadable_sources ?? [],
  }
}

export const assistantApi = {
  async getSession(sessionId: string, signal?: AbortSignal): Promise<AssistantSessionModel> {
    const normalizedId = sessionId.trim()
    if (!normalizedId) throw new AssistantContextError()
    const response = await http.get<AssistantSessionResponseDto>(
      `/ai-assistant/sessions/${encodeURIComponent(normalizedId)}`,
      { signal },
    )
    return mapAssistantSession(response.data)
  },

  async sendMessage(
    sessionId: string,
    request: AssistantMessageRequestDto,
    signal?: AbortSignal,
  ): Promise<AssistantMessageResponseDto> {
    const normalizedId = sessionId.trim()
    const normalizedContent = request.content.trim()
    if (!normalizedId || !normalizedContent) throw new AssistantContextError()
    if (normalizedContent.length > 4000) throw new Error('問題內容不可超過 4000 字。')

    const payload: AssistantMessageRequestDto = { content: normalizedContent }
    if (request.confirmed_fields !== undefined) payload.confirmed_fields = request.confirmed_fields
    if (request.confirmed_candidate_ids !== undefined) payload.confirmed_candidate_ids = [...request.confirmed_candidate_ids]
    if (request.confirm_apply !== undefined) payload.confirm_apply = request.confirm_apply
    if (request.run_calculation !== undefined) payload.run_calculation = request.run_calculation
    if (request.run_validation !== undefined) payload.run_validation = request.run_validation
    if (request.generate_report_pdf !== undefined) payload.generate_report_pdf = request.generate_report_pdf
    if (request.nearest_facility !== undefined) payload.nearest_facility = request.nearest_facility
    if (request.confirm_action !== undefined) payload.confirm_action = request.confirm_action

    const response = await http.post<AssistantMessageResponseDto>(
      `/ai-assistant/sessions/${encodeURIComponent(normalizedId)}/messages`,
      payload,
      { signal },
    )
    return response.data
  },

  async askQuestion(
    sessionId: string,
    request: AssistantQuestionRequestDto,
    signal?: AbortSignal,
  ): Promise<AssistantQuestionResponseDto> {
    const normalizedId = sessionId.trim()
    const question = request.question.trim()
    if (!normalizedId) throw new AssistantContextError()
    if (question.length < ASSISTANT_QUESTION_MIN_LENGTH) throw new AssistantQuestionValidationError()
    if (question.length > 2000) throw new Error('問題內容不可超過 2000 字。')

    const payload: AssistantQuestionRequestDto = { question }
    if (request.as_of_date !== undefined) payload.as_of_date = request.as_of_date
    if (request.document_types !== undefined) payload.document_types = [...request.document_types]
    if (request.limit !== undefined) payload.limit = request.limit

    const response = await http.post<AssistantQuestionResponseDto>(
      `/ai-assistant/sessions/${encodeURIComponent(normalizedId)}/questions`,
      payload,
      { signal },
    )
    return response.data
  },

  async getSessionMessages(sessionId: string, signal?: AbortSignal): Promise<AssistantHistoryMessageDto[]> {
    const normalizedId = sessionId.trim()
    if (!normalizedId) throw new AssistantContextError()
    const response = await http.get<AssistantHistoryMessageDto[]>(
      `/ai-assistant/sessions/${encodeURIComponent(normalizedId)}/messages`,
      { signal },
    )
    return response.data
  },

  async createKnowledgeConversation(
    context: AssistantConversationContextDto = {},
    signal?: AbortSignal,
  ): Promise<KnowledgeConversationDto> {
    const response = await http.post<KnowledgeConversationDto>('/knowledge/conversations', context, { signal })
    return response.data
  },

  async listKnowledgeConversations(signal?: AbortSignal): Promise<KnowledgeConversationDto[]> {
    const response = await http.get<KnowledgeConversationDto[]>('/knowledge/conversations', { signal })
    return response.data
  },

  async getKnowledgeConversationMessages(
    conversationId: string,
    signal?: AbortSignal,
  ): Promise<KnowledgeConversationMessageDto[]> {
    const normalizedId = conversationId.trim()
    if (!normalizedId) return []
    const response = await http.get<KnowledgeConversationMessageDto[]>(
      `/knowledge/conversations/${encodeURIComponent(normalizedId)}/messages`,
      { signal },
    )
    return response.data
  },

  async askKnowledgeConversation(
    conversationId: string,
    request: AssistantQuestionRequestDto,
    signal?: AbortSignal,
  ): Promise<AssistantQuestionResponseDto> {
    const normalizedId = conversationId.trim()
    const question = request.question.trim()
    if (!normalizedId) throw new AssistantContextError()
    if (question.length < ASSISTANT_QUESTION_MIN_LENGTH) throw new AssistantQuestionValidationError()
    if (question.length > 2000) throw new Error('問題內容不可超過 2000 字。')
    const payload: AssistantQuestionRequestDto = { question }
    if (request.case_id !== undefined) payload.case_id = request.case_id
    if (request.review_id !== undefined) payload.review_id = request.review_id
    if (request.finding_id !== undefined) payload.finding_id = request.finding_id
    if (request.workspace !== undefined) payload.workspace = request.workspace
    if (request.as_of_date !== undefined) payload.as_of_date = request.as_of_date
    if (request.document_types !== undefined) payload.document_types = [...request.document_types]
    if (request.limit !== undefined) payload.limit = request.limit
    const response = await http.post<KnowledgeQuestionResponseDto>(
      `/knowledge/conversations/${encodeURIComponent(normalizedId)}/messages`,
      payload,
      { signal },
    )
    return mapKnowledgeQuestionResponse(response.data)
  },

  async askGeneralQuestion(
    request: AssistantQuestionRequestDto,
    signal?: AbortSignal,
  ): Promise<AssistantQuestionResponseDto> {
    const question = request.question.trim()
    if (question.length < ASSISTANT_QUESTION_MIN_LENGTH) throw new AssistantQuestionValidationError()
    if (question.length > 2000) throw new Error('問題內容不可超過 2000 字。')
    const payload: AssistantQuestionRequestDto = { question }
    if (request.as_of_date !== undefined) payload.as_of_date = request.as_of_date
    if (request.document_types !== undefined) payload.document_types = [...request.document_types]
    if (request.limit !== undefined) payload.limit = request.limit
    const response = await http.post<KnowledgeQuestionResponseDto>('/knowledge/ask', payload, { signal })
    return mapKnowledgeQuestionResponse(response.data)
  },
}

function responseErrorCode(error: unknown): string {
  if (!isAxiosError(error)) return ''
  const data = error.response?.data as { error?: { code?: unknown } } | undefined
  return typeof data?.error?.code === 'string' ? data.error.code : ''
}

export function safeAssistantErrorMessage(error: unknown): string {
  if (error instanceof AssistantContextError) return error.message
  if (error instanceof AssistantQuestionValidationError) return error.message
  if (error instanceof ForbiddenError) return error.message
  if (isAxiosError(error) && error.response?.status === 404) {
    return '目前的智能助理對話已失效，請重新開啟智能助理。'
  }
  if (isAxiosError(error) && error.response?.status === 409) {
    const code = responseErrorCode(error)
    if (code === 'ASSISTANT_SESSION_CLOSED') {
      return '目前的智能助理對話已結束，請重新開啟智能助理。'
    }
    if (code === 'ASSISTANT_CONTEXT_CONFLICT') {
      return '目前對話綁定的案件情境與頁面不一致，請開啟新的對話。'
    }
    if (code === 'CASE_STATE_CONFLICT') {
      return '案件目前已進入不可修改狀態；仍可查詢案件或法規，但不能執行修改型操作。'
    }
    if (code === 'FORM_STATE_CONFLICT') {
      return '目前比準地地價估計表狀態不可修改；仍可查詢資料，但不能執行需要變更表單的操作。'
    }
    return '目前操作與案件或表單狀態衝突，請重新整理後確認目前狀態。'
  }
  if (isAxiosError(error) && error.response?.status === 422) {
    const code = responseErrorCode(error)
    if (code === 'ASSISTANT_CONTEXT_INVALID') {
      return '目前智能助理無法使用這個工作情境，請重新整理後再試。'
    }
    if (code === 'CASE_CONTEXT_INTEGRATION_PENDING') {
      return '目前這項知識查詢尚未支援案件情境，請改用一般知識問題。'
    }
    return '問題內容或目前案件情境無法處理，請確認後再試。'
  }
  return '智能助理目前無法回應，請稍後再試。'
}
