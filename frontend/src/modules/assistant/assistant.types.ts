export interface AssistantContext {
  caseId?: string
  parcelId?: string
  formId?: string
  findingId?: string
  routeName: string
}

export type AssistantContextField = keyof AssistantContext

/** The only create-session fields accepted by the verified AI Assistant API. */
export interface AssistantSessionCreateDto {
  case_id: string
  form_instance_id: string
  selected_form_type: 'F03'
}

export interface AssistantSessionResponseDto {
  assistant_session_id: string
  case_id: string
  user_id: string
  form_instance_id: string | null
  current_step: string
  selected_form_type: string
  missing_fields: string[]
  missing_documents: string[]
  last_tool_name: string | null
  last_tool_status: string | null
  provider: string
  model_id: string
  prompt_version: string
  session_status: string
  created_at: string
  updated_at: string
}

export interface AssistantProgressResponseDto {
  assistant_session_id: string
  current_step: string
  missing_fields: string[]
  missing_documents: string[]
  confirmed_candidate_count: number
  pending_candidate_count: number
  completed_items: number
  total_items: number
}

export interface AssistantToolExecutionResponseDto {
  tool_name: string
  status: string
  result: Record<string, unknown>
}

/** The verified Assistant message request from the backend schema. */
export interface AssistantMessageRequestDto {
  content: string
  confirmed_fields?: Record<string, unknown>
  confirmed_candidate_ids?: string[]
  confirm_apply?: boolean
  run_calculation?: boolean
  run_validation?: boolean
  generate_report_pdf?: boolean
  nearest_facility?: NearestFacilityRequestDto | null
  confirm_action?: boolean
}

export type AssistantFacilityOriginType =
  | 'SUBJECT_PARCEL_ENTRANCE'
  | 'BENCHMARK_LAND_ENTRANCE'
  | 'DISTRICT_REPRESENTATIVE'
  | 'MANUAL_COORDINATE'

/** Exact nested request accepted by AssistantMessageRequest.nearest_facility. */
export interface NearestFacilityRequestDto {
  facility_type: string
  origin_type?: AssistantFacilityOriginType
  origin_address?: string | null
  origin_lat?: number | string | null
  origin_lng?: number | string | null
  origin_reference_id?: string | null
  confirm_lookup?: boolean
}

export interface AssistantCitationResponseDto {
  citation_id: string
  document_id: string
  document_title: string
  document_code: string
  version_no: number
  effective_from: string | null
  effective_to: string | null
  page_start: number | null
  page_end: number | null
  section_title: string | null
  article_no: string | null
  quoted_text: string
  supporting_quote?: string | null
  supported_claim?: string | null
}

export interface AssistantMessageResponseDto {
  session: AssistantSessionResponseDto
  reply: string
  progress: AssistantProgressResponseDto
  tools: AssistantToolExecutionResponseDto[]
}

export interface AssistantQuestionRequestDto {
  question: string
  as_of_date?: string | null
  document_types?: string[]
  limit?: number
}

export type AssistantAnswerStatus =
  | 'SUPPORTED'
  | 'EVIDENCE_ONLY'
  | 'CLARIFICATION_REQUIRED'
  | 'NO_RELEVANT_SOURCE'
  | 'CASE_CONTEXT_NOT_AVAILABLE'

export interface AssistantClaimResponseDto {
  text: string
  citation_ids: string[]
}

export interface AssistantUnreadableSourceResponseDto {
  document_id: string
  document_title: string
  original_filename: string
  reason: string
}

export interface AssistantQuestionResponseDto {
  assistant_session_id: string
  answer_status: AssistantAnswerStatus
  answer: string
  generation_mode: string
  next_action: string
  clarification_question?: string | null
  claims: AssistantClaimResponseDto[]
  citations: AssistantCitationResponseDto[]
  unreadable_sources: AssistantUnreadableSourceResponseDto[]
}

/** Raw response returned by POST /knowledge/ask for context-free knowledge questions. */
export interface KnowledgeQuestionCitationResponseDto {
  chunk_id: string
  document_id: string
  document_title: string
  document_code: string
  version_no: number
  effective_from: string | null
  effective_to: string | null
  page_start: number | null
  page_end: number | null
  section_title: string | null
  article_no: string | null
  quoted_text: string
  supporting_quote?: string | null
  supported_claim?: string | null
}

export interface KnowledgeQuestionResponseDto {
  answer_status: AssistantAnswerStatus
  answer: string
  generation_mode: string
  next_action: string
  clarification_question?: string | null
  citations: KnowledgeQuestionCitationResponseDto[]
  unreadable_sources: AssistantUnreadableSourceResponseDto[]
}

export interface AssistantSessionModel {
  assistantSessionId: string
  caseId: string
  formInstanceId: string | null
  currentStep: string
  selectedFormType: string
  missingFields: string[]
  missingDocuments: string[]
  sessionStatus: string
  updatedAt: string
}

export interface AssistantCitationModel {
  citationId: string
  documentId: string | null
  documentName: string | null
  documentCode: string | null
  versionNo: number | null
  effectiveFrom: string | null
  effectiveTo: string | null
  pageStart: number | null
  pageEnd: number | null
  sectionTitle: string | null
  articleNo: string | null
  quotedText: string | null
  supportingQuote: string | null
  supportedClaim: string | null
}

export interface AssistantClaimModel {
  text: string
  citationIds: string[]
}

export interface AssistantAnswerModel {
  answerStatus: AssistantAnswerStatus
  text: string
  generationMode: string
  nextAction: string
  clarificationQuestion: string | null
  claims: AssistantClaimModel[]
  citations: AssistantCitationModel[]
  supported: boolean
}

export interface AssistantChatMessage {
  id: string
  role: 'user' | 'assistant'
  content?: string
  answer?: AssistantAnswerModel
}
