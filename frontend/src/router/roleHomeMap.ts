import type { AuthUser } from '../modules/auth/auth.types'
import { HISTORY_ROLES } from './roleAccess'

export { HISTORY_ROLES }

export const ROLE_HOME: Readonly<Record<string, string>> = {
  APPRAISER: '/app/valuation/dashboard',
  REVIEWER: '/app/review/dashboard',
  INSPECTOR: '/app/history/search',
  ADMIN: '/app',
  SYSTEM_ADMIN: '/app',
  SUPERADMIN: '/app',
}

const UNKNOWN_ROLE_HOME = '/app/unauthorized'

export function homeFor(user: Pick<AuthUser, 'roles'> | null | undefined): string {
  for (const role of user?.roles ?? []) {
    const home = ROLE_HOME[role]
    if (home) return home
  }
  return UNKNOWN_ROLE_HOME
}
