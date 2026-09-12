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

async function switchDemoRole(page: Page, testId: string, role: string, expectedPath: RegExp): Promise<void> {
  const responsePromise = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST' && path.endsWith('/auth/demo-login')
  })
  await page.getByRole('button', { name: '開啟使用者選單' }).click()
  await page.getByTestId(testId).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON()).toEqual({ role })
  await expect(page).toHaveURL(expectedPath)
}

async function expectAssistantFramework(page: Page): Promise<void> {
  const shortcut = page.getByTestId('assistant-shortcut')
  await expect(shortcut).toBeVisible()
  await shortcut.click()
  const assistant = page.getByTestId('assistant-floating-window')
  await expect(assistant).toBeVisible()
  await expect(assistant).toContainText('AI 助手')
  await expect(assistant).toContainText('依問題自動判斷資料來源')
  await assistant.getByRole('button', { name: '關閉' }).click()
  await expect(assistant).toHaveCount(0)
}

test('three Demo role buttons enter the correct workspaces without typing credentials', async ({ page }) => {
  await quickLogin(page, 'demo-login-appraiser', 'APPRAISER', /\/app\/valuation\/dashboard$/)
  await expectAssistantFramework(page)
  await logout(page)

  await quickLogin(page, 'demo-login-reviewer', 'REVIEWER', /\/app\/review\/dashboard$/)
  await expectAssistantFramework(page)
  await logout(page)

  await quickLogin(page, 'demo-login-inspector', 'INSPECTOR', /\/app\/history\/search$/)
  await expectAssistantFramework(page)
})

test('Demo presenter can switch roles inside the authenticated workspace without logging out', async ({ page }) => {
  await quickLogin(page, 'demo-login-appraiser', 'APPRAISER', /\/app\/valuation\/dashboard$/)

  await switchDemoRole(page, 'demo-switch-reviewer', 'REVIEWER', /\/app\/review\/dashboard$/)
  await switchDemoRole(page, 'demo-switch-inspector', 'INSPECTOR', /\/app\/history\/search$/)

  await page.getByRole('button', { name: '開啟使用者選單' }).click()
  await expect(page.getByTestId('demo-switch-inspector')).toBeDisabled()
  await expect(page.getByTestId('demo-switch-inspector')).toContainText('目前')
})
