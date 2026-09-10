import type { Page, Request, Response, TestInfo } from '@playwright/test'

const DEFAULT_API_BASE_URL = 'http://localhost:8000/api/v1'
const DEFAULT_APP_ORIGIN = 'http://127.0.0.1:5173'
const TOKEN_STORAGE_KEY = 'lva-demo-access-token'
const AUTH_ENDPOINTS: ReadonlyMap<string, DiagnosticEndpoint> = new Map([
  ['/auth/login', 'LOGIN'],
  ['/auth/me', 'ME'],
] as const)

export type DiagnosticEndpoint = 'LOGIN' | 'ME'
export type DiagnosticPhase = 'REQUEST' | 'RESPONSE' | 'FAILED'
export type DiagnosticPage = 'PUBLIC' | 'APP' | 'OTHER'

export type LoginBoundaryEvent = {
  endpoint: DiagnosticEndpoint
  phase: DiagnosticPhase
  status?: number
}

export type LoginDiagnosticSnapshot = {
  schemaVersion: 1
  events: LoginBoundaryEvent[]
  page: DiagnosticPage
  alertPresent: boolean
  loginButtonDisabled: boolean
  tokenPresent: boolean
}

export type LoginBoundaryDiagnosticsOptions = {
  apiBaseUrl?: string
  appOrigin?: string
}

function normalizePath(value: string): string {
  return value.replace(/\/+$/, '') || '/'
}

function endpointFor(value: string, apiBaseUrl: string): DiagnosticEndpoint | null {
  try {
    const base = new URL(apiBaseUrl)
    const request = new URL(value)
    if (request.origin !== base.origin) return null

    const basePath = normalizePath(base.pathname)
    const requestPath = normalizePath(request.pathname)
    const suffix = basePath === '/'
      ? requestPath
      : requestPath.startsWith(`${basePath}/`)
        ? requestPath.slice(basePath.length)
        : ''
    return AUTH_ENDPOINTS.get(suffix) ?? null
  } catch {
    return null
  }
}

function httpStatus(value: number): number | undefined {
  return Number.isInteger(value) && value >= 100 && value <= 599 ? value : undefined
}

function pageKind(value: string, appOrigin: string): DiagnosticPage {
  try {
    const parsed = new URL(value)
    if (parsed.origin !== new URL(appOrigin).origin) return 'OTHER'
    const pathname = parsed.pathname.replace(/\/+$/, '') || '/'
    if (pathname === '/') return 'PUBLIC'
    if (pathname === '/app' || pathname.startsWith('/app/')) return 'APP'
  } catch {
    return 'OTHER'
  }
  return 'OTHER'
}

async function tokenIsPresent(page: Page): Promise<boolean> {
  try {
    return Boolean(await page.evaluate(() => Boolean(window.sessionStorage.getItem(TOKEN_STORAGE_KEY))))
  } catch {
    return false
  }
}

async function failureState(page: Page, appOrigin: string): Promise<Pick<LoginDiagnosticSnapshot, 'page' | 'alertPresent' | 'loginButtonDisabled' | 'tokenPresent'>> {
  let currentPage: DiagnosticPage = 'OTHER'
  try {
    currentPage = pageKind(page.url(), appOrigin)
  } catch {
    // Keep the enum boundary fail-closed when the page is already closing.
  }

  const alert = page.getByRole('alert').first()
  const loginButton = page.locator('button.login-submit').first()
  const [alertPresent, loginButtonDisabled, tokenPresent] = await Promise.all([
    alert.isVisible({ timeout: 0 }).then(Boolean).catch(() => false),
    loginButton.isDisabled({ timeout: 0 }).then(Boolean).catch(() => false),
    tokenIsPresent(page),
  ])
  return { page: currentPage, alertPresent, loginButtonDisabled, tokenPresent }
}

