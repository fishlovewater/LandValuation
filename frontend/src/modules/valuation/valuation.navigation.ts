import type { LocationQueryRaw, RouteLocationRaw, RouteRecordName } from 'vue-router'
import type { ValuationWorkspaceStage } from './valuation.types'

const STAGE_ROUTE_NAMES: Readonly<Record<ValuationWorkspaceStage, string>> = {
  case: 'valuation-case',
  documents: 'valuation-documents',
  'ai-review': 'valuation-ai-review',
  data: 'valuation-data',
  calculation: 'valuation-calculation',
  report: 'valuation-report',
}

const ROUTE_STAGE_NAMES = new Map<string, ValuationWorkspaceStage>(
  Object.entries(STAGE_ROUTE_NAMES).map(([stage, routeName]) => [routeName, stage as ValuationWorkspaceStage]),
)

export function valuationStageRouteName(stage: ValuationWorkspaceStage): string {
  return STAGE_ROUTE_NAMES[stage]
}

export function valuationStageFromRouteName(name: RouteRecordName | null | undefined): ValuationWorkspaceStage | null {
  return name == null ? null : ROUTE_STAGE_NAMES.get(String(name)) ?? null
}

export function valuationStageRoute(
  caseId: string,
  stage: ValuationWorkspaceStage,
  query?: LocationQueryRaw,
): RouteLocationRaw {
  return {
    name: valuationStageRouteName(stage),
    params: { caseId },
    ...(query ? { query } : {}),
  }
}
