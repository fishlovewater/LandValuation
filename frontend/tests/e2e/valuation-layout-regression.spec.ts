import { expect, test } from '@playwright/test'

test('valuation modal and document workspace stay within their visual columns', async ({ page }) => {
  const caseId = process.env.E2E_CASE_ID
  const caseNo = process.env.E2E_CASE_NO ?? 'DEMO-F03-PERSISTENT-001'

  await page.setViewportSize({ width: 1110, height: 900 })
  await page.goto('/')
  await page.getByTestId('demo-login-appraiser').click()
  await expect(page).toHaveURL(/\/app\/valuation\/dashboard$/)

  await page.getByTestId('create-case').click()
  const modal = page.getByRole('dialog', { name: '新增估價案件' })
  await expect(modal).toBeVisible()
  const overflow = await modal.evaluate((element) => ({
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
    right: element.getBoundingClientRect().right,
    viewport: window.innerWidth,
  }))
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1)
  expect(overflow.right).toBeLessThanOrEqual(overflow.viewport)
  await page.getByRole('button', { name: '取消' }).click()

  if (caseId) {
    await page.goto(`/app/valuation/cases/${caseId}/documents`)
    await expect(page).toHaveURL(new RegExp(`/app/valuation/cases/${caseId}/documents$`))
  } else {
    const targetRow = page.getByRole('row').filter({ hasText: caseNo })
    await expect(targetRow).toBeVisible()
    await targetRow.getByRole('button', { name: '繼續估價' }).click()
    await expect(page).toHaveURL(/\/app\/valuation\/cases\/[^/]+(?:\/(?:documents|ai-review|data|calculation|report))?$/)
    await page.getByTestId('valuation-step-2').click()
    await expect(page).toHaveURL(/\/app\/valuation\/cases\/[^/]+\/documents$/)
  }

  const workspace = page.locator('#valuation-document-workspace')
  await expect(workspace).toBeVisible()
  const layout = await workspace.evaluate((element) => {
    const list = element.querySelector('.document-ai-grid__list') as HTMLElement
    const preview = element.querySelector('.document-preview') as HTMLElement
    const listRect = list.getBoundingClientRect()
    const previewRect = preview.getBoundingClientRect()
    return {
      workspaceOverflow: element.scrollWidth - element.clientWidth,
      listOverflow: list.scrollWidth - list.clientWidth,
      listRight: listRect.right,
      previewLeft: previewRect.left,
    }
  })
  expect(layout.workspaceOverflow).toBeLessThanOrEqual(1)
  expect(layout.listOverflow).toBeLessThanOrEqual(1)
  expect(layout.listRight).toBeLessThanOrEqual(layout.previewLeft + 1)
})
