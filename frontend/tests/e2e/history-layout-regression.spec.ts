import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

async function loginForHistory(page: Page, role: 'inspector' | 'appraiser' | 'reviewer' = 'inspector'): Promise<void> {
  await page.goto('/')
  await page.getByTestId(`demo-login-${role}`).click()
  await expect.poll(
    () => page.evaluate(() => Boolean(sessionStorage.getItem('lva-demo-access-token'))),
    { timeout: 15_000 },
  ).toBe(true)
  await page.goto('/app/history/search')
  await expect(page).toHaveURL(/\/app\/history\/search$/)
}

test('History search stays readable from desktop to mobile without exposing internal location codes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginForHistory(page)
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
  await loginForHistory(page)

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

for (const scenario of [
  {
    role: 'appraiser',
    permission: '目前可查看：估價資料',
    visibleTab: 'history-tab-valuation',
    hiddenTab: 'history-tab-review',
  },
  {
    role: 'reviewer',
    permission: '目前可查看：審查資料',
    visibleTab: 'history-tab-review',
    hiddenTab: 'history-tab-valuation',
  },
] as const) {
  test(`History ${scenario.role} scope only exposes authorized case data`, async ({ page }) => {
    await loginForHistory(page, scenario.role)

    await expect(page.locator('.history-search__permission')).toHaveText(scenario.permission)
    const completedCase = page.locator('[data-testid^="history-case-row-"]', {
      hasText: 'DEMO-LIFECYCLE-005',
    })
    await expect(completedCase).toBeVisible()
    await completedCase.getByRole('button', { name: '查看案件' }).click()

    await expect(page).toHaveURL(/\/app\/history\/cases\//)
    await expect(page.getByTestId(scenario.visibleTab)).toBeVisible()
    await expect(page.getByTestId(scenario.hiddenTab)).toHaveCount(0)

    const detailText = await page.getByTestId('history-case').innerText()
    if (scenario.role === 'appraiser') {
      expect(detailText).toContain('可查看：估價資料')
      expect(detailText).not.toContain('可查看：審查資料')
    } else {
      expect(detailText).toContain('可查看：審查資料')
      expect(detailText).not.toContain('可查看：估價資料')
    }
  })
}

test('History rich demo verifies document versions, DOCX/XLSX preview, and field version comparison', async ({ page }) => {
  await loginForHistory(page)

  await page.getByTestId('history-keyword').fill('HIST-BOTH-001')
  await page.getByTestId('history-search-submit').click()
  const richCase = page.locator('[data-testid^="history-case-row-"]', { hasText: 'HIST-BOTH-001' })
  await expect(richCase).toBeVisible()
  await richCase.getByRole('button', { name: '查看案件' }).click()

  await expect(page).toHaveURL(/\/app\/history\/cases\/71000000-0000-4000-8000-000000000003/)
  await expect(page.getByTestId('history-case')).toContainText('3 份目前文件 · 1 個歷史版本')

  await page.getByTestId('history-preview-77000000-0000-4000-8000-000000000005').click()
  const spreadsheet = page.getByTestId('spreadsheet-preview')
  await expect(spreadsheet).toBeVisible()
  await expect(spreadsheet).toContainText('比準地估價')
  await expect(spreadsheet).toContainText('125000')
  await expect(spreadsheet).toContainText('HIST-BOTH-001')
  await page.getByRole('button', { name: '關閉預覽' }).click()

  const historyVersions = page.locator('.document-list__versions', { hasText: '歷史版本 1 個' })
  await historyVersions.locator('summary').click()
  await page.getByTestId('history-preview-77000000-0000-4000-8000-000000000004').click()
  await expect(page.getByTestId('spreadsheet-preview')).toContainText('120000')
  await expect(page.getByTestId('spreadsheet-preview')).not.toContainText('125000')
  await page.getByRole('button', { name: '關閉預覽' }).click()

  await page.getByTestId('history-preview-77000000-0000-4000-8000-000000000003').click()
  const docxPreview = page.getByTestId('document-text-preview')
  await expect(docxPreview).toBeVisible()
  await expect(docxPreview).toContainText('案件歷史 DOCX 預覽測試')
  await expect(docxPreview).toContainText('HIST-BOTH-001')

  await page.getByTestId('history-tab-versions').click()
  const versionSection = page.getByTestId('history-version-section')
  await expect(versionSection).toBeVisible()
  await expect(versionSection).toContainText('建立案件歷史驗證基準')
  await expect(versionSection).toContainText('更新比準地價格並完成審查')
  await expect(versionSection).toContainText('比較法價格')
  await expect(versionSection).toContainText('120000')
  await expect(versionSection).toContainText('125000')
  await expect(versionSection).not.toContainText('REVIEWING')
  await expect(versionSection).not.toContainText('COMPLETED')
})

test('History missing MinIO object degrades to a safe document error in the real demo', async ({ page }) => {
  await loginForHistory(page)

  await page.getByTestId('history-keyword').fill('HIST-REV-001')
  await page.getByTestId('history-search-submit').click()
  const missingCase = page.locator('[data-testid^="history-case-row-"]', { hasText: 'HIST-REV-001' })
  await expect(missingCase).toBeVisible()
  await missingCase.getByRole('button', { name: '查看案件' }).click()

  await expect(page).toHaveURL(/\/app\/history\/cases\/71000000-0000-4000-8000-000000000002/)
  await page.getByTestId('history-preview-77000000-0000-4000-8000-000000000002').click()
  await expect(page.getByTestId('history-document-preview')).toBeVisible()
  await expect(page.getByTestId('history-document-preview')).toContainText('文件目前無法下載')

  await page.getByTestId('history-download-77000000-0000-4000-8000-000000000002').click()
  await expect(page.getByTestId('history-case')).toContainText('文件目前無法下載')
})

test('History supports keyboard navigation, tab semantics, and preview focus restoration', async ({ page }) => {
  await loginForHistory(page)

  const searchFlowCurrent = page.locator('.history-search__flow [aria-current="step"]')
  await expect(searchFlowCurrent).toContainText('搜尋案件')

  const advancedToggle = page.getByTestId('history-advanced-toggle')
  await advancedToggle.focus()
  await page.keyboard.press('Enter')
  await expect(advancedToggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByTestId('history-advanced-filters')).toBeVisible()

  await page.getByTestId('history-keyword').fill('HIST-BOTH-001')
  await page.getByTestId('history-search-submit').click()
  const richCase = page.locator('[data-testid^="history-case-row-"]', { hasText: 'HIST-BOTH-001' })
  await expect(richCase).toBeVisible()
  await richCase.getByRole('button', { name: '查看案件' }).click()

  await expect(page.locator('.history-case__flow [aria-current="step"]')).toContainText('查看資料 / 下載文件')
  const tablist = page.getByRole('tablist', { name: '案件歷程資料區段' })
  await expect(tablist).toBeVisible()

  const overviewTab = page.getByTestId('history-tab-overview')
  const timelineTab = page.getByTestId('history-tab-timeline')
  const versionsTab = page.getByTestId('history-tab-versions')
  await expect(overviewTab).toHaveAttribute('aria-selected', 'true')
  await expect(overviewTab).toHaveAttribute('tabindex', '0')

  await overviewTab.focus()
  await page.keyboard.press('ArrowRight')
  await expect(timelineTab).toBeFocused()
  await expect(timelineTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#history-panel-timeline')).toBeVisible()
  await expect(page.getByTestId('history-timeline-filter-all')).toHaveAttribute('aria-pressed', 'true')

  await page.keyboard.press('End')
  await expect(versionsTab).toBeFocused()
  await expect(versionsTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#history-panel-versions')).toBeVisible()

  await page.keyboard.press('Home')
  await expect(overviewTab).toBeFocused()
  await expect(page.locator('#history-panel-overview')).toBeVisible()

  const docxPreviewButton = page.getByTestId('history-preview-77000000-0000-4000-8000-000000000003')
  await docxPreviewButton.focus()
  await page.keyboard.press('Enter')
  const preview = page.getByTestId('history-document-preview')
  await expect(preview).toBeVisible()
  await expect(preview).toBeFocused()
  await expect(page.getByTestId('document-text-preview')).toContainText('案件歷史 DOCX 預覽測試')

  await page.keyboard.press('Escape')
  await expect(preview).toHaveCount(0)
  await expect(docxPreviewButton).toBeFocused()
})