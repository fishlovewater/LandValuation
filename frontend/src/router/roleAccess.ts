/**
 * History uses the backend's verified role-scoped contract. It does not
 * expose a standalone History permission code.
 */
export const HISTORY_ROLES = [
  'APPRAISER',
  'REVIEWER',
  'INSPECTOR',
  'ADMIN',
  'SYSTEM_ADMIN',
  'SUPERADMIN',
] as const

export interface HistoryRoleScope {
  valuation: boolean
  review: boolean
}

/** Mirrors app.history.permissions.history_scope without inventing a permission code. */
export function historyScopeForRoles(roles: readonly string[]): HistoryRoleScope {
  const roleSet = new Set(roles)
  const fullAccess = ['INSPECTOR', 'ADMIN', 'SYSTEM_ADMIN', 'SUPERADMIN'].some((role) => roleSet.has(role))
  return {
    valuation: fullAccess || roleSet.has('APPRAISER'),
    review: fullAccess || roleSet.has('REVIEWER'),
  }
}

export function hasHistoryRole(roles: readonly string[]): boolean {
  return roles.some((role) => HISTORY_ROLES.includes(role as (typeof HISTORY_ROLES)[number]))
}
