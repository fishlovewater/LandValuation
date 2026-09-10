import type { AuthUser } from '../modules/auth/auth.types'

export const ROLE_HOME: Record<string, string> = {
  REVIEWER: '/app/review/dashboard',
}

export function homeForRole(user: AuthUser): string {
  if (!user.permissions.includes('review.execute')) return '/app/unauthorized'
  return user.roles.map((role) => ROLE_HOME[role]).find(Boolean) ?? '/app/unauthorized'
}