import { expect, test } from '@playwright/test'

const caseId = process.env.E2E_CASE_ID ?? ''
const sourceFilename = process.env.E2E_OCR_SOURCE_FILENAME ?? '比準地查估.pdf'

const ready = Boolean(caseId)

test.describe('persistent Demo OCR + Ollama field analysis', () => {
  test.skip(!ready, 'E2E_CASE_ID is required for the persistent Demo acceptance run')
  test.setTimeout(300_000)

  test('runs the real source PDF through local OCR and qwen3.5, then exposes grounded candidates', async ({ page }) => {
    await page.goto('/')
    const loginResponse = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && new URL(response.url()).pathname.endsWith('/auth/demo-login')
    ))
    await page.getByTestId('demo-login-appraiser').click()
    expect((await loginResponse).status()).toBe(200)

    await page.goto(`/app/valuation/cases/${encodeURIComponent(caseId)}/documents`)
    await expect(page.getByTestId('valuation-step-2')).toHaveAttribute('aria-current', 'step')
    await expect(page.locator('#valuation-document-workspace')).toBeVisible()

    const documentRow = page.locator('li').filter({ hasText: sourceFilename }).first()
    await expect(documentRow).toBeVisible()
    await documentRow.locator('select[data-testid^="document-analysis-form-"]').selectOption('F03')

    const extractionResponsePromise = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname
      return response.request().method() === 'POST'
        && path.includes(`/valuation/cases/${encodeURIComponent(caseId)}/documents/`)
        && path.endsWith('/extract')
    }, { timeout: 120_000 })
    const analysisResponsesPromise = new Promise<Response[]>((resolve) => {
      const responses: Response[] = []
      const handler = (response: Response) => {
        const path = new URL(response.url()).pathname
        if (
          response.request().method() === 'POST'
          && path.includes(`/valuation/cases/${encodeURIComponent(caseId)}/documents/`)
          && path.endsWith('/extraction/analyze-fields')
        ) {
          responses.push(response)
          if (responses.length === 6) {
            page.off('response', handler)
            resolve(responses)
          }
        }
      }
      page.on('response', handler)
    })

    await documentRow.locator('button[data-testid^="extract-document-"]').click()

    const extractionResponse = await extractionResponsePromise
    expect(extractionResponse.ok()).toBeTruthy()
    const extraction = await extractionResponse.json() as {
      extraction_status: string
      provider: string
      extracted_text?: string | null
    }
    expect(extraction.extraction_status).toBe('COMPLETED')
    expect(extraction.provider.toLowerCase()).toContain('local')
    expect((extraction.extracted_text ?? '').trim().length).toBeGreaterThan(100)

    const analysisResponses = await analysisResponsesPromise
    expect(analysisResponses).toHaveLength(6)
    expect(analysisResponses.every((response) => response.ok())).toBeTruthy()
    expect(analysisResponses.map((response) => response.request().postDataJSON())).toEqual([
      { form_code: 'F01' },
      { form_code: 'F02' },
      { form_code: 'F02-RF' },
      { form_code: 'F03' },
      { form_code: 'F04' },
      { form_code: 'S01' },
    ])
    const analysis = await analysisResponses[5].json() as {
      candidates: Array<{
        analysis_provider: string
        model_id: string | null
        source_text: string | null
        field_status: string
      }>
    }
    expect(analysis.candidates.length).toBeGreaterThan(0)
    expect(analysis.candidates.some((candidate) => candidate.analysis_provider === 'OLLAMA')).toBeTruthy()
    expect(analysis.candidates.some((candidate) => candidate.model_id === 'qwen3.5:latest')).toBeTruthy()
    expect(analysis.candidates.every((candidate) => Boolean(candidate.source_text?.trim()))).toBeTruthy()
    expect(analysis.candidates.some((candidate) => candidate.field_status === 'NEEDS_CONFIRMATION')).toBeTruthy()

    await expect(page.getByTestId('valuation-candidate-workspace')).toBeVisible()
    await expect(page.locator('article[data-testid^="candidate-"]')).toHaveCount(analysis.candidates.length)
  })
})
