import { expect, test, type Page } from '@playwright/test'

async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: '開啟使用者選單' }).click()
  await page.getByRole('menuitem', { name: '登出' }).click()
  await expect(page).toHaveURL(/\/$/)
}

async function quickLogin(page: Page, testId: string, role: string, expectedPath: RegExp): Promise<void> {
  await page.goto('/')
  const responsePromise = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST' && path.endsWith('/auth/demo-login')
  })
  await page.getByTestId(testId).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON()).toEqual({ role })
  await expect(page).toHaveURL(expectedPath)
}

test('three Demo role buttons enter the correct workspaces without typing credentials', async ({ page }) => {
  await quickLogin(page, 'demo-login-appraiser', 'APPRAISER', /\/app\/valuation\/dashboard$/)
  await logout(page)

  await quickLogin(page, 'demo-login-reviewer', 'REVIEWER', /\/app\/review\/dashboard$/)
  await logout(page)

  await quickLogin(page, 'demo-login-inspector', 'INSPECTOR', /\/app\/history\/search$/)
})
