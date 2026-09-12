import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ mode: 'serial' })
test.skip(process.platform !== 'win32', 'History visual baselines are captured on the Windows demo environment')

const CASE_ID = '71000000-0000-4000-8000-000000000003'
const CASE_NO = 'HIST-BOTH-001'

async function loginInspector(page: Page): Promise<void> {
  await page.goto('/')
  await page.getByTestId('demo-login-inspector').click()
  await expect.poll(
    () => page.evaluate(() => Boolean(sessionStorage.getItem('lva-demo-access-token'))),
    { timeout: 15_000 },
  ).toBe(true)
  await page.goto('/app/history/search')
  await expect(page).toHaveURL(/\/app\/history\/search$/)
}

async function stabilizePage(page: Page): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
        caret-color: transparent !important;
      }
    `,
  })
}

async function openDeterministicSearch(page: Page): Promise<void> {
  await loginInspector(page)
  await stabilizePage(page)
  await page.getByTestId('history-keyword').fill(CASE_NO)
  await page.getByTestId('history-search-submit').click()
  const row = page.locator('[data-testid^="history-case-row-"]', { hasText: CASE_NO })
  await expect(row).toBeVisible()
  await expect(page.locator('[data-testid^="history-case-row-"]')).toHaveCount(1)
}

async function openDeterministicCase(page: Page): Promise<void> {
  await openDeterministicSearch(page)
  await page.locator('[data-testid^="history-case-row-"]', { hasText: CASE_NO })
    .getByRole('button', { name: '查看案件' })
    .click()
  await expect(page).toHaveURL(new RegExp(`/app/history/cases/${CASE_ID}`))
  await expect(page.getByTestId('history-case')).toContainText('3 份目前文件 · 1 個歷史版本')
}

for (const viewport of [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 1024, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
] as const) {
  test(`History search visual baseline - ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await openDeterministicSearch(page)

    await expect(page.getByTestId('history-search')).toHaveScreenshot(
      `history-search-${viewport.name}.png`,
      {
        animations: 'disabled',
        caret: 'hide',
        maxDiffPixelRatio: 0.01,
      },
    )
  })

  test(`History case visual baseline - ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await openDeterministicCase(page)

    await expect(page.getByTestId('history-case')).toHaveScreenshot(
      `history-case-${viewport.name}.png`,
      {
        animations: 'disabled',
        caret: 'hide',
        maxDiffPixelRatio: 0.01,
      },
    )
  })
}
