import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

const ACCESS_TOKEN_KEY = 'lva-demo-access-token'
const TOKEN_EXPIRES_AT_KEY = 'lva-demo-token-expires-at'
let authGeneration = 0

function storage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.sessionStorage
}

export const tokenService = {
  get(): string | null {
    const store = storage()
    const token = store?.getItem(ACCESS_TOKEN_KEY) ?? null
    const expiresAt = store?.getItem(TOKEN_EXPIRES_AT_KEY)
    if (token && expiresAt && Date.now() >= Number(expiresAt)) {
      this.clear()
      return null
    }
    return token
  },

  generation(): number {
    return authGeneration
  },

  set(accessToken: string, expiresIn: number): void {
    const store = storage()
    if (!store) return
    authGeneration += 1
    store.setItem(ACCESS_TOKEN_KEY, accessToken)
    store.setItem(TOKEN_EXPIRES_AT_KEY, String(Date.now() + Math.max(0, expiresIn) * 1000))
  },

  clear(): void {
    const store = storage()
    authGeneration += 1
    store?.removeItem(ACCESS_TOKEN_KEY)
    store?.removeItem(TOKEN_EXPIRES_AT_KEY)
  },
}

export class ForbiddenError extends Error {
  readonly code = 'FORBIDDEN'

  constructor() {
    super('您沒有執行此操作的權限。')
    this.name = 'ForbiddenError'
  }
}

const unauthorizedHandlers = new Set<() => void>()

export function registerUnauthorizedHandler(handler: () => void): () => void {
  unauthorizedHandlers.add(handler)
  let disposed = false
  return () => {
    if (disposed) return
    disposed = true
    unauthorizedHandlers.delete(handler)
  }
}

function notifyUnauthorized(): void {
  for (const handler of [...unauthorizedHandlers]) {
    try {
      handler()
    } catch {
      // Auth reset must not mask the original HTTP error.
    }
  }
}

type AuthenticatedRequestConfig = InternalAxiosRequestConfig & {
  __lvaAuthGeneration?: number
  __lvaAuthToken?: string | null
}

function addBearerToken(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  const token = tokenService.get()
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  const authConfig = config as AuthenticatedRequestConfig
  authConfig.__lvaAuthGeneration = tokenService.generation()
  authConfig.__lvaAuthToken = token
  return config
}

function requestBearerToken(error: AxiosError): string | null {
  const headers = error.config?.headers
  if (!headers) return null

  let value: unknown
  if (typeof headers.get === 'function') {
    value = headers.get('Authorization') ?? headers.get('authorization')
  }
  if (value === undefined || value === null) {
    const record = headers as unknown as Record<string, unknown>
    value = record.Authorization ?? record.authorization
  }
  if (Array.isArray(value)) value = value[0]
  if (typeof value !== 'string') return null

  const match = /^\s*Bearer\s+(.+?)\s*$/i.exec(value)
  return match?.[1] ?? null
}

function mapAuthResponseError(error: AxiosError): Promise<never> {
  const status = error.response?.status
  const config = error.config as AuthenticatedRequestConfig | undefined
  const hasAuthContext = typeof config?.__lvaAuthGeneration === 'number'
  const failedToken = hasAuthContext ? config?.__lvaAuthToken ?? null : requestBearerToken(error)
  const failedGeneration = hasAuthContext ? config?.__lvaAuthGeneration : null
  const currentToken = tokenService.get()
  if (
    status === 401 &&
    failedToken &&
    failedGeneration !== null &&
    currentToken === failedToken &&
    tokenService.generation() === failedGeneration
  ) {
    tokenService.clear()
    notifyUnauthorized()
  }
  if (status === 403) return Promise.reject(new ForbiddenError())
  return Promise.reject(error)
}

export const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use(addBearerToken)
http.interceptors.response.use((response) => response, mapAuthResponseError)
