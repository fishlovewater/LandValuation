type BuildEnvironment = {
  PROD: boolean
  DEV?: boolean
  MODE?: string
  VITE_USE_MOCK_API?: string
  VITE_DEMO_QUICK_LOGIN?: string
}

export function assertSafeBuildEnvironment(env: BuildEnvironment): void {
  if (env.PROD && env.VITE_USE_MOCK_API === 'true') {
    throw new Error('Production build cannot use mock API')
  }
}

export function isDemoQuickLoginEnabled(env: BuildEnvironment): boolean {
  return env.DEV === true || env.MODE === 'demo' || env.VITE_DEMO_QUICK_LOGIN === 'true'
}
