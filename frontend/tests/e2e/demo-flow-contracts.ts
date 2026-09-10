export const INSUFFICIENT_EVIDENCE_COPY = '目前沒有足夠的可讀適用來源，無法支持這項回答。'

const supportedPermissionCodes = new Set(['knowledge.read', 'case.read'])

export const FINALIZE_CONFIRMATION_SELECTOR = '[role="alertdialog"] [data-confirm]'

function shellVariable(name: string): string {
  return `(?:%${name}%|\\$env:${name}|\\$\\{${name}\\}|\\$${name})`
}

const documentedPermissionOperatorCommand = new RegExp(
  `^docker\\s+compose\\s+--project-directory\\s+\\.\\.\\s+` +
  `-p\\s+landvaluation-persistent-demo\\s+` +
  `-f\\s+\\.\\./docker-compose\\.yml\\s+` +
  `-f\\s+\\.\\./docker-compose\\.demo\\.yml\\s+` +
  `--env-file\\s+\\.\\./\\.env\\.example\\s+` +
  `exec\\s+-T\\s+api\\s+python(?:\\.exe)?\\s+-m\\s+app\\.demo\\s+permission\\s+` +
  `(?:${shellVariable('E2E_PERMISSION_ACTION')}|["']${shellVariable('E2E_PERMISSION_ACTION')}["'])\\s+` +
  `(?:${shellVariable('E2E_PERMISSION_CODE')}|["']${shellVariable('E2E_PERMISSION_CODE')}["'])$`,
  'i',
)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function caseIdentityMatches(
  actual: unknown,
  expected: { caseId: string; caseNo: string },
): boolean {
  return isRecord(actual)
    && actual.case_id === expected.caseId
    && actual.case_no === expected.caseNo
}

export function reviewIdFromSubmission(payload: unknown): string {
  if (!isRecord(payload) || typeof payload.review_id !== 'string' || !payload.review_id) {
    throw new Error('The real submission response did not provide review_id.')
  }
  return payload.review_id
}

export function reviewStartHasCompletedRun(payload: unknown): boolean {
  return isRecord(payload)
    && payload.outcome === 'COMPLETED'
    && isRecord(payload.run)
    && payload.run.run_status === 'COMPLETED'
}

export function isDocumentedPermissionOperatorCommand(command: string): boolean {
  return documentedPermissionOperatorCommand.test(command.trim().replace(/\s+/g, ' '))
}

export function isPermissionGateReady(input: {
  enabled: boolean
  command: string
  permission: string
}): boolean {
  return input.enabled
    && isDocumentedPermissionOperatorCommand(input.command)
    && supportedPermissionCodes.has(input.permission.trim())
}
