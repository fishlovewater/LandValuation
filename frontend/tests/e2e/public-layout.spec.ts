import { expect, test } from '@playwright/test'

test.use({ viewport: { width: 1366, height: 768 } })

test('shows the login card and subsystem cards in the first viewport', async ({ page }) => {
  await page.goto('/')

  const viewport = page.viewportSize()
  expect(viewport).not.toBeNull()
  const loginBox = await page.locator('.login-card').boundingBox()
  const valueBoxes = await page.locator('.value-card').evaluateAll((elements) =>
    elements.map((element) => {
      const box = element.getBoundingClientRect()
      return { top: box.top, bottom: box.bottom, height: box.height }
    }),
  )

  expect(loginBox).not.toBeNull()
  expect(loginBox!.y).toBeGreaterThanOrEqual(0)
  expect(loginBox!.y + loginBox!.height).toBeLessThanOrEqual(viewport!.height)
  expect(valueBoxes).toHaveLength(4)
  for (const box of valueBoxes) {
    expect(box.top).toBeGreaterThanOrEqual(0)
    expect(box.bottom).toBeLessThanOrEqual(viewport!.height)
  }
})

test('keeps page controls at least 44px high', async ({ page }) => {
  await page.goto('/')
  const controls = page.locator('button, a[href], input')
  const boxes = await controls.evaluateAll((elements) =>
    elements.map((element) => {
      const box = element.getBoundingClientRect()
      return { height: box.height, width: box.width }
    }),
  )

  expect(boxes.length).toBeGreaterThan(0)
  for (const box of boxes) {
    expect(box.height).toBeGreaterThanOrEqual(44)
  }
})

test.describe('authenticated mobile shell', () => {
  test.use({ viewport: { width: 640, height: 768 } })

  test('keeps authorized case search usable at 640px', async ({ page }) => {
    await page.route('**/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'user-appraiser',
          username: 'appraiser.demo',
          email: 'appraiser@example.test',
          display_name: '示範估價人員',
          roles: ['APPRAISER'],
          permissions: ['case.read', 'valuation.read', 'valuation.update'],
        }),
      }),
    )
    await page.route('**/api/v1/history/cases?offset=0&limit=20', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          total: 0,
          offset: 0,
          limit: 20,
          permissions: {
            can_view_valuation: true,
            can_view_review: false,
          },
        }),
      }),
    )
    await page.addInitScript(() => {
      sessionStorage.setItem('lva-demo-access-token', 'browser-demo-token')
      sessionStorage.setItem('lva-demo-token-expires-at', String(Date.now() + 1_800_000))
    })

    await page.goto('/app/history/search')
    const trigger = page.getByTestId('case-search-trigger')
    await expect(trigger).toBeVisible()
    const triggerBox = await trigger.boundingBox()
    expect(triggerBox).not.toBeNull()
    expect(triggerBox!.width).toBeGreaterThanOrEqual(44)
    expect(triggerBox!.height).toBeGreaterThanOrEqual(44)
    await expect(page.getByTestId('case-search')).toBeHidden()

    await trigger.click()
    const popover = page.locator('#case-search-popover')
    await expect(popover).toBeVisible()
    const input = popover.locator('input[type="search"]')
    await expect(input).toBeFocused()

    await input.fill('HIST-640')
    await input.press('Escape')
    await expect(popover).toBeHidden()
    await expect(trigger).toBeFocused()

    await trigger.click()
    await input.fill('HIST-640')
    await popover.getByRole('button', { name: '搜尋', exact: true }).click()
    await expect(page).toHaveURL(/\/app\/history\/search\?keyword=HIST-640$/)
  })
})
