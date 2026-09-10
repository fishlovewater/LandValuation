type BuildEnvironment = {
  PROD: boolean
  VITE_USE_MOCK_API?: string
}

export function assertSafeBuildEnvironment(env: BuildEnvironment): void {
  if (env.PROD && env.VITE_USE_MOCK_API === 'true') {
    throw new Error('Production build cannot use mock API')
  }
}
