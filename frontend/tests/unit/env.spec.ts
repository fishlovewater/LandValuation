import { describe, expect, it } from 'vitest'
import { assertSafeBuildEnvironment } from '../../src/config/environment'

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
})
