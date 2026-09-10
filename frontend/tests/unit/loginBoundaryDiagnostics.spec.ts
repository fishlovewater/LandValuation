import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import {
  attachLoginFailureDiagnostics,
  createLoginBoundaryDiagnostics,
  loginAs,
} from '../e2e/login-boundary-diagnostics'

const frontendDirectory = resolve(import.meta.dirname, '../..')
const helperPath = resolve(frontendDirectory, 'tests/e2e/login-boundary-diagnostics.ts')
const flowPath = resolve(frontendDirectory, 'tests/e2e/demo-flow.spec.ts')
const playwrightConfigPath = resolve(frontendDirectory, 'playwright.config.ts')
const frontendIgnorePath = resolve(frontendDirectory, '.gitignore')
const runbookPath = resolve(frontendDirectory, 'docs/demo-runbook.md')

type Handler = (value?: unknown) => void

function makeDiagnosticsPage(url = 'http://127.0.0.1:5173/app/valuation/dashboard?token=hostile') {
  const handlers = new Map<string, Handler[]>()
  const alert = {
    isVisible: vi.fn().mockResolvedValue(true),
    textContent: vi.fn(() => { throw new Error('diagnostics must not read alert text') }),
  }
  const loginButton = {
    isDisabled: vi.fn().mockResolvedValue(true),
  }
  const page = {
    on: vi.fn((event: string, handler: Handler) => {
      handlers.set(event, [...(handlers.get(event) ?? []), handler])
    }),
    off: vi.fn((event: string, handler: Handler) => {
      handlers.set(event, (handlers.get(event) ?? []).filter((candidate) => candidate !== handler))
    }),
    url: vi.fn(() => url),
    evaluate: vi.fn().mockResolvedValue(true),
    getByRole: vi.fn(() => ({ first: () => alert })),
    locator: vi.fn(() => ({ first: () => loginButton })),
  }
  const emit = (event: string, value: unknown): void => {
    for (const handler of handlers.get(event) ?? []) handler(value)
  }
  return { page, alert, loginButton, emit }
}

function request(url: string, method = 'POST'): Record<string, unknown> {
  return {
    method: () => method,
    url: () => url,
    headers: () => ({ authorization: 'Bearer hostile-token' }),
    postData: () => 'password=hostile-password',
    body: () => Buffer.from('hostile-body'),
  }
}

function response(requestValue: Record<string, unknown>, status: number): Record<string, unknown> {
  return {
    request: () => requestValue,
    status: () => status,
    headers: () => ({ 'x-request-id': 'hostile-request-id' }),
    text: () => Promise.resolve('hostile-response-body'),
    body: () => Promise.resolve(Buffer.from('hostile-response-body')),
  }
}

function makeLoginPage(events: string[], failWith?: Error) {
  const page = {
    on: vi.fn((event: string) => events.push(`on:${event}`)),
    off: vi.fn((event: string) => events.push(`off:${event}`)),
    goto: vi.fn(async () => { events.push('goto') }),
    waitForURL: vi.fn(async () => {
      events.push('waitForURL')
      if (failWith) throw failWith
    }),
    getByRole: vi.fn((role: string) => role === 'alert'
      ? { first: () => ({ isVisible: vi.fn().mockResolvedValue(false) }) }
      : { click: vi.fn(async () => { events.push('click') }) }),
    locator: vi.fn((selector: string) => selector === 'button.login-submit'
      ? { first: () => ({ isDisabled: vi.fn().mockResolvedValue(false) }) }
      : { fill: vi.fn(async (value: string) => { events.push(`fill:${value}`) }) }),
    url: vi.fn(() => 'http://127.0.0.1:5173/'),
    evaluate: vi.fn().mockResolvedValue(false),
  }
  return page
}