export function createLoginBoundaryDiagnostics(page: Page, options: LoginBoundaryDiagnosticsOptions = {}): {
  attach(): void
  detach(): void
  snapshot(): LoginDiagnosticSnapshot
  failureSnapshot(): Promise<LoginDiagnosticSnapshot>
} {
  const apiBaseUrl = options.apiBaseUrl ?? DEFAULT_API_BASE_URL
  const appOrigin = options.appOrigin ?? DEFAULT_APP_ORIGIN
  const events: LoginBoundaryEvent[] = []
  let attached = false

  function capture(request: Request, phase: DiagnosticPhase, status?: number): void {
    const endpoint = endpointFor(request.url(), apiBaseUrl)
    if (!endpoint) return
    const event: LoginBoundaryEvent = { endpoint, phase }
    if (phase === 'RESPONSE') {
      const safeStatus = httpStatus(status ?? NaN)
      if (safeStatus !== undefined) event.status = safeStatus
    }
    events.push(event)
  }

  function onRequest(request: Request): void {
    capture(request, 'REQUEST')
  }

  function onResponse(response: Response): void {
    capture(response.request(), 'RESPONSE', response.status())
  }

  function onRequestFailed(request: Request): void {
    capture(request, 'FAILED')
  }

  const listeners: Array<[string, (...args: never[]) => void]> = [
    ['request', onRequest as (...args: never[]) => void],
    ['response', onResponse as (...args: never[]) => void],
    ['requestfailed', onRequestFailed as (...args: never[]) => void],
  ]
  const attachedListeners: Array<[string, (...args: never[]) => void]> = []

  function attach(): void {
    if (attached) return
    try {
      for (const [event, listener] of listeners) {
        page.on(event as never, listener as never)
        attachedListeners.push([event, listener])
      }
      attached = true
    } catch (error: unknown) {
      for (const [event, listener] of attachedListeners.reverse()) page.off(event as never, listener as never)
      attachedListeners.length = 0
      throw error
    }
  }

  function detach(): void {
    if (!attached) return
    attached = false
    for (const [event, listener] of attachedListeners.splice(0)) page.off(event as never, listener as never)
  }

  function snapshot(): LoginDiagnosticSnapshot {
    let currentPage: DiagnosticPage = 'OTHER'
    try {
      currentPage = pageKind(page.url(), appOrigin)
    } catch {
      // Keep the enum boundary fail-closed when the page is already closing.
    }
    return {
      schemaVersion: 1,
      events: events.map((event) => ({ ...event })),
      page: currentPage,
      alertPresent: false,
      loginButtonDisabled: false,
      tokenPresent: false,
    }
  }

  async function failureSnapshot(): Promise<LoginDiagnosticSnapshot> {
    return { ...snapshot(), ...(await failureState(page, appOrigin)) }
  }

  return { attach, detach, snapshot, failureSnapshot }
}

export async function attachLoginFailureDiagnostics(
  testInfo: TestInfo,
  diagnostics: ReturnType<typeof createLoginBoundaryDiagnostics>,
): Promise<void> {
  try {
    const body = JSON.stringify(await diagnostics.failureSnapshot())
    await testInfo.attach('login-boundary-diagnostics', {
      body,
      contentType: 'application/json',
    })
  } catch {
    // Preserve the original login failure if the JSON handoff cannot complete.
  }
}

export type DemoRole = 'APPRAISER' | 'REVIEWER' | 'INSPECTOR'

export type LoginCredentials = {
  username: string
  password: string
}

export async function loginAs(
  page: Page,
  _role: DemoRole,
  credentials: LoginCredentials,
  testInfo: TestInfo,
  options: LoginBoundaryDiagnosticsOptions = {},
): Promise<void> {
  const diagnostics = createLoginBoundaryDiagnostics(page, options)
  try {
    diagnostics.attach()
    await page.goto('/')
    await page.locator('#login-username').fill(credentials.username)
    await page.locator('#login-password').fill(credentials.password)
    await Promise.all([
      page.waitForURL(/\/app\//),
      page.getByRole('button', { name: '登入工作台' }).click(),
    ])
  } catch (error: unknown) {
    await attachLoginFailureDiagnostics(testInfo, diagnostics)
    throw error
  } finally {
    diagnostics.detach()
  }
}
