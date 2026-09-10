import type { AuthUser } from '../modules/auth/auth.types'
import { homeForRole } from './roleHomeMap'

interface GuardRoute {
  path: string
  fullPath: string
  meta: { requiresAuth?: boolean; permission?: string }
}

interface GuardAuthState {
  user: AuthUser | null
  initialized: boolean
  restore: () => Promise<void>
}

export function homeFor(user: AuthUser): string {
  return homeForRole(user)
}

export async function evaluateRouteAccess(to: GuardRoute, auth: GuardAuthState) {
  if (!auth.initialized) await auth.restore()
  if (!to.meta.requiresAuth) return true
  if (!auth.user) return { path: '/', query: { redirect: to.fullPath } }
  if (to.meta.permission && !auth.user.permissions.includes(to.meta.permission)) {
    return { path: '/app/unauthorized' }
  }
  return true
}