import { describe, expect, it } from 'vitest'
import { assertSafeBuildEnvironment, isDemoQuickLoginEnabled } from '../../src/config/environment'

describe('build environment', () => {
  it('rejects mock API in production', () => {
    expect(() =>
      assertSafeBuildEnvironment({ PROD: true, VITE_USE_MOCK_API: 'true' }),
    ).toThrow('Production build cannot use mock API')
  })

  it('allows mock API in development', () => {
    expect(() =>
      assertSafeBuildEnvironment({ PROD: false, VITE_USE_MOCK_API: 'true' }),
    ).not.toThrow()
  })

  it('allows the real API in production', () => {
    expect(() =>
      assertSafeBuildEnvironment({ PROD: true, VITE_USE_MOCK_API: 'false' }),
    ).not.toThrow()
  })

  it('enables Demo quick login only for development, demo mode, or an explicit opt-in', () => {
    expect(isDemoQuickLoginEnabled({ PROD: false, DEV: true, MODE: 'development' })).toBe(true)
    expect(isDemoQuickLoginEnabled({ PROD: true, DEV: false, MODE: 'demo' })).toBe(true)
    expect(isDemoQuickLoginEnabled({ PROD: true, DEV: false, MODE: 'production', VITE_DEMO_QUICK_LOGIN: 'true' })).toBe(true)
    expect(isDemoQuickLoginEnabled({ PROD: true, DEV: false, MODE: 'production', VITE_DEMO_QUICK_LOGIN: 'false' })).toBe(false)
  })
})
