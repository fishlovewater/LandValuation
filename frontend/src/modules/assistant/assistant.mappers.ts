import type {
  AssistantAnswerModel,
  AssistantAnswerRoute,
  AssistantCitationModel,
  AssistantCitationResponseDto,
  AssistantClaimModel,
  AssistantQuestionResponseDto,
  AssistantSessionModel,
  AssistantSessionResponseDto,
} from './assistant.types'

export const ASSISTANT_UNSUPPORTED_QUESTION_COPY = '目前沒有足夠的可讀適用來源，無法支持這項回答。'

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const result = value.trim()
  return result || null
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function nullableDate(value: unknown): string | null {
  return nonEmptyString(value)
}

export function mapAssistantSession(dto: AssistantSessionResponseDto): AssistantSessionModel {
  return {
    assistantSessionId: dto.assistant_session_id,
    caseId: dto.case_id,
    formInstanceId: dto.form_instance_id,
    currentStep: dto.current_step,
    selectedFormType: dto.selected_form_type,
    missingFields: Array.isArray(dto.missing_fields) ? [...dto.missing_fields] : [],
    missingDocuments: Array.isArray(dto.missing_documents) ? [...dto.missing_documents] : [],
    sessionStatus: dto.session_status,
    updatedAt: dto.updated_at,
  }
}

export function mapAssistantCitation(dto: AssistantCitationResponseDto): AssistantCitationModel {
  return {
    citationId: nonEmptyString(dto.citation_id) ?? '',
    documentId: nonEmptyString(dto.document_id),
    documentName: nonEmptyString(dto.document_title),
    documentCode: nonEmptyString(dto.document_code),
    versionNo: nullableNumber(dto.version_no),
    effectiveFrom: nullableDate(dto.effective_from),
    effectiveTo: nullableDate(dto.effective_to),
    pageStart: nullableNumber(dto.page_start),
    pageEnd: nullableNumber(dto.page_end),
    sectionTitle: nonEmptyString(dto.section_title),
    articleNo: nonEmptyString(dto.article_no),
    quotedText: nonEmptyString(dto.quoted_text),
    supportingQuote: nonEmptyString(dto.supporting_quote),
    supportedClaim: nonEmptyString(dto.supported_claim),
  }
}

function unsupportedAnswer(dto: AssistantQuestionResponseDto): AssistantAnswerModel {
  return {
    answerStatus: dto.answer_status,
    text: ASSISTANT_UNSUPPORTED_QUESTION_COPY,
    answerRoute: normalizeAnswerRoute(dto.answer_route),
    generationMode: dto.generation_mode,
    nextAction: dto.next_action,
    clarificationQuestion: nonEmptyString(dto.clarification_question),
    claims: [],
    citations: [],
    supported: false,
  }
}

function normalizeAnswerRoute(value: unknown): AssistantAnswerRoute {
  return value === 'CHAT' || value === 'CASE' || value === 'HYBRID' || value === 'KNOWLEDGE'
    ? value
    : 'KNOWLEDGE'
}

function completeClaimGraph(
  dto: AssistantQuestionResponseDto,
  citations: AssistantCitationModel[],
): { claims: AssistantClaimModel[]; supported: boolean } {
  if (dto.answer_status !== 'SUPPORTED' && dto.answer_status !== 'EVIDENCE_ONLY') {
    return { claims: [], supported: false }
  }
  if (!nonEmptyString(dto.answer)) return { claims: [], supported: false }
  if (!Array.isArray(dto.claims) || !Array.isArray(dto.citations) || !citations.length) {
    return { claims: [], supported: false }
  }

  const returnedCitationIds = citations.map((citation) => citation.citationId)
  const citationIdSet = new Set(returnedCitationIds)
  if (returnedCitationIds.some((id) => !id) || citationIdSet.size !== returnedCitationIds.length) {
    return { claims: [], supported: false }
  }

  const claims: AssistantClaimModel[] = []
  const usedCitationIds = new Set<string>()
  for (const claim of dto.claims) {
    const text = nonEmptyString(claim?.text)
    const rawCitationIds = claim?.citation_ids
    if (!Array.isArray(rawCitationIds) || rawCitationIds.some((id: unknown) => typeof id !== 'string' || !id.trim())) {
      return { claims: [], supported: false }
    }
    const citationIds = rawCitationIds.map((id) => id.trim())
    if (!text || !citationIds.length || new Set(citationIds).size !== citationIds.length || citationIds.some((id) => !citationIdSet.has(id))) {
      return { claims: [], supported: false }
    }
    citationIds.forEach((id) => usedCitationIds.add(id))
    claims.push({ text, citationIds })
  }

  return {
    claims,
    supported: Boolean(claims.length) && usedCitationIds.size === citationIdSet.size,
  }
}

export function mapAssistantQuestion(dto: AssistantQuestionResponseDto): AssistantAnswerModel {
  const answerRoute = normalizeAnswerRoute(dto.answer_route)
  const directAnswer = nonEmptyString(dto.answer)
  if (
    dto.answer_status === 'SUPPORTED'
    && directAnswer
    && (answerRoute === 'CHAT' || answerRoute === 'CASE')
  ) {
    return {
      answerStatus: dto.answer_status,
      text: directAnswer,
      answerRoute,
      generationMode: dto.generation_mode,
      nextAction: dto.next_action,
      clarificationQuestion: nonEmptyString(dto.clarification_question),
      claims: [],
      citations: [],
      supported: true,
    }
  }

  const citations = (Array.isArray(dto.citations) ? dto.citations : []).map(mapAssistantCitation)
  const graph = completeClaimGraph(dto, citations)
  if (!graph.supported) return unsupportedAnswer(dto)

  return {
    answerStatus: dto.answer_status,
    text: nonEmptyString(dto.answer) ?? ASSISTANT_UNSUPPORTED_QUESTION_COPY,
    answerRoute,
    generationMode: dto.generation_mode,
    nextAction: dto.next_action,
    clarificationQuestion: nonEmptyString(dto.clarification_question),
    claims: graph.claims,
    citations,
    supported: true,
  }
}

/** Compatibility name for callers that render a mapped Assistant answer. */
export const mapAssistantAnswer = mapAssistantQuestion
