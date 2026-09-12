import type { NavigationGuard, RouteLocationNormalized } from 'vue-router'
import { tokenService } from '../api/http'
import { useAuthStore } from '../stores/auth.store'
import { homeFor } from './roleHomeMap'

export interface PermissionRouteMeta {
  requiresAuth?: boolean
  guestOnly?: boolean
  permission?: string
  permissions?: string[]
  anyPermission?: string[]
  roles?: string[]
}

function routeMeta(to: RouteLocationNormalized): PermissionRouteMeta[] {
  return to.matched.map((record) => record.meta as PermissionRouteMeta)
}

function requiresAuth(to: RouteLocationNormalized): boolean {
  return routeMeta(to).some((meta) => meta.requiresAuth === true)
}

function isGuestOnly(to: RouteLocationNormalized): boolean {
  return routeMeta(to).some((meta) => meta.guestOnly === true)
}

function hasPermission(to: RouteLocationNormalized, permissions: readonly string[]): boolean {
  const granted = new Set(permissions)
  for (const meta of routeMeta(to)) {
    if (meta.permission && !granted.has(meta.permission)) return false
    if (meta.permissions?.some((permission) => !granted.has(permission))) return false
    if (meta.anyPermission?.length && !meta.anyPermission.some((permission) => granted.has(permission))) {
      return false
    }
  }
  return true
}

function hasRole(to: RouteLocationNormalized, roles: readonly string[]): boolean {
  for (const meta of routeMeta(to)) {
    if (meta.roles?.length && !meta.roles.some((role) => roles.includes(role))) return false
  }
  return true
}

function loginRedirect(to: RouteLocationNormalized) {
  return {
    path: '/',
    query: { redirect: to.fullPath },
    replace: true,
  }
}

function homeRedirect(path: string) {
  return { path, replace: true }
}

/**
 * The guard owns session restoration and route permission checks so protected
 * views are never mounted while the current user is still unresolved.
 */
export function createAuthGuard(): NavigationGuard {
  return async (to) => {
    const authStore = useAuthStore()
    const token = tokenService.get()

    if (!token && authStore.user) authStore.logout()

    if (requiresAuth(to)) {
      if (!token) {
        authStore.logout()
        return loginRedirect(to)
      }

      if (!authStore.user && !(await authStore.restoreSession())) {
        return loginRedirect(to)
      }

      if (!authStore.user) return loginRedirect(to)
      if (!hasPermission(to, authStore.permissions) || !hasRole(to, authStore.roles)) {
        return homeRedirect('/app/unauthorized')
      }

      const roleHome = homeFor(authStore.user)
      if (to.path === '/app' && roleHome !== '/app') return homeRedirect(roleHome)
      return true
    }

    if (isGuestOnly(to) && token) {
      if (!authStore.user && !(await authStore.restoreSession())) return true
      if (authStore.user) return homeRedirect(homeFor(authStore.user))
    }

    return true
  }
}

export const authGuard = createAuthGuard()
