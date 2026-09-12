import type { RouteLocationNormalizedLoaded } from 'vue-router'
import type { AssistantConversationContextDto, KnowledgeConversationDto } from './assistant.types'

function routeString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function assistantWorkspace(routeName: unknown, explicitWorkspace?: unknown): string | null {
  const explicit = routeString(explicitWorkspace).toLowerCase()
  if (explicit) return explicit
  const name = String(routeName ?? '')
  if (name.startsWith('valuation-')) return 'valuation'
  if (name.startsWith('review-')) return 'review'
  if (name.startsWith('history-')) return 'history'
  return null
}

export function assistantRouteContext(
  route: Pick<RouteLocationNormalizedLoaded, 'name' | 'params' | 'query'>,
  resolvedCaseId = '',
): AssistantConversationContextDto {
  const caseId = routeString(route.query.caseId)
    || routeString(route.query.case_id)
    || routeString(route.params.caseId)
    || resolvedCaseId.trim()
  const reviewId = routeString(route.params.reviewId)
    || routeString(route.query.reviewId)
    || routeString(route.query.review_id)
  const findingId = routeString(route.query.finding)
    || routeString(route.query.findingId)
    || routeString(route.query.finding_id)
  const workspace = assistantWorkspace(route.name, route.query.workspace)

  return {
    case_id: caseId || null,
    review_id: caseId ? reviewId || null : null,
    finding_id: caseId ? findingId || null : null,
    workspace,
  }
}

export function conversationMatchesAssistantContext(
  conversation: KnowledgeConversationDto,
  context: AssistantConversationContextDto,
): boolean {
  return (conversation.case_id ?? '') === (context.case_id ?? '')
    && (conversation.review_id ?? '') === (context.review_id ?? '')
    && (conversation.finding_id ?? '') === (context.finding_id ?? '')
    && (conversation.workspace ?? '') === (context.workspace ?? '')
}

export function assistantConversationRouteQuery(conversation: KnowledgeConversationDto): Record<string, string> {
  const query: Record<string, string> = { conversationId: conversation.conversation_id }
  if (conversation.case_id) query.caseId = conversation.case_id
  if (conversation.review_id) query.reviewId = conversation.review_id
  if (conversation.finding_id) query.findingId = conversation.finding_id
  if (conversation.workspace) query.workspace = conversation.workspace
  return query
}
