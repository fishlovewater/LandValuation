import { expect, test, type Page } from '@playwright/test'
import { reviewIdFromSubmission } from './demo-flow-contracts'
import { loginAs } from './login-boundary-diagnostics'

const demo = {
  caseId: process.env.E2E_CASE_ID ?? '',
  caseNo: process.env.E2E_CASE_NO ?? '',
  appraiser: {
    username: process.env.E2E_APPRAISER_USERNAME ?? '',
    password: process.env.E2E_APPRAISER_PASSWORD ?? '',
  },
  reviewer: {
    username: process.env.E2E_REVIEWER_USERNAME ?? '',
    password: process.env.E2E_REVIEWER_PASSWORD ?? '',
  },
}

const ready = [
  demo.caseId,
  demo.caseNo,
  demo.appraiser.username,
  demo.appraiser.password,
  demo.reviewer.username,
  demo.reviewer.password,
].every(Boolean)

async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: '開啟使用者選單' }).click()
  await page.getByRole('menuitem', { name: '登出' }).click()
  await expect(page).toHaveURL(/\/$/)
}

async function submitValuation(page: Page): Promise<string> {
  await page.goto(`/app/valuation/cases/${encodeURIComponent(demo.caseId)}/prepare`)
  await expect(page.locator('#case-summary-title')).toContainText(demo.caseNo)
  await page.getByTestId('run-valuation').click()
  await expect(page.getByText('伺服器已完成計算、檢核、F03 提交與正式輸出。')).toBeVisible()

  await page.getByTestId('go-to-submit').click()
  await expect(page.getByTestId('report-package-draft-flow')).toBeVisible()
  await page.getByTestId('report-page-s01-confirm').check()
  await page.getByTestId('report-page-f02-rf-confirm').check()
  await page.getByTestId('report-page-f02-confirm').check()

  const saveResponses = ['/S01', '/F02-RF', '/F02'].map((suffix) => page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'PATCH'
      && path.includes(`/valuation/cases/${encodeURIComponent(demo.caseId)}/reports/`)
      && path.endsWith(`/pages${suffix}`)
  }))
  await page.getByTestId('save-report-pages').click()
  await Promise.all(saveResponses)

  const calculation = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST' && path.endsWith('/formal-calculation')
  })
  await page.getByTestId('run-formal-calculation').click()
  expect((await calculation).ok()).toBeTruthy()

  const formalValidation = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST' && path.endsWith('/formal-validation')
  })
  await page.getByTestId('run-report-formal-validation').click()
  expect((await formalValidation).status()).toBe(201)
  await expect(page.getByTestId('formal-validation-result')).toBeVisible()

  const warningCheckboxes = page.locator('input[data-testid^="formal-warning-"]')
  for (let index = 0; index < await warningCheckboxes.count(); index += 1) {
    const checkbox = warningCheckboxes.nth(index)
    if (!(await checkbox.isChecked())) await checkbox.check()
  }

  const formalPdf = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST' && path.endsWith('/formal-pdf')
  })
  await page.getByTestId('generate-formal-pdf').click()
  expect((await formalPdf).status()).toBe(201)

  const submission = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST'
      && path.endsWith(`/valuation/cases/${encodeURIComponent(demo.caseId)}/submit-for-review`)
  })
  await page.getByTestId('submit-for-review').click()
  const submissionResponse = await submission
  expect(submissionResponse.status()).toBe(201)
  return reviewIdFromSubmission(await submissionResponse.json())
}

