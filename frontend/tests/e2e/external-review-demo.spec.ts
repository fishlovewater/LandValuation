import { expect, test } from '@playwright/test'

const reviewId = process.env.E2E_EXTERNAL_REVIEW_ID ?? ''
const caseNo = process.env.E2E_EXTERNAL_CASE_NO ?? 'DEMO-EXTERNAL-REVIEW-001'

test.describe('real External Review demo', () => {
  test.skip(!reviewId, 'A seeded External Review ID is required.')

  test('opens the external intake and freezes version 1 when review starts', async ({ page }) => {
    await page.goto('/')
    const loginResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'POST' && path.endsWith('/auth/demo-login')
    })
    await page.getByTestId('demo-login-reviewer').click()
    expect((await loginResponse).status()).toBe(200)
    await expect(page).toHaveURL(/\/app\/review\/dashboard$/)

    await page.goto(`/app/review/workbench/${encodeURIComponent(reviewId)}`)
    const workbench = page.getByTestId('review-workbench')
    await expect(workbench).toBeVisible()
    await expect(workbench).toContainText(caseNo)
    await expect(page.getByTestId('review-source-strip')).toContainText('外部案件')

    const progress = page.getByTestId('review-progress')
    await expect(progress).toContainText('建立案件')
    await expect(progress).toContainText('文件匯入')
    await expect(progress).toContainText('欄位確認')

    const intake = page.getByTestId('external-review-intake')
    await expect(intake).toBeVisible()
    await expect(intake).toContainText('文件匯入與欄位確認')
    await expect(intake).toContainText('估價報告原始文件')
    await expect(intake).toContainText('已納入審查')

    const preflightResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'POST'
        && path.endsWith(`/review/workbench/cases/${reviewId}/start/preflight`)
    })
    const startResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'POST'
        && path.endsWith(`/review/workbench/cases/${reviewId}/start`)
    })
    await page.getByTestId('start-review').click()
    expect((await preflightResponse).status()).toBe(200)
    const started = await startResponse
    expect(started.status()).toBe(200)
    const payload = await started.json()
    expect(payload.run?.external_input_snapshot_id).toBeTruthy()
    expect(payload.run?.external_input_snapshot_no).toBe(1)
    expect(payload.run?.external_input_fingerprint).toMatch(/^[0-9a-f]{64}$/)

    await expect(page.getByTestId('review-input-provenance')).toContainText('v1')
    await expect(page.getByTestId('review-input-provenance')).toContainText('審查輸入已凍結')
  })
})