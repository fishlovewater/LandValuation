import { AxiosError } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ForbiddenError, http, tokenService } from '../../src/api/http'
import { authApi } from '../../src/modules/auth/auth.api'

const token = {
  access_token: 'adapter-token',
  token_type: 'bearer',
  expires_in: 1800,
}

const currentUser = {
  user_id: 'user-001',
  username: 'reviewer.demo',
  email: 'reviewer@example.test',
  display_name: '示範審查員',
  roles: ['REVIEWER'],
  permissions: ['review.execute'],
}

const originalAdapter = http.defaults.adapter
const originalBaseUrl = http.defaults.baseURL

afterEach(() => {
  http.defaults.adapter = originalAdapter
  http.defaults.baseURL = originalBaseUrl
  tokenService.clear()
  vi.restoreAllMocks()
})

describe('auth API adapter boundary', () => {
  it('posts account access requests to the self-service registration endpoint', async () => {
    http.defaults.baseURL = 'https://api.example.test/api/v1'
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: `${config.baseURL}${config.url}`, data: config.data })
      return {
        data: {
          request_id: 'request-001',
          status: 'PENDING',
          message: '帳號申請已送出。',
        },
        status: 201,
        statusText: 'Created',
        headers: {},
        config,
      }
    }) as unknown as typeof originalAdapter

    const received = await authApi.requestAccount({
      username: 'new.reviewer',
      email: 'new.reviewer@example.test',
      display_name: '新審查人員',
      requested_role: 'REVIEWER',
      reason: '案件審查工作',
    })

    expect(requests).toEqual([
      {
        method: 'post',
        url: 'https://api.example.test/api/v1/auth/registration-requests',
        data: JSON.stringify({
          username: 'new.reviewer',
          email: 'new.reviewer@example.test',
          display_name: '新審查人員',
          requested_role: 'REVIEWER',
          reason: '案件審查工作',
        }),
      },
    ])
    expect(received.status).toBe('PENDING')
  })

  it('uses the password-reset request and confirmation endpoints without adding auth headers', async () => {
    http.defaults.baseURL = 'https://api.example.test/api/v1'
    const requests: Array<{ method?: string; url?: string; data?: unknown; authorization?: string }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      const authorization = config.headers.get?.('Authorization') ?? config.headers.Authorization
      requests.push({ method: config.method, url: `${config.baseURL}${config.url}`, data: config.data, authorization })
      return {
        data: { message: 'ok' },
        status: config.url === '/auth/password-reset-requests' ? 202 : 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }) as unknown as typeof originalAdapter

    await authApi.requestPasswordReset('reviewer.demo')
    await authApi.confirmPasswordReset('reset-token-value', 'replacement-value-123')

    expect(requests).toEqual([
      {
        method: 'post',
        url: 'https://api.example.test/api/v1/auth/password-reset-requests',
        data: JSON.stringify({ account: 'reviewer.demo' }),
        authorization: undefined,
      },
      {
        method: 'post',
        url: 'https://api.example.test/api/v1/auth/password-reset-confirm',
        data: JSON.stringify({ token: 'reset-token-value', new_password: 'replacement-value-123' }),
        authorization: undefined,
      },
    ])
  })

  it('uses the development Demo login endpoint with only the selected role', async () => {
    http.defaults.baseURL = 'https://api.example.test/api/v1'
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({ method: config.method, url: `${config.baseURL}${config.url}`, data: config.data })
      return { data: token, status: 200, statusText: 'OK', headers: {}, config }
    }) as unknown as typeof originalAdapter

    const received = await authApi.demoLogin('REVIEWER')

    expect(requests).toEqual([
      {
        method: 'post',
        url: 'https://api.example.test/api/v1/auth/demo-login',
        data: JSON.stringify({ role: 'REVIEWER' }),
      },
    ])
    expect(received).toEqual(token)
  })

  it('uses the exact login then me paths and maps the verified DTOs', async () => {
    http.defaults.baseURL = 'https://api.example.test/api/v1'
    const requests: Array<{ method?: string; url?: string; data?: unknown; authorization?: string }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      const authorization = config.headers.get?.('Authorization') ?? config.headers.Authorization
      requests.push({ method: config.method, url: `${config.baseURL}${config.url}`, data: config.data, authorization })
      if (config.url === '/auth/login') {
        return { data: token, status: 200, statusText: 'OK', headers: {}, config }
      }
      return { data: currentUser, status: 200, statusText: 'OK', headers: {}, config }
    }) as unknown as typeof originalAdapter

    const receivedToken = await authApi.login({ username: 'reviewer.demo', password: 'not-recorded' })
    tokenService.set(receivedToken.access_token, receivedToken.expires_in)
    const receivedUser = await authApi.me()

    expect(requests).toEqual([
      {
        method: 'post',
        url: 'https://api.example.test/api/v1/auth/login',
        data: JSON.stringify({ username: 'reviewer.demo', password: 'not-recorded' }),
        authorization: undefined,
      },
      {
        method: 'get',
        url: 'https://api.example.test/api/v1/auth/me',
        data: undefined,
        authorization: 'Bearer adapter-token',
      },
    ])
    expect(receivedUser).toEqual({
      id: 'user-001',
      username: 'reviewer.demo',
      email: 'reviewer@example.test',
      displayName: '示範審查員',
      roles: ['REVIEWER'],
      permissions: ['review.execute'],
    })
  })

  it('clears a bearer token on 401 and maps 403 without exposing response detail', async () => {
    tokenService.set('temporary-token', 1800)
    http.defaults.adapter = vi.fn(async (config) => {
      const status = config.url === '/auth/me' ? 401 : 403
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, undefined, {
        data: { detail: 'internal permission detail' },
        status,
        statusText: status === 401 ? 'Unauthorized' : 'Forbidden',
        headers: {},
        config,
      })
    }) as unknown as typeof originalAdapter

    await expect(authApi.me()).rejects.toBeInstanceOf(AxiosError)
    expect(tokenService.get()).toBeNull()
    await expect(http.get('/restricted')).rejects.toBeInstanceOf(ForbiddenError)
    await expect(http.get('/restricted')).rejects.toMatchObject({ message: '您沒有執行此操作的權限。' })
  })
})
