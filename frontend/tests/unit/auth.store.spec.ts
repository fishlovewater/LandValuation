import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import { authApi } from '../../src/modules/auth/auth.api'
import type { AuthUser, TokenResponseDto } from '../../src/modules/auth/auth.types'
import { ForbiddenError, http, registerUnauthorizedHandler, tokenService } from '../../src/api/http'
import { useAuthStore } from '../../src/stores/auth.store'

const token: TokenResponseDto = {
  access_token: 'demo-access-token',
  token_type: 'bearer',
  expires_in: 1800,
}

const user: AuthUser = {
  id: 'user-001',
  username: 'reviewer.demo',
  email: 'reviewer@example.test',
  displayName: '示範審查員',
  roles: ['REVIEWER'],
  permissions: ['review.execute'],
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    tokenService.clear()
    vi.restoreAllMocks()
  })

  it('logs in in order, stores the token, then stores the mapped current user', async () => {
    const order: string[] = []
    vi.spyOn(authApi, 'login').mockImplementation(async () => {
      order.push('login')
      return token
    })
    const setToken = vi.spyOn(tokenService, 'set').mockImplementation((accessToken, expiresIn) => {
      order.push('token')
      sessionStorage.setItem('lva-demo-access-token', accessToken)
      sessionStorage.setItem('lva-demo-token-expires-at', String(Date.now() + expiresIn * 1000))
    })
    vi.spyOn(authApi, 'me').mockImplementation(async () => {
      order.push('me')
      expect(tokenService.get()).toBe(token.access_token)
      return user
    })

    const store = useAuthStore()
    await store.login({ username: user.username, password: 'not-recorded' })

    expect(order).toEqual(['login', 'token', 'me'])
    expect(setToken).toHaveBeenCalledWith(token.access_token, token.expires_in)
    expect(store.user).toEqual(user)
    expect(store.isAuthenticated).toBe(true)
    expect(store.roles).toEqual(user.roles)
    expect(store.permissions).toEqual(user.permissions)
    expect(store.isSubmitting).toBe(false)
  })

  it('ignores a second login while the first request is still submitting', async () => {
    let resolveLogin: (value: TokenResponseDto) => void = () => undefined
    const loginPromise = new Promise<TokenResponseDto>((resolve) => {
      resolveLogin = resolve
    })
    const login = vi.spyOn(authApi, 'login').mockReturnValue(loginPromise)
    vi.spyOn(authApi, 'me').mockResolvedValue(user)

    const store = useAuthStore()
    const first = store.login({ username: user.username, password: 'first' })
    const second = store.login({ username: user.username, password: 'second' })

    expect(store.isSubmitting).toBe(true)
    expect(login).toHaveBeenCalledTimes(1)

    resolveLogin(token)
    await Promise.all([first, second])
    expect(store.user).toEqual(user)
    expect(store.isSubmitting).toBe(false)
  })

  it('clears an issued token and user when fetching the current user fails', async () => {
    vi.spyOn(authApi, 'login').mockResolvedValue(token)
    vi.spyOn(authApi, 'me').mockRejectedValue(new Error('network unavailable'))
    const store = useAuthStore()

    await expect(store.login({ username: user.username, password: 'not-recorded' })).rejects.toThrow(
      'network unavailable',
    )

    expect(tokenService.get()).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isSubmitting).toBe(false)
  })

  it('logout clears the user and the token', async () => {
    vi.spyOn(authApi, 'login').mockResolvedValue(token)
    vi.spyOn(authApi, 'me').mockResolvedValue(user)
    const store = useAuthStore()
    await store.login({ username: user.username, password: 'not-recorded' })

    store.logout()

    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(tokenService.get()).toBeNull()
  })

  it('does not let a late session restore repopulate a user after logout', async () => {
    let resolveMe: (value: AuthUser) => void = () => undefined
    const pendingMe = new Promise<AuthUser>((resolve) => {
      resolveMe = resolve
    })
    tokenService.set('restore-before-logout', 1800)
    vi.spyOn(authApi, 'me').mockReturnValue(pendingMe)
    const store = useAuthStore()

    const restore = store.restoreSession()
    store.logout()
    resolveMe(user)

    await expect(restore).resolves.toBe(false)
    expect(store.user).toBeNull()
    expect(tokenService.get()).toBeNull()
  })

  it('rejects a restore response when the stored token changes', async () => {
    let resolveMe: (value: AuthUser) => void = () => undefined
    const pendingMe = new Promise<AuthUser>((resolve) => {
      resolveMe = resolve
    })
    tokenService.set('restore-old-token', 1800)
    vi.spyOn(authApi, 'me').mockReturnValue(pendingMe)
    const store = useAuthStore()

    const restore = store.restoreSession()
    tokenService.set('restore-new-token', 1800)
    resolveMe(user)

    await expect(restore).resolves.toBe(false)
    expect(store.user).toBeNull()
    expect(tokenService.get()).toBe('restore-new-token')
  })

  it('keeps a newer login user when an older restore resolves later', async () => {
    const newerUser: AuthUser = {
      ...user,
      id: 'user-newer',
      username: 'newer.demo',
      displayName: '新的使用者',
    }
    let resolveOldRestore: (value: AuthUser) => void = () => undefined
    const oldRestore = new Promise<AuthUser>((resolve) => {
      resolveOldRestore = resolve
    })
    tokenService.set('restore-token', 1800)
    vi.spyOn(authApi, 'me').mockImplementationOnce(() => oldRestore).mockResolvedValueOnce(newerUser)
    vi.spyOn(authApi, 'login').mockResolvedValue(token)
    const store = useAuthStore()

    const restore = store.restoreSession()
    await store.login({ username: newerUser.username, password: 'not-recorded' })
    resolveOldRestore(user)

    await expect(restore).resolves.toBe(false)
    expect(store.user).toEqual(newerUser)
    expect(tokenService.get()).toBe(token.access_token)
  })

  it('adds the bearer token and clears auth on 401 without leaking backend details', async () => {
    tokenService.set('header-token', 1800)
    const reset = vi.fn()
    const unregister = registerUnauthorizedHandler(reset)
    const originalAdapter = http.defaults.adapter
    let requestHeaders: unknown
    http.defaults.adapter = vi.fn(async (config) => {
      requestHeaders = config.headers
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, undefined, {
        data: { detail: 'backend secret detail' },
        status: 401,
        statusText: 'Unauthorized',
        headers: {},
        config,
      })
    }) as unknown as typeof originalAdapter

    try {
      await expect(http.get('/auth/me')).rejects.toBeInstanceOf(AxiosError)
      const headers = requestHeaders as { Authorization?: string; get?: (name: string) => string | null }
      expect(headers.get?.('Authorization') ?? headers.Authorization).toBe('Bearer header-token')
      expect(tokenService.get()).toBeNull()
      expect(reset).toHaveBeenCalledOnce()
    } finally {
      http.defaults.adapter = originalAdapter
      unregister()
    }
  })

  it('does not clear a newer session when an older request returns 401', async () => {
    const oldToken = 'old-request-token'
    const newToken = 'new-session-token'
    tokenService.set(oldToken, 1800)
    const store = useAuthStore()
    store.user = user
    const reset = vi.fn()
    const unregister = registerUnauthorizedHandler(reset)
    const originalAdapter = http.defaults.adapter
    http.defaults.adapter = vi.fn(async (config) => {
      const requestHeaders = config.headers as { get?: (name: string) => string | null }
      expect(requestHeaders.get?.('Authorization')).toBe(`Bearer ${oldToken}`)
      tokenService.set(newToken, 1800)
      const failedConfig = {
        ...config,
        headers: { authorization: `bearer ${oldToken}` },
      } as typeof config
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', failedConfig, undefined, {
        data: { detail: 'stale token' },
        status: 401,
        statusText: 'Unauthorized',
        headers: {},
        config: failedConfig,
      })
    }) as unknown as typeof originalAdapter

    try {
      await expect(http.get('/auth/me')).rejects.toBeInstanceOf(AxiosError)
      expect(tokenService.get()).toBe(newToken)
      expect(store.user).toEqual(user)
      expect(reset).not.toHaveBeenCalled()
    } finally {
      http.defaults.adapter = originalAdapter
      unregister()
    }
  })

  it('does not clear a reissued same-token session when an older request returns 401', async () => {
    const reusedToken = 'reused-session-token'
    tokenService.set(reusedToken, 1800)
    const store = useAuthStore()
    store.user = user
    const reset = vi.fn()
    const unregister = registerUnauthorizedHandler(reset)
    const originalAdapter = http.defaults.adapter
    http.defaults.adapter = vi.fn(async (config) => {
      expect((config.headers as { get?: (name: string) => string | null }).get?.('Authorization')).toBe(
        `Bearer ${reusedToken}`,
      )
      tokenService.set(reusedToken, 1800)
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, undefined, {
        data: { detail: 'reissued token' },
        status: 401,
        statusText: 'Unauthorized',
        headers: {},
        config,
      })
    }) as unknown as typeof originalAdapter

    try {
      await expect(http.get('/auth/me')).rejects.toBeInstanceOf(AxiosError)
      expect(tokenService.get()).toBe(reusedToken)
      expect(store.user).toEqual(user)
      expect(reset).not.toHaveBeenCalled()
    } finally {
      http.defaults.adapter = originalAdapter
      unregister()
    }
  })

  it('maps a 403 transport response to a safe typed forbidden error', async () => {
    const originalAdapter = http.defaults.adapter
    http.defaults.adapter = vi.fn(async (config) => {
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, undefined, {
        data: { detail: 'internal permission detail' },
        status: 403,
        statusText: 'Forbidden',
        headers: {},
        config,
      })
    }) as unknown as typeof originalAdapter

    try {
      await expect(http.get('/restricted')).rejects.toBeInstanceOf(ForbiddenError)
    } finally {
      http.defaults.adapter = originalAdapter
    }
  })

  it('notifies every live auth store and unregisters a disposed store', async () => {
    const firstPinia = createPinia()
    setActivePinia(firstPinia)
    const first = useAuthStore()
    first.user = user

    const secondPinia = createPinia()
    setActivePinia(secondPinia)
    const second = useAuthStore()
    second.user = user
    tokenService.set('live-store-token', 1800)

    const originalAdapter = http.defaults.adapter
    http.defaults.adapter = vi.fn(async (config) => {
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, undefined, {
        data: { detail: 'backend detail' },
        status: 401,
        statusText: 'Unauthorized',
        headers: {},
        config,
      })
    }) as unknown as typeof originalAdapter

    try {
      await expect(http.get('/auth/me')).rejects.toBeInstanceOf(AxiosError)
      expect(first.user).toBeNull()
      expect(second.user).toBeNull()

      first.user = user
      second.user = user
      tokenService.set('live-store-token-2', 1800)
      first.$dispose()
      await expect(http.get('/auth/me')).rejects.toBeInstanceOf(AxiosError)
      expect(first.user).toEqual(user)
      expect(second.user).toBeNull()
    } finally {
      second.$dispose()
      http.defaults.adapter = originalAdapter
    }
  })
})
