import { expect, test, type Page } from '@playwright/test'

const APP_USER = {
  user_id: 'responsive-user',
  username: 'responsive.user',
  email: 'responsive.user@local.invalid',
  display_name: 'Responsive Demo User',
  roles: ['APPRAISER'],
  permissions: [
    'case.read',
    'valuation.read',
    'assistant.use',
    'knowledge.read',
  ],
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
  }))

  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
  expect(dimensions.bodyWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
}

async function mockAuthenticatedApp(page: Page): Promise<void> {
  await page.route('**/auth/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(APP_USER) }),
  )
  await page.addInitScript(() => {
    sessionStorage.setItem('lva-demo-access-token', 'responsive-test-token')
    sessionStorage.setItem('lva-demo-token-expires-at', String(Date.now() + 1_800_000))
  })
}

async function mockAssistantSession(page: Page): Promise<void> {
  const session = {
    assistant_session_id: 'responsive-assistant-session',
    case_id: 'responsive-case',
    user_id: APP_USER.user_id,
    form_instance_id: 'responsive-f03',
    current_step: 'COLLECTING',
    selected_form_type: 'F03',
    missing_fields: [],
    missing_documents: [],
    last_tool_name: null,
    last_tool_status: null,
    provider: 'evidence_only',
    model_id: 'responsive-test-model',
    prompt_version: 'responsive-test-prompt',
    session_status: 'ACTIVE',
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
  }
  await page.route('**/ai-assistant/sessions', (route) =>
    route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(session) }),
  )
  await page.route('**/ai-assistant/sessions/*', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) }),
  )
}

test.describe('responsive and accessibility coverage (mocked API)', () => {
  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
  ]) {
    test(`desktop ${viewport.width}x${viewport.height} keeps login usable`, async ({ page }) => {
      await page.setViewportSize(viewport)
      await page.goto('/')

      await expect(page.locator('.login-card')).toBeVisible()
      await expect(page.getByRole('button', { name: '登入工作台' })).toBeVisible()
      await assertNoHorizontalOverflow(page)
    })
  }

  test('mobile login remains usable when Liquid Glass is unavailable', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.route('**/vendor/liquid-glass/liquid-glass.js', (route) => route.abort())
    await page.goto('/')

    await expect(page.locator('.login-card')).toBeVisible()
    await page.getByRole('button', { name: '前往登入' }).click()
    await expect(page.locator('#login-username')).toBeFocused()
    await assertNoHorizontalOverflow(page)
  })

  test('mobile authenticated shell gives desktop guidance for complex work', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await mockAuthenticatedApp(page)
    await page.goto('/app/history/search')

    await expect(page.getByTestId('complex-work-guidance')).toBeVisible()
    await assertNoHorizontalOverflow(page)
  })

  test('reduced motion disables the login spinner animation', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.route('**/auth/login', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 250))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: 'responsive-test-token', token_type: 'bearer', expires_in: 1800 }),
      })
    })
    await page.route('**/auth/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(APP_USER) }),
    )
    await page.goto('/')
    await page.locator('#login-username').fill('responsive.user')
    await page.locator('#login-password').fill('not-a-secret')
    await page.getByRole('button', { name: '登入工作台' }).click()

    const animationDuration = await page.locator('.login-submit__spinner').evaluate(
      (element) => getComputedStyle(element).animationDuration,
    )
    expect(Number.parseFloat(animationDuration)).toBeLessThan(0.01)
  })

  test('tablet sidebar is a focusable drawer with an escape path', async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 768 })
    await mockAuthenticatedApp(page)
    await page.goto('/app/history/search')

    const trigger = page.locator('#app-sidebar-trigger')
    await trigger.click()
    const sidebar = page.locator('#app-sidebar')
    await expect(sidebar).toHaveAttribute('role', 'dialog')
    await expect(sidebar).toHaveAttribute('aria-modal', 'true')
    await expect(sidebar.locator('a, button').first()).toBeFocused()

    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
  })

  test('Assistant citation drawer exposes truthful focus and ARIA state', async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 768 })
    await mockAuthenticatedApp(page)
    await mockAssistantSession(page)
    await page.goto('/app/assistant?caseId=responsive-case&formId=responsive-f03')

    const trigger = page.getByTestId('assistant-open-drawer')
    await expect(trigger).toHaveAttribute('aria-controls', 'assistant-drawer')
    await expect(trigger).toHaveAttribute('aria-expanded', 'false')
    await trigger.click()

    const drawer = page.getByRole('dialog', { name: '智能助理' })
    await expect(drawer).toBeVisible()
    await expect(trigger).toHaveAttribute('aria-expanded', 'true')
    await expect(drawer.getByRole('button', { name: '關閉' })).toBeFocused()

    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    await expect(trigger).toBeFocused()
  })
})
