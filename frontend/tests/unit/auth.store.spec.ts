import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authApi } from '../../src/modules/auth/auth.api'
import { useAuthStore } from '../../src/modules/auth/auth.store'
import { readAccessToken } from '../../src/utils/storage'

describe('auth store', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('stores only the access token and loads the current user after login', async () => {
    vi.spyOn(authApi, 'login').mockResolvedValue({ accessToken: 'test-token', tokenType: 'bearer', expiresIn: 1800 })
    vi.spyOn(authApi, 'me').mockResolvedValue({
      userId: 'user-1',
      username: 'reviewer',
      displayName: '審查人員',
      isActive: true,
      roles: ['REVIEWER'],
      permissions: ['review.execute', 'review.decide'],
    })

    const store = useAuthStore()
    await store.login('reviewer', 'DoNotStoreThisPassword!')

    expect(readAccessToken()).toBe('test-token')
    expect(authApi.me).toHaveBeenCalledOnce()
    expect(store.user?.roles).toEqual(['REVIEWER'])
    expect(store.user?.permissions).toContain('review.execute')
    expect(JSON.stringify(sessionStorage)).not.toContain('DoNotStoreThisPassword!')
  })

  it('clears the whole auth session when requested by the HTTP 401 boundary', async () => {
    vi.spyOn(authApi, 'login').mockResolvedValue({ accessToken: 'expired-token', tokenType: 'bearer', expiresIn: 1 })
    vi.spyOn(authApi, 'me').mockResolvedValue({
      userId: 'user-1', username: 'reviewer', displayName: 'Reviewer', isActive: true,
      roles: ['REVIEWER'], permissions: ['review.execute'],
    })
    const store = useAuthStore()
    await store.login('reviewer', 'secret')

    store.clearSession()

    expect(readAccessToken()).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })
})