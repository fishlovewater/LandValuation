import { expect, test } from '@playwright/test'
import { loginAs } from './login-boundary-diagnostics'

const demo = {
  caseId: process.env.E2E_CASE_ID ?? '',
  caseNo: process.env.E2E_CASE_NO ?? '',
  appraiser: {
    username: process.env.E2E_APPRAISER_USERNAME ?? '',
    password: process.env.E2E_APPRAISER_PASSWORD ?? '',
  },
}

const ready = Boolean(
  demo.caseId
  && demo.caseNo
  && demo.appraiser.username
  && demo.appraiser.password,
)

function previousDate(value: string): string {
  const date = new Date(`${value}T12:00:00`)
  date.setDate(date.getDate() - 1)
  return date.toISOString().slice(0, 10)
}

test.describe('valuation remediation workflow', () => {
  test.skip(!ready, 'Persistent Demo identifiers and appraiser credentials are required.')

  test('turns a real validation blocker into a guided field correction, then permits the next step', async ({ page }, testInfo) => {
    await loginAs(page, 'APPRAISER', demo.appraiser, testInfo)
    await page.goto(`/app/valuation/cases/${encodeURIComponent(demo.caseId)}/prepare`)

    await expect(page.locator('#case-summary-title')).toContainText(demo.caseNo)
    await expect(page.getByTestId('valuation-workflow-guide')).toContainText('第 1 步 / 6')
    await page.getByTestId('valuation-step-3').click()
    await page.getByTestId('data-section-f03').click()

    const valuationDate = page.locator('#f03-valuation-base-date')
    await expect(valuationDate).toBeEnabled()
    const originalDate = await valuationDate.inputValue()
    expect(originalDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)

    await valuationDate.fill(previousDate(originalDate))

    const blockedValidationResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'POST'
        && path.endsWith(`/valuation/cases/${encodeURIComponent(demo.caseId)}/validations`)
    })
    await page.getByTestId('valuation-step-4').click()
    await page.getByTestId('run-valuation').click()
    const blockedValidation = await blockedValidationResponse
    expect(blockedValidation.status()).toBe(201)

    const consistencyFinding = page.locator('.finding-list li').filter({ hasText: 'F03_CASE_CONSISTENCY' })
    await expect(consistencyFinding).toBeVisible()
    await expect(consistencyFinding).toContainText('問題位置：')
    await expect(consistencyFinding).toContainText('估價基準日')
    await expect(consistencyFinding.getByRole('button', { name: '前往修正' })).toBeVisible()
    await expect(page.getByTestId('go-to-submit')).toBeDisabled()
    await expect(page.locator('[aria-current="step"]')).toContainText('4')

    await consistencyFinding.getByRole('button', { name: '前往修正' }).click()
    await expect(valuationDate).toBeFocused()

    await valuationDate.fill(originalDate)

    const passingValidationResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'POST'
        && path.endsWith(`/valuation/cases/${encodeURIComponent(demo.caseId)}/validations`)
    })
    await page.getByTestId('valuation-step-4').click()
    await page.getByTestId('run-valuation').click()
    const passingValidation = await passingValidationResponse
    expect(passingValidation.status()).toBe(201)

    await expect(page.getByText('伺服器已完成計算、檢核、F03 提交與正式輸出。')).toBeVisible()
    await expect(page.getByTestId('go-to-submit')).toBeEnabled()
    await expect(page.getByTestId('valuation-workflow-guide')).toContainText('第 4 步 / 6')
    await Promise.all([
      page.waitForURL(new RegExp(`/app/valuation/cases/${encodeURIComponent(demo.caseId)}/submit$`)),
      page.getByTestId('wizard-next').click(),
    ])
    await expect(page.locator('[aria-current="step"]')).toContainText('5')
  })
})
