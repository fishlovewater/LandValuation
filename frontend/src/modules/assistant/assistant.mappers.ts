import type {
  AssistantAnswerModel,
  AssistantCitationModel,
  AssistantCitationResponseDto,
  AssistantClaimModel,
  AssistantContext,
  AssistantContextField,
  AssistantQuestionResponseDto,
  AssistantSessionCreateDto,
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

function normalizedContextValue(value: unknown): string | undefined {
  const result = nonEmptyString(value)
  return result ?? undefined
}

/**
 * Keep only fields explicitly allowed by the caller. Route/user/case data is
 * never copied implicitly, and the session adapter only serializes caseId and
 * formId because those are the verified create-session fields.
 */
export function sanitizeAssistantContext(
  context: AssistantContext,
  acceptedFields: readonly AssistantContextField[] = ['caseId', 'formId'],
): AssistantContext {
  const accepted = new Set(acceptedFields)
  return {
    caseId: accepted.has('caseId') ? normalizedContextValue(context.caseId) : undefined,
    parcelId: accepted.has('parcelId') ? normalizedContextValue(context.parcelId) : undefined,
    formId: accepted.has('formId') ? normalizedContextValue(context.formId) : undefined,
    findingId: accepted.has('findingId') ? normalizedContextValue(context.findingId) : undefined,
    routeName: accepted.has('routeName') ? normalizedContextValue(context.routeName) ?? '' : '',
  }
}

export function buildAssistantContextPayload(context: AssistantContext): AssistantSessionCreateDto {
  return {
    case_id: context.caseId?.trim() ?? '',
    form_instance_id: context.formId?.trim() ?? '',
    selected_form_type: 'F03',
  }
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
    generationMode: dto.generation_mode,
    nextAction: dto.next_action,
    clarificationQuestion: nonEmptyString(dto.clarification_question),
    claims: [],
    citations: [],
    supported: false,
  }
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
  const citations = (Array.isArray(dto.citations) ? dto.citations : []).map(mapAssistantCitation)
  const graph = completeClaimGraph(dto, citations)
  if (!graph.supported) return unsupportedAnswer(dto)

  return {
    answerStatus: dto.answer_status,
    text: nonEmptyString(dto.answer) ?? ASSISTANT_UNSUPPORTED_QUESTION_COPY,
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

export function isUsableAssistantContext(context: AssistantContext | null | undefined): context is AssistantContext & { caseId: string; formId: string } {
  return Boolean(context?.caseId?.trim() && context?.formId?.trim())
}