describe('hackathon-minimal structured login diagnostics', () => {
  it('serializes exactly the fixed schema and never copies hostile input', async () => {
    const hostile = 'password=hostile-password&access_token=hostile-token'
    const { page, alert, emit } = makeDiagnosticsPage()
    const diagnostics = createLoginBoundaryDiagnostics(page as never, {
      apiBaseUrl: 'http://localhost:8000/api/v1',
    })

    diagnostics.attach()
    emit('request', request(`http://localhost:8000/api/v1/auth/login?${hostile}`))
    emit('response', response(request(`http://localhost:8000/api/v1/auth/me?${hostile}`), 401))
    emit('requestfailed', request('http://localhost:8000/api/v1/auth/me', 'GET'))
    emit('request', request('http://localhost:8000/api/v1/auth/login-extra', 'POST'))

    const payload = await diagnostics.failureSnapshot()
    expect(Object.keys(payload).sort()).toEqual([
      'alertPresent',
      'events',
      'loginButtonDisabled',
      'page',
      'schemaVersion',
      'tokenPresent',
    ])
    expect(payload).toEqual({
      schemaVersion: 1,
      events: [
        { endpoint: 'LOGIN', phase: 'REQUEST' },
        { endpoint: 'ME', phase: 'RESPONSE', status: 401 },
        { endpoint: 'ME', phase: 'FAILED' },
      ],
      page: 'APP',
      alertPresent: true,
      loginButtonDisabled: true,
      tokenPresent: true,
    })
    for (const event of payload.events) {
      expect(['LOGIN', 'ME']).toContain(event.endpoint)
      expect(['REQUEST', 'RESPONSE', 'FAILED']).toContain(event.phase)
      if ('status' in event) {
        expect(event.phase).toBe('RESPONSE')
        expect(Number.isInteger(event.status)).toBe(true)
        expect(event.status).toBeGreaterThanOrEqual(100)
        expect(event.status).toBeLessThanOrEqual(599)
      }
    }
    expect(alert.textContent).not.toHaveBeenCalled()
    expect(JSON.stringify(payload)).not.toContain(hostile)
    expect(JSON.stringify(payload)).not.toContain('hostile-request-id')
    expect(JSON.stringify(payload)).not.toContain('hostile-response-body')
  })

  it('uses only in-memory page classification and boolean UI state', async () => {
    const { page } = makeDiagnosticsPage('http://evil.test/?password=hostile')
    const diagnostics = createLoginBoundaryDiagnostics(page as never)

    const payload = await diagnostics.failureSnapshot()

    expect(payload.page).toBe('OTHER')
    expect(typeof payload.alertPresent).toBe('boolean')
    expect(typeof payload.loginButtonDisabled).toBe('boolean')
    expect(typeof payload.tokenPresent).toBe('boolean')
    expect(JSON.stringify(payload)).not.toContain('http://')
    expect(JSON.stringify(payload)).not.toContain('password')
  })

  it('keeps event order in the array and attaches only auth listeners', () => {
    const { page } = makeDiagnosticsPage()
    const diagnostics = createLoginBoundaryDiagnostics(page as never)

    diagnostics.attach()

    expect(page.on.mock.calls.map(([event]) => event)).toEqual([
      'request',
      'response',
      'requestfailed',
    ])
  })

  it('attaches before the first login action and detaches after success', async () => {
    const events: string[] = []
    const page = makeLoginPage(events)

    await loginAs(
      page as never,
      'APPRAISER',
      { username: 'hostile-user', password: 'hostile-password' },
      { attach: vi.fn() } as never,
      { apiBaseUrl: 'http://localhost:8000/api/v1' },
    )

    expect(events.findIndex((event) => event === 'on:request')).toBeLessThan(events.indexOf('goto'))
    expect(events.findIndex((event) => event.startsWith('off:'))).toBeGreaterThan(events.indexOf('click'))
    expect(events.filter((event) => event.startsWith('on:'))).toHaveLength(3)
    expect(events.filter((event) => event.startsWith('off:'))).toHaveLength(3)
  })

  it('preserves the original login failure when JSON handoff fails and always detaches', async () => {
    const originalError = new Error('waitForURL timeout; hostile-password')
    const events: string[] = []
    const page = makeLoginPage(events, originalError)
    const attach = vi.fn(async () => { throw new Error('artifact write failed') })

    await expect(loginAs(
      page as never,
      'APPRAISER',
      { username: 'hostile-user', password: 'hostile-password' },
      { attach } as never,
      { apiBaseUrl: 'http://localhost:8000/api/v1' },
    )).rejects.toBe(originalError)
    expect(attach).toHaveBeenCalledOnce()
    expect(events.filter((event) => event.startsWith('off:'))).toHaveLength(3)
  })

  it('hands off the exact structured JSON before finally detaches', async () => {
    const events: string[] = []
    const page = makeLoginPage(events, new Error('login failed'))
    const attach = vi.fn(async (_name: string, attachment: { body: string; contentType: string }) => {
      events.push('handoff')
      expect(attachment.contentType).toBe('application/json')
      const payload = JSON.parse(attachment.body) as Record<string, unknown>
      expect(Object.keys(payload).sort()).toEqual([
        'alertPresent',
        'events',
        'loginButtonDisabled',
        'page',
        'schemaVersion',
        'tokenPresent',
      ])
    })

    await expect(loginAs(
      page as never,
      'APPRAISER',
      { username: 'hostile-user', password: 'hostile-password' },
      { attach } as never,
      { apiBaseUrl: 'http://localhost:8000/api/v1' },
    )).rejects.toThrow('login failed')

    expect(events.indexOf('handoff')).toBeGreaterThanOrEqual(0)
    expect(events.indexOf('handoff')).toBeLessThan(events.findIndex((event) => event.startsWith('off:')))
  })

  it('keeps the existing login matcher, timeout, retry and trace boundaries', () => {
    const flow = readFileSync(flowPath, 'utf8')
    const config = readFileSync(playwrightConfigPath, 'utf8')
    const helper = readFileSync(helperPath, 'utf8')

    expect(helper).toContain('page.waitForURL(/\\/app\\//)')
    expect(flow).not.toContain('page.waitForTimeout')
    expect(flow).not.toContain('timeout:')
    expect(flow).not.toContain('retry')
    expect(config).toContain("retries: process.env.CI ? 2 : 0")
    expect(config).toContain("trace: 'off'")
    expect(helper).not.toContain("['console'")
    expect(helper).not.toContain("['pageerror'")
    expect(helper).not.toContain("['framenavigated'")
    expect(helper).not.toContain('textContent')
    expect(helper).not.toContain('sensitiveValues')
  })

  it('keeps runtime artifact directories ignored after sanitized handoff cleanup', () => {
    const frontendIgnore = readFileSync(frontendIgnorePath, 'utf8')
    const runbook = readFileSync(runbookPath, 'utf8')

    expect(frontendIgnore).toContain('test-results/')
    expect(frontendIgnore).toContain('playwright-report/')
    expect(runbook).toContain('sanitized JSON')
    expect(runbook).toContain('durable handoff')
    expect(runbook).toContain('frontend/test-results/')
    expect(runbook).toContain('frontend/playwright-report/')
    expect(runbook).toContain('after the durable handoff')
  })

  it('does not pass login credentials into the diagnostics options', () => {
    const helper = readFileSync(helperPath, 'utf8')
    const createCall = helper.slice(helper.indexOf('const diagnostics ='), helper.indexOf('try {', helper.indexOf('const diagnostics =')))

    expect(createCall).not.toContain('credentials.username')
    expect(createCall).not.toContain('credentials.password')
    expect(createCall).not.toContain('sensitiveValues')
  })

  it('swallows a standalone attachment error without changing the structured contract', async () => {
    const { page } = makeDiagnosticsPage()
    const diagnostics = createLoginBoundaryDiagnostics(page as never)
    const attach = vi.fn(async () => { throw new Error('handoff unavailable') })

    await expect(attachLoginFailureDiagnostics({ attach } as never, diagnostics)).resolves.toBeUndefined()
    expect(attach).toHaveBeenCalledOnce()
  })
})
