import { expect, test } from '@playwright/test'

test('History search stays readable from desktop to mobile without exposing internal location codes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.getByTestId('demo-login-inspector').click()
  await expect(page).toHaveURL(/\/app\/history\/search$/)
  await expect(page.locator('.history-search__permission')).toContainText('估價資料、審查資料')

  await page.getByTestId('history-advanced-toggle').click()
  await expect(page.getByTestId('history-advanced-filters')).toBeVisible()
  await expect(page.getByTestId('history-district-code').locator('option')).toHaveCount(30)

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport)
    await expect(page.getByTestId('history-search')).toBeVisible()
    await expect(page.getByTestId('history-search-submit')).toBeVisible()

    const overflow = await page.evaluate(() => (
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    ))
    expect(overflow).toBeLessThanOrEqual(1)
  }

  const visibleText = await page.locator('body').innerText()
  expect(visibleText).not.toContain('縣市代碼')
  expect(visibleText).not.toContain('行政區代碼')
  expect(visibleText).not.toContain('65000000')
  expect(visibleText).not.toContain('3101')
})

test('History detail exposes readable data, previewable documents, and no raw workflow codes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.getByTestId('demo-login-inspector').click()
  await expect(page).toHaveURL(/\/app\/history\/search$/)

  const completedCase = page.locator('[data-testid^="history-case-row-"]', {
    hasText: 'DEMO-LIFECYCLE-005',
  })
  await expect(completedCase).toBeVisible()
  await completedCase.getByRole('button', { name: '查看案件' }).click()
  await expect(page).toHaveURL(/\/app\/history\/cases\//)
  await expect(page.getByTestId('history-case')).toContainText('土地徵收補償市價查估案件')
  await expect(page.getByTestId('history-case')).toContainText('新北市 板橋區')

  const previewButton = page.locator('[data-testid^="history-preview-"]').first()
  await expect(previewButton).toBeVisible()
  await previewButton.click()
  await expect(page.getByTestId('history-document-preview')).toBeVisible()
  await expect(page.getByTestId('history-document-pdf')).toBeVisible()

  const downloadResponse = page.waitForResponse((response) => (
    response.request().method() === 'GET'
    && /\/history\/documents\/.+\/download$/.test(new URL(response.url()).pathname)
  ))
  await page.locator('[data-testid^="history-download-"]').first().click()
  expect((await downloadResponse).status()).toBe(200)
  await expect(page.getByText(/已準備下載/)).toBeVisible()

  await page.getByTestId('history-tab-review').click()
  const reviewSection = page.getByTestId('history-review-section')
  await expect(reviewSection).toContainText('審查狀態：已收件')
  await expect(reviewSection).toContainText('審查狀態：審查完成')
  await expect(reviewSection).not.toContainText('RECEIVED')
  await expect(reviewSection).not.toContainText('REVIEW_COMPLETED')

  await page.getByTestId('history-tab-timeline').click()
  await expect(page.getByTestId('history-timeline-section')).toContainText('案件時間軸')

  await page.setViewportSize({ width: 390, height: 844 })
  const overflow = await page.evaluate(() => (
    document.documentElement.scrollWidth - document.documentElement.clientWidth
  ))
  expect(overflow).toBeLessThanOrEqual(1)

  const visibleText = await page.locator('body').innerText()
  expect(visibleText).not.toContain('LAND')
  expect(visibleText).not.toContain('NWT')
  expect(visibleText).not.toContain('65000010')
})