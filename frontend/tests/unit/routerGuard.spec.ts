import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '../../src/modules/auth/auth.api'
import type { AuthUser } from '../../src/modules/auth/auth.types'
import { createAppRouter } from '../../src/router'
import { HISTORY_ROLES, homeFor } from '../../src/router/roleHomeMap'
import { safeAppRedirect } from '../../src/router/redirects'
import { tokenService } from '../../src/api/http'
import { useAuthStore } from '../../src/stores/auth.store'

const appraiser: AuthUser = {
  id: 'user-appraiser',
  username: 'appraiser.demo',
  email: 'appraiser@example.test',
  displayName: '示範估價人員',
  roles: ['APPRAISER'],
  permissions: [
    'assistant.use',
    'case.read',
    'knowledge.read',
    'valuation.read',
    'valuation.update',
  ],
}

const reviewer: AuthUser = {
  id: 'user-reviewer',
  username: 'reviewer.demo',
  email: 'reviewer@example.test',
  displayName: '示範審查員',
  roles: ['REVIEWER'],
  permissions: ['case.read', 'review.execute'],
}

function authenticatedUser(user: AuthUser): void {
  const store = useAuthStore()
  store.user = user
  tokenService.set('guard-token', 1800)
}

describe('router guards', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    tokenService.clear()
    vi.restoreAllMocks()
  })

  it('preserves the destination when an unauthenticated user enters a protected route', async () => {
    const router = createAppRouter()

    await router.push('/app/review/workbench?status=ready')

    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.query.redirect).toBe('/app/review/workbench?status=ready')
  })

  it('logs out and redirects to the public landing page when the token has expired', async () => {
    const store = useAuthStore()
    store.user = appraiser
    tokenService.set('expired-token', -1)
    const router = createAppRouter()

    await router.push('/app/valuation/dashboard')

    expect(store.user).toBeNull()
    expect(tokenService.get()).toBeNull()
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('sends an authenticated user from the landing page to the role home', async () => {
    authenticatedUser(reviewer)
    const router = createAppRouter()

    await router.push('/')

    expect(router.currentRoute.value.path).toBe('/app/review/dashboard')
  })

  it('redirects an authenticated user away from a route missing its permission', async () => {
    authenticatedUser(appraiser)
    const router = createAppRouter()

    await router.push('/app/review/dashboard')

    expect(router.currentRoute.value.path).toBe('/app/unauthorized')
  })

  it('keeps the Review workspace reviewer-only even if an appraiser is granted review.execute', async () => {
    authenticatedUser({
      ...appraiser,
      permissions: [...appraiser.permissions, 'review.execute'],
    })
    const appraiserRouter = createAppRouter()
    await appraiserRouter.push('/app/review/dashboard')
    expect(appraiserRouter.currentRoute.value.path).toBe('/app/unauthorized')

    authenticatedUser(reviewer)
    const reviewerRouter = createAppRouter()
    await reviewerRouter.push('/app/review/dashboard')
    expect(reviewerRouter.currentRoute.value.path).toBe('/app/review/dashboard')
  })

  it('uses assistant.use, not a role name or valuation.update, for Assistant route entry', async () => {
    authenticatedUser({
      ...appraiser,
      roles: ['REVIEWER'],
      permissions: ['assistant.use'],
    })
    const allowedRouter = createAppRouter()
    await allowedRouter.push('/app/assistant')
    expect(allowedRouter.currentRoute.value.path).toBe('/app/assistant')

    authenticatedUser({
      ...appraiser,
      roles: ['APPRAISER'],
      permissions: ['valuation.update'],
    })
    const deniedRouter = createAppRouter()
    await deniedRouter.push('/app/assistant')
    expect(deniedRouter.currentRoute.value.path).toBe('/app/unauthorized')
  })

  it('allows a custom role onto a permission-authorized route while keeping its default home fail-closed', async () => {
    authenticatedUser({
      ...appraiser,
      roles: ['CUSTOM_APPRAISER'],
      permissions: ['assistant.use'],
    })
    const featureRouter = createAppRouter()
    await featureRouter.push('/app/assistant')
    expect(featureRouter.currentRoute.value.path).toBe('/app/assistant')

    const homeRouter = createAppRouter()
    await homeRouter.push('/app')
    expect(homeRouter.currentRoute.value.path).toBe('/app/unauthorized')
  })

  it('does not grant Assistant entry to a role that lacks assistant.use', async () => {
    authenticatedUser({
      ...appraiser,
      roles: ['APPRAISER'],
      permissions: ['valuation.read', 'case.read', 'knowledge.read'],
    })
    const router = createAppRouter()

    await router.push('/app/assistant')

    expect(router.currentRoute.value.path).toBe('/app/unauthorized')
  })

  it('requires case.read in addition to valuation permissions for Valuation list and detail routes', async () => {
    authenticatedUser({
      ...appraiser,
      permissions: ['valuation.read', 'valuation.update', 'valuation.submit_review', 'document.download'],
    })
    const listRouter = createAppRouter()
    await listRouter.push('/app/valuation/dashboard')
    expect(listRouter.currentRoute.value.path).toBe('/app/unauthorized')

    authenticatedUser({ ...appraiser, permissions: ['case.read', 'valuation.read'] })
    const prepareRouter = createAppRouter()
    await prepareRouter.push('/app/valuation/cases/case-a/prepare')
    expect(prepareRouter.currentRoute.value.path).toBe('/app/unauthorized')

    authenticatedUser({
      ...appraiser,
      permissions: ['case.read', 'valuation.submit_review', 'valuation.update', 'document.download'],
    })
    const submitRouter = createAppRouter()
    await submitRouter.push('/app/valuation/cases/case-a/submit')
    expect(submitRouter.currentRoute.value.path).toBe('/app/unauthorized')

    authenticatedUser({
      ...appraiser,
      permissions: ['case.read', 'valuation.read', 'valuation.submit_review', 'valuation.update', 'document.download'],
    })
    const allowedSubmitRouter = createAppRouter()
    await allowedSubmitRouter.push('/app/valuation/cases/case-a/submit')
    expect(allowedSubmitRouter.currentRoute.value.path).toBe('/app/valuation/cases/case-a/submit')
  })

  it('keeps the interactive Valuation workspace appraiser-only even when review/history roles have valuation evidence permissions', async () => {
    authenticatedUser({
      ...reviewer,
      permissions: ['case.read', 'valuation.read', 'valuation.update', 'valuation.submit_review', 'document.download'],
    })
    const reviewerRouter = createAppRouter()
    await reviewerRouter.push('/app/valuation/dashboard')
    expect(reviewerRouter.currentRoute.value.path).toBe('/app/unauthorized')

    authenticatedUser({
      ...appraiser,
      roles: ['INSPECTOR'],
      permissions: ['case.read', 'valuation.read', 'valuation.update', 'valuation.submit_review', 'document.download'],
    })
    const inspectorRouter = createAppRouter()
    await inspectorRouter.push('/app/valuation/cases/case-a/prepare')
    expect(inspectorRouter.currentRoute.value.path).toBe('/app/unauthorized')
  })

  it('allows History for its verified roles without requiring an invented permission', async () => {
    authenticatedUser({
      ...appraiser,
      roles: ['INSPECTOR'],
      permissions: [],
    })
    const router = createAppRouter()

    await router.push('/app/history/search')

    expect(router.currentRoute.value.path).toBe('/app/history/search')
  })

  it('fails closed for a role outside the verified History contract', async () => {
    authenticatedUser({
      ...appraiser,
      roles: ['SUPERVISOR'],
      permissions: ['case.read'],
    })
    const router = createAppRouter()

    await router.push('/app/history/search')

    expect(router.currentRoute.value.path).toBe('/app/unauthorized')
  })

  it('hydrates a token-backed session before rendering a protected view', async () => {
    tokenService.set('restore-token', 1800)
    vi.spyOn(authApi, 'me').mockResolvedValue(appraiser)
    const router = createAppRouter()

    await router.push('/app/valuation/dashboard')

    expect(authApi.me).toHaveBeenCalledOnce()
    expect(useAuthStore().user).toEqual(appraiser)
    expect(router.currentRoute.value.path).toBe('/app/valuation/dashboard')
  })

  it('maps every verified role and fails closed for an unknown role', () => {
    expect(homeFor({ roles: ['APPRAISER'] })).toBe('/app/valuation/dashboard')
    expect(homeFor({ roles: ['REVIEWER'] })).toBe('/app/review/dashboard')
    expect(homeFor({ roles: ['INSPECTOR'] })).toBe('/app/history/search')
    expect(homeFor({ roles: ['SUPERVISOR'] })).toBe('/app/unauthorized')
    expect(homeFor({ roles: ['ADMIN'] })).toBe('/app')
    expect(homeFor({ roles: ['SYSTEM_ADMIN'] })).toBe('/app')
    expect(homeFor({ roles: ['SUPERADMIN'] })).toBe('/app')
    expect(homeFor({ roles: ['UNRECOGNIZED'] })).toBe('/app/unauthorized')
    expect(HISTORY_ROLES).toEqual([
      'APPRAISER',
      'REVIEWER',
      'INSPECTOR',
      'ADMIN',
      'SYSTEM_ADMIN',
      'SUPERADMIN',
    ])
  })

  it('rejects dot-segment and encoded separator login redirects', () => {
    expect(safeAppRedirect('/app/review/workbench?status=ready#finding')).toBe(
      '/app/review/workbench?status=ready#finding',
    )
    for (const redirect of [
      '/app/../privacy',
      '/app/%2e%2e/privacy',
      '/app/%252e%252e/privacy',
      '/app/%2f%2fevil.example',
      '/app/%5c%5cevil.example',
      '/app//review/workbench',
      '/app/%252f%252fevil.example',
      '/app/%252F%252Fevil.example',
      '/app/..%2fprivacy',
      '/app\\..\\privacy',
    ]) {
      expect(safeAppRedirect(redirect)).toBeNull()
    }
    expect(safeAppRedirect('/app/review/workbench?next=%252f%252fevil.example#finding')).toBe(
      '/app/review/workbench?next=%252f%252fevil.example#finding',
    )
  })
})
