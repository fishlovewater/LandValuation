import { isAxiosError } from 'axios'
import { ForbiddenError, http } from '../../api/http'
import { buildAssistantContextPayload, isUsableAssistantContext, mapAssistantSession } from './assistant.mappers'
import type {
  AssistantContext,
  AssistantMessageResponseDto,
  AssistantMessageRequestDto,
  AssistantQuestionRequestDto,
  AssistantQuestionResponseDto,
  AssistantSessionModel,
  AssistantSessionResponseDto,
  KnowledgeQuestionResponseDto,
} from './assistant.types'

export const ASSISTANT_QUESTION_MIN_LENGTH = 2
export const ASSISTANT_QUESTION_VALIDATION_MESSAGE = '問題至少需要 2 個字元。'

export class AssistantContextError extends Error {
  constructor() {
    super('請先從已授權的 F03 案件脈絡開啟智能助理。')
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

export function canStartAssistantSession(permissions: readonly string[]): boolean {
  return hasPermissions(permissions, ['assistant.use', 'valuation.read'])
}

export function canAskAssistantQuestion(permissions: readonly string[]): boolean {
  return hasPermissions(permissions, [
    'assistant.use',
    'valuation.read',
    'knowledge.read',
    'case.read',
  ])
}

export function canAskGeneralAssistantQuestion(permissions: readonly string[]): boolean {
  return hasPermissions(permissions, ['assistant.use', 'knowledge.read'])
}

export function canUpdateAssistantValuation(permissions: readonly string[]): boolean {
  return permissions.includes('valuation.update')
}

function hasPermissions(permissions: readonly string[], required: readonly string[]): boolean {
  const granted = new Set(permissions)
  return required.every((permission) => granted.has(permission))
}

export const assistantApi = {
  async createSession(context: AssistantContext, signal?: AbortSignal): Promise<AssistantSessionModel> {
    if (!isUsableAssistantContext(context)) throw new AssistantContextError()
    const response = await http.post<AssistantSessionResponseDto>(
      '/ai-assistant/sessions',
      buildAssistantContextPayload(context),
      { signal },
    )
    return mapAssistantSession(response.data)
  },

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
    const citations = (response.data.citations ?? []).map((citation) => ({
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
    if (response.data.answer_status === 'EVIDENCE_ONLY' && citations.length && !claims.length) {
      claims.push({
        text: '以下為可供人工查核的候選來源，尚未經 AI 驗證為正式規則結論。',
        citation_ids: citations.map((citation) => citation.citation_id),
      })
    }

    return {
      assistant_session_id: '',
      answer_status: response.data.answer_status,
      answer: response.data.answer,
      generation_mode: response.data.generation_mode,
      next_action: response.data.next_action,
      clarification_question: response.data.clarification_question,
      claims,
      citations,
      unreadable_sources: response.data.unreadable_sources ?? [],
    }
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
    return '找不到目前智能助理工作階段，請從已授權的案件重新開啟。'
  }
  if (isAxiosError(error) && error.response?.status === 409) {
    const code = responseErrorCode(error)
    if (code === 'ASSISTANT_SESSION_CLOSED') {
      return '目前智能助理工作階段已關閉，請重新建立工作階段。'
    }
    if (code === 'CASE_STATE_CONFLICT') {
      return '案件目前已進入不可修改狀態；仍可查詢案件或法規，但不能執行修改型操作。'
    }
    if (code === 'FORM_STATE_CONFLICT') {
      return '目前 F03 狀態不可修改；仍可查詢資料，但不能執行需要變更表單的操作。'
    }
    return '目前操作與案件或表單狀態衝突，請重新整理後確認目前狀態。'
  }
  return '智能助理目前無法回應，請稍後再試。'
}
