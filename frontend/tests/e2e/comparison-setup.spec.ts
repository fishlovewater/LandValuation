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

test.describe('structured comparison setup', () => {
  test.skip(!ready, 'Persistent Demo case and appraiser credentials are required.')

  test('supports the explicit disabled path and creates one traceable comparison setup without raw UUID editing', async ({ page }, testInfo) => {
    await loginAs(page, 'APPRAISER', demo.appraiser, testInfo)
    await page.goto(`/app/valuation/cases/${encodeURIComponent(demo.caseId)}/prepare`)
    await expect(page.locator('#case-summary-title')).toContainText(demo.caseNo)

    await page.getByTestId('valuation-step-4').click()
    await page.getByTestId('run-valuation').click()
    await expect(page.getByText('已完成計算、檢核、F03 確認與單表輸出。')).toBeVisible()
    await page.getByTestId('go-to-submit').click()

    await page.getByTestId('open-report-page-editors').click()
    await page.getByRole('button', { name: 'F02', exact: true }).click()

    const panel = page.getByTestId('comparison-setup')
    await expect(panel).toBeVisible()
    const enabled = page.getByTestId('comparison-workflow-enabled')
    await expect(enabled).toBeChecked()

    const disableResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'PATCH'
        && path.includes(`/valuation/cases/${encodeURIComponent(demo.caseId)}/reports/`)
        && path.endsWith('/pages/F02')
    })
    await enabled.uncheck()
    const disabled = await disableResponse
    expect(disabled.ok()).toBeTruthy()
    expect(disabled.request().postDataJSON()).toEqual({ comparison_workflow_enabled: false })
    await expect(page.getByTestId('comparison-disabled-note')).toBeVisible()

    const enableResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'PATCH'
        && path.includes(`/valuation/cases/${encodeURIComponent(demo.caseId)}/reports/`)
        && path.endsWith('/pages/F02')
    })
    await enabled.check()
    const reenabled = await enableResponse
    expect(reenabled.ok()).toBeTruthy()
    expect(reenabled.request().postDataJSON()).toEqual({ comparison_workflow_enabled: true })
    await expect(page.getByTestId('comparison-disabled-note')).toHaveCount(0)

    await page.getByTestId('comparison-target-count').selectOption('1')
    await page.getByTestId('comparison-transaction-no-0').fill(`E2E-COMP-${Date.now().toString().slice(-8)}`)
    await page.getByTestId('comparison-transaction-date-0').fill('2026-07-15')
    await page.getByTestId('comparison-total-price-0').fill('15000000')
    await page.getByTestId('comparison-unit-price-0').fill('180000')
    await page.getByTestId('comparison-weight-0').fill('1')
    await page.getByTestId('comparison-source-notes-0').fill('E2E 人工確認之交易案例來源。')

    const createButton = page.getByTestId('create-comparison-setup')
    await expect(createButton).toBeEnabled()
    const createResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'POST'
        && path.endsWith(`/valuation/cases/${encodeURIComponent(demo.caseId)}/comparison-setup`)
    })
    await createButton.click()
    const created = await createResponse
    expect(created.ok()).toBeTruthy()

    const payload = created.request().postDataJSON() as Record<string, unknown>
    expect(payload).not.toHaveProperty('rule_version_id')
    expect(payload).not.toHaveProperty('comparison_targets')
    expect(payload).toMatchObject({
      report_id: expect.any(String),
      benchmark_land_id: expect.any(String),
      targets: [
        expect.objectContaining({
          transaction_date: '2026-07-15',
          transaction_total_price: '15000000',
          normal_land_unit_price: '180000',
          weight: '1',
          source_notes: 'E2E 人工確認之交易案例來源。',
        }),
      ],
    })
    await expect(panel).toContainText('比較分析已建立並寫入正式 F02 / F02-RF，共 1 筆比較標的。')
  })
})
