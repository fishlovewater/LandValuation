import { describe, expect, it, vi } from 'vitest'

import { evaluateRouteAccess, homeFor } from '../../src/router/guards'
import type { AuthUser } from '../../src/modules/auth/auth.types'

const reviewer: AuthUser = {
  userId: '1', username: 'reviewer', displayName: 'Reviewer', isActive: true,
  roles: ['REVIEWER'], permissions: ['review.execute', 'review.decide'],
}

describe('route guard policy', () => {
  it('redirects unauthenticated users and preserves the intended destination', async () => {
    const restore = vi.fn()
    const result = await evaluateRouteAccess(
      { path: '/app/review/dashboard', fullPath: '/app/review/dashboard?q=1', meta: { requiresAuth: true } },
      { user: null, initialized: true, restore },
    )
    expect(result).toEqual({ path: '/', query: { redirect: '/app/review/dashboard?q=1' } })
  })

  it('restores an existing session before evaluating permissions', async () => {
    const state = { user: null as AuthUser | null, initialized: false, restore: vi.fn() }
    state.restore.mockImplementation(async () => { state.user = reviewer; state.initialized = true })
    const result = await evaluateRouteAccess(
      { path: '/app/review/dashboard', fullPath: '/app/review/dashboard', meta: { requiresAuth: true, permission: 'review.execute' } },
      state,
    )
    expect(state.restore).toHaveBeenCalledOnce()
    expect(result).toBe(true)
  })

  it('sends users without the required permission to unauthorized', async () => {
    const result = await evaluateRouteAccess(
      { path: '/app/review/dashboard', fullPath: '/app/review/dashboard', meta: { requiresAuth: true, permission: 'review.execute' } },
      { user: { ...reviewer, permissions: [] }, initialized: true, restore: vi.fn() },
    )
    expect(result).toEqual({ path: '/app/unauthorized' })
  })

  it('maps a verified reviewer to the review dashboard only when permission exists', () => {
    expect(homeFor(reviewer)).toBe('/app/review/dashboard')
    expect(homeFor({ ...reviewer, permissions: [] })).toBe('/app/unauthorized')
  })
})