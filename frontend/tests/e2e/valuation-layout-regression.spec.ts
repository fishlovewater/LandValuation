import { expect, test } from '@playwright/test'

test('valuation modal and document workspace stay within their visual columns', async ({ page }) => {
  const caseId = process.env.E2E_CASE_ID
  if (!caseId) throw new Error('E2E_CASE_ID is required')

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

  await page.goto(`/app/valuation/cases/${caseId}/prepare`)
  const next = page.getByTestId('wizard-next')
  await expect(next).toBeVisible()
  await next.click()

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