async function sendCorrection(page: Page, reviewId: string): Promise<void> {
  await page.goto(`/app/review/workbench/${encodeURIComponent(reviewId)}`)
  await expect(page.getByTestId('review-workbench')).toContainText(demo.caseNo)

  const start = page.getByTestId('start-review')
  await expect(start).toBeEnabled()
  await start.click()
  await expect(start).toHaveCount(0)

  const openFindings = () => page.locator('[data-testid^="finding-select-"]').filter({ hasText: '待處理' })
  const initialOpenCount = await openFindings().count()
  const firstOpen = openFindings().first()
  await expect(firstOpen).toBeVisible()
  await firstOpen.click()
  await page.locator('#finding-decision').selectOption('CONFIRMED_ISSUE')
  await page.getByTestId('finding-reason').fill('人工確認此問題需要估價端補正。')
  const confirmed = page.waitForResponse((response) => response.request().method() === 'POST' && /\/review\/findings\/[^/]+\/triage$/.test(new URL(response.url()).pathname))
  await page.getByTestId('save-finding-decision').click()
  expect((await confirmed).status()).toBe(201)
  await expect(openFindings()).toHaveCount(initialOpenCount - 1)

  while (await openFindings().count()) {
    const openCount = await openFindings().count()
    const open = openFindings().first()
    await open.click()
    await expect(page.locator('#finding-decision')).toBeEnabled()
    await page.locator('#finding-decision').selectOption('DISMISSED_FALSE_POSITIVE')
    await page.getByTestId('finding-reason').fill('其餘項目經人工確認不需納入本次補正。')
    const triage = page.waitForResponse((response) => response.request().method() === 'POST' && /\/review\/findings\/[^/]+\/triage$/.test(new URL(response.url()).pathname))
    await page.getByTestId('save-finding-decision').click()
    expect((await triage).status()).toBe(201)
    await expect(openFindings()).toHaveCount(openCount - 1)
  }

  const correctionButton = page.getByTestId('request-correction')
  await expect(correctionButton).toBeEnabled()
  await correctionButton.click()
  await expect(page.getByTestId('correction-request-form')).toBeVisible()
  await expect(page.locator('#review-correction-message')).not.toHaveValue('')

  const createRequest = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST' && path.endsWith(`/review/cases/${encodeURIComponent(reviewId)}/correction-requests`)
  })
  const sendRequest = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST' && /\/review\/correction-requests\/[^/]+\/send$/.test(path)
  })
  await page.getByTestId('correction-request-form').locator('button[type="submit"]').click()
  expect((await createRequest).status()).toBe(201)
  expect((await sendRequest).status()).toBe(200)
  await expect(page.getByTestId('correction-status-panel')).toContainText('SENT')
  await expect(page.getByTestId('awaiting-correction')).toBeDisabled()
}

test.describe('real correction handoff workflow', () => {
  test.skip(!ready, 'Persistent Demo case and appraiser/reviewer credentials are required.')

  test('returns a confirmed Review issue to the appraiser with an actionable newer-draft path', async ({ page }, testInfo) => {
    await loginAs(page, 'APPRAISER', demo.appraiser, testInfo)
    const reviewId = await submitValuation(page)
    await logout(page)

    await loginAs(page, 'REVIEWER', demo.reviewer, testInfo)
    await sendCorrection(page, reviewId)
    await logout(page)

    await loginAs(page, 'APPRAISER', demo.appraiser, testInfo)
    await page.goto(`/app/valuation/cases/${encodeURIComponent(demo.caseId)}/prepare`)

    const correctionPanel = page.getByTestId('valuation-correction-request')
    await expect(correctionPanel).toBeVisible()
    await expect(correctionPanel).toContainText('第 1 次補正要求')
    await expect(correctionPanel).toContainText('要求修正')

    const correctionLocationButton = correctionPanel.getByRole('button', { name: /前往(文件處理|資料修正)/ }).first()
    await correctionLocationButton.click()
    await expect(page.getByText(/修正要求：/)).toBeVisible()
    await expect(page.getByTestId('open-revision-fields')).toBeVisible()
    await expect(page.getByTestId('save-confirmed-fields')).toBeEnabled()
    await expect(page.getByTestId('prepare-revision-draft')).toHaveCount(0)
    await expect(correctionPanel).toContainText('補正要求')
  })
})
