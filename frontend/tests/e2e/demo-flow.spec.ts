import { exec } from 'node:child_process'
import { resolve } from 'node:path'
import { promisify } from 'node:util'
import { expect, test, type APIResponse, type Page } from '@playwright/test'
import {
  FINALIZE_CONFIRMATION_SELECTOR,
  INSUFFICIENT_EVIDENCE_COPY,
  caseIdentityMatches,
  isPermissionGateReady,
  reviewIdFromSubmission,
  reviewStartHasCompletedRun,
} from './demo-flow-contracts'
import {
  loginAs,
} from './login-boundary-diagnostics'

const execAsync = promisify(exec)
const frontendWorkingDirectory = resolve(import.meta.dirname, '../..')

type AssistantQuestionPayload = {
  assistant_session_id: string
  answer_status: string
  answer?: string
  citations: unknown[]
}

type AssistantConversationPayload = {
  conversation_id: string
  case_id: string
  review_id: string | null
  finding_id: string | null
  workspace: string | null
}

type ReviewDetailPayload = {
  case: {
    case_id: string
    case_no: string
  }
  review: {
    review_id: string
  }
}

type HistoryDetailPayload = {
  case: {
    case_id: string
    case_no: string
  }
}

type PermissionAction = 'revoke' | 'restore'

type ResponseLike = Awaited<ReturnType<Page['waitForResponse']>>

type SafeAnswerStep = 'PRE_SUBMISSION' | 'RESTORED'
type SafeAnswerAspect = 'STATUS' | 'CITATIONS' | 'COPY' | 'UI'

const ASSISTANT_DENIED_STATUS_FAILURE = 'ASSISTANT_DENIED_STATUS'
const ASSISTANT_DENIED_NO_SIDE_EFFECT_FAILURE = 'ASSISTANT_DENIED_NO_SIDE_EFFECT'

function assistantFailureCode(step: SafeAnswerStep, aspect: SafeAnswerAspect): string {
  return `ASSISTANT_${step}_${aspect}`
}

async function withAssistantFailureTag(
  step: SafeAnswerStep,
  aspect: SafeAnswerAspect,
  assertion: () => Promise<void> | void,
): Promise<void> {
  try {
    await assertion()
  } catch {
    throw new Error(assistantFailureCode(step, aspect))
  }
}

const demo = {
  caseId: process.env.E2E_CASE_ID ?? '',
  caseNo: process.env.E2E_CASE_NO ?? '',
  formId: process.env.E2E_F03_FORM_ID ?? '',
  knowledgeAnswerProvider: (process.env.KNOWLEDGE_ANSWER_PROVIDER ?? 'evidence_only').trim().toLowerCase(),
  permissionGateEnabled: process.env.E2E_PERMISSION_GATE_ENABLED === 'true',
  permissionCode: process.env.E2E_PERMISSION_CODE ?? '',
  permissionOperatorCommand: process.env.E2E_PERMISSION_OPERATOR_COMMAND ?? '',
  appraiser: {
    username: process.env.E2E_APPRAISER_USERNAME ?? '',
    password: process.env.E2E_APPRAISER_PASSWORD ?? '',
  },
  reviewer: {
    username: process.env.E2E_REVIEWER_USERNAME ?? '',
    password: process.env.E2E_REVIEWER_PASSWORD ?? '',
  },
  inspector: {
    username: process.env.E2E_INSPECTOR_USERNAME ?? '',
    password: process.env.E2E_INSPECTOR_PASSWORD ?? '',
  },
}

const TRUE_NO_SOURCE_QUESTION = '量子泡沫黑洞磁場是否影響木星環？'

const e2eAppOrigin = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
const diagnosticApiBaseUrl = process.env.VITE_API_BASE_URL?.startsWith('http')
  ? process.env.VITE_API_BASE_URL
  : `${e2eAppOrigin}${process.env.VITE_API_BASE_URL || '/api/v1'}`

const requiredPersistentInputs = [
  demo.caseId,
  demo.caseNo,
  demo.formId,
  demo.appraiser.username,
  demo.appraiser.password,
  demo.reviewer.username,
  demo.reviewer.password,
  demo.inspector.username,
  demo.inspector.password,
]

const persistentInputsReady = requiredPersistentInputs.every(Boolean)
const permissionGateReady = isPermissionGateReady({
  enabled: demo.permissionGateEnabled,
  command: demo.permissionOperatorCommand,
  permission: demo.permissionCode,
})

const providerBacked = new Set(['codex_cli', 'bedrock']).has(demo.knowledgeAnswerProvider)
const ollamaBacked = demo.knowledgeAnswerProvider === 'ollama'

let sharedAssistantSessionId = ''

async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: '開啟使用者選單' }).click()
  await page.getByRole('menuitem', { name: '登出' }).click()
  await expect(page).toHaveURL(/\/$/)
}

async function submitPreparedValuation(page: Page): Promise<string> {
  await page.goto(`/app/valuation/cases/${encodeURIComponent(demo.caseId)}/calculation`)
  await expect(page.getByTestId('case-context')).toContainText(demo.caseNo)
  const runButton = page.getByTestId('run-valuation')
  await expect(runButton).toBeEnabled()
  await runButton.click()
  await expect(page.getByText('已完成計算、檢核、比準地地價估計表確認與單表輸出。')).toBeVisible()

  await expect(page.getByTestId('go-to-submit')).toBeEnabled()
  await Promise.all([
    page.waitForURL(new RegExp(`/app/valuation/cases/${encodeURIComponent(demo.caseId)}/report$`)),
    page.getByTestId('go-to-submit').click(),
  ])

  await expect(page.getByTestId('report-package-draft-flow')).toBeVisible()
  await page.getByTestId('open-report-page-editors').click()
  await expect(page.getByTestId('report-page-s01-confirm')).toBeVisible()
  await page.getByTestId('report-page-s01-confirm').check()
  await page.getByTestId('report-next-page').click()
  await expect(page.getByTestId('report-page-f02-rf-confirm')).toBeVisible()
  await page.getByTestId('report-page-f02-rf-confirm').check()
  await page.getByTestId('report-next-page').click()
  await expect(page.getByTestId('report-page-f02-confirm')).toBeVisible()
  await page.getByTestId('report-page-f02-confirm').check()
  const savedPages = ['/S01', '/F02-RF', '/F02'].map((pageCode) => page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'PATCH'
      && path.includes(`/valuation/cases/${encodeURIComponent(demo.caseId)}/reports/`)
      && path.endsWith(`/pages${pageCode}`)
  }))
  await page.getByTestId('save-report-pages').click()
  await Promise.all(savedPages)

  const formalCalculationResponse = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST'
      && path.includes(`/valuation/cases/${encodeURIComponent(demo.caseId)}/reports/`)
      && path.endsWith('/formal-calculation')
  })
  await page.getByTestId('run-formal-calculation').click()
  expect((await formalCalculationResponse).ok()).toBeTruthy()

  const reportPageValidationResponse = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST'
      && path.includes(`/valuation/cases/${encodeURIComponent(demo.caseId)}/reports/`)
      && path.endsWith('/formal-validation')
  })
  await page.getByTestId('run-report-formal-validation').click()
  const reportPageValidation = await reportPageValidationResponse
  expect(reportPageValidation.status()).toBe(201)
  const authoritativePackage = page.getByTestId('report-package-authoritative')
  await expect(authoritativePackage).toContainText('查估書內容已完成確認')
  await expect(authoritativePackage).toContainText('F02 第')

  await expect(page.getByTestId('formal-validation-result')).toBeVisible()

  const warningCheckboxes = page.locator('input[data-testid^="formal-warning-"]')
  for (let index = 0; index < await warningCheckboxes.count(); index += 1) {
    const checkbox = warningCheckboxes.nth(index)
    if (!(await checkbox.isChecked())) await checkbox.check()
  }

  const formalPdfResponse = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST'
      && path.includes(`/valuation/cases/${encodeURIComponent(demo.caseId)}/reports/`)
      && path.endsWith('/formal-pdf')
  })
  await page.getByTestId('generate-formal-pdf').click()
  const formalPdf = await formalPdfResponse
  expect(formalPdf.status()).toBe(201)
  await expect(page.getByTestId('formal-pdf-result')).toBeVisible()

  const submitButton = page.getByTestId('submit-for-review')
  await expect(submitButton).toBeEnabled()
  const submissionResponse = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'POST'
      && path.endsWith(`/valuation/cases/${encodeURIComponent(demo.caseId)}/submit-for-review`)
  })
  await submitButton.click()
  const response = await submissionResponse
  expect(response.status()).toBe(201)
  const reviewId = reviewIdFromSubmission(await response.json())
  await expect(page.getByTestId('submission-result')).toBeVisible()
  return reviewId
}

function isAssistantConversationCreateResponse(response: ResponseLike): boolean {
  return response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/knowledge/conversations')
}

function isAssistantQuestionResponse(response: ResponseLike, conversationId: string): boolean {
  const path = new URL(response.url()).pathname
  return response.request().method() === 'POST'
    && path.endsWith(`/knowledge/conversations/${encodeURIComponent(conversationId)}/messages`)
}

async function openAssistantSession(page: Page, conversationId?: string): Promise<string> {
  const conversationResponse = page.waitForResponse((response) => {
    if (conversationId) {
      return response.request().method() === 'GET'
        && new URL(response.url()).pathname.endsWith(`/knowledge/conversations/${encodeURIComponent(conversationId)}/messages`)
    }
    return isAssistantConversationCreateResponse(response)
  })
  const query = new URLSearchParams({ caseId: demo.caseId, workspace: 'valuation' })
  if (conversationId) query.set('conversationId', conversationId)
  await page.goto(`/app/assistant?${query.toString()}`)
  const response = await conversationResponse
  expect(response.ok()).toBeTruthy()
  let resolvedConversationId = conversationId ?? ''
  if (!conversationId) {
    const payload = await response.json() as AssistantConversationPayload
    expect(payload.case_id).toBe(demo.caseId)
    expect(payload.review_id).toBeNull()
    expect(payload.finding_id).toBeNull()
    expect(payload.workspace).toBe('valuation')
    expect(payload.conversation_id).toBeTruthy()
    resolvedConversationId = payload.conversation_id
  }
  await expect(page.getByTestId('assistant-context')).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`conversationId=${encodeURIComponent(resolvedConversationId)}`))
  await expect(page.getByTestId('assistant-question')).toBeEnabled()
  return resolvedConversationId
}

async function askAssistantQuestion(page: Page, conversationId: string, question: string): Promise<{
  response: ResponseLike
  payload: AssistantQuestionPayload
}> {
  const questionResponse = page.waitForResponse((response) => isAssistantQuestionResponse(response, conversationId))
  await page.getByTestId('assistant-question').fill(question)
  await page.getByTestId('assistant-submit').click()
  const response = await questionResponse
  const payload = response.status() === 403
    ? { assistant_session_id: conversationId, answer_status: '', citations: [] }
    : { ...(await response.json()), assistant_session_id: conversationId } as AssistantQuestionPayload
  return { response, payload }
}

async function askAssistantQuestionDirect(
  page: Page,
  conversationId: string,
  question: string,
): Promise<APIResponse> {
  const accessToken = await page.evaluate(() => window.sessionStorage.getItem('lva-demo-access-token'))
  expect(accessToken).toBeTruthy()
  return page.request.post(
    `${diagnosticApiBaseUrl}/knowledge/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        question,
        case_id: demo.caseId,
        review_id: null,
        finding_id: null,
        workspace: 'valuation',
      },
    },
  )
}

async function expectSafeAssistantRefusal(
  page: Page,
  payload: AssistantQuestionPayload,
  step: SafeAnswerStep,
  allowedStatuses: readonly string[] = ['EVIDENCE_ONLY'],
): Promise<void> {
  await withAssistantFailureTag(step, 'STATUS', () => {
    expect(allowedStatuses).toContain(payload.answer_status)
  })
  await withAssistantFailureTag(step, 'CITATIONS', () => {
    expect(payload.citations).toHaveLength(0)
  })
  const latestAnswer = page.getByTestId('assistant-answer').last()
  await withAssistantFailureTag(step, 'COPY', () => expect(
    latestAnswer.getByTestId('assistant-insufficient'),
  ).toHaveText(new RegExp(String.raw`^\s*${INSUFFICIENT_EVIDENCE_COPY}\s*$`)))
  await withAssistantFailureTag(step, 'UI', async () => {
    await expect(latestAnswer.locator('button[data-testid^="assistant-citation-"]')).toHaveCount(0)
    await expect(latestAnswer.locator('[data-testid^="assistant-citation-panel-"]')).toHaveCount(0)
  })
}

async function expectNonStrictProviderOutcome(
  page: Page,
  payload: AssistantQuestionPayload,
  step: SafeAnswerStep,
): Promise<void> {
  if (!ollamaBacked) {
    await expectSafeAssistantRefusal(page, payload, step)
    return
  }

  if (payload.answer_status === 'SUPPORTED') {
    await withAssistantFailureTag(step, 'CITATIONS', () => {
      expect(payload.citations.length).toBeGreaterThan(0)
    })
    await withAssistantFailureTag(step, 'UI', async () => {
      const latestAnswer = page.locator('article[data-testid="assistant-answer"]:visible').last()
      await expect(latestAnswer).toBeVisible()
      await expect(latestAnswer.getByTestId('assistant-insufficient')).toHaveCount(0)
      await expect(
        latestAnswer.locator('button[data-testid^="assistant-citation-"]'),
      ).toHaveCount(payload.citations.length)
    })
    return
  }

  await expectSafeAssistantRefusal(
    page,
    payload,
    step,
    ['EVIDENCE_ONLY', 'NO_RELEVANT_SOURCE', 'CLARIFICATION_REQUIRED'],
  )
}

async function expectAssistantPermissionDenied(
  response: APIResponse,
): Promise<void> {
  try {
    expect(response.status()).toBe(403)
  } catch {
    throw new Error(ASSISTANT_DENIED_STATUS_FAILURE)
  }
}

async function expectNoRelevantSourceRefusal(page: Page, payload: AssistantQuestionPayload): Promise<void> {
  expect(payload.answer_status).toBe('NO_RELEVANT_SOURCE')
  expect(payload.citations).toHaveLength(0)
  const latestAnswer = page.getByTestId('assistant-answer').last()
  await expect(latestAnswer.getByTestId('assistant-insufficient')).toHaveText(new RegExp(String.raw`^\s*${INSUFFICIENT_EVIDENCE_COPY}\s*$`))
  await expect(latestAnswer.locator('button[data-testid^="assistant-citation-"]')).toHaveCount(0)
  await expect(latestAnswer.locator('[data-testid^="assistant-citation-panel-"]')).toHaveCount(0)
}

async function askAndVerifyCitation(page: Page, sessionId?: string): Promise<string> {
  const assistantSessionId = await openAssistantSession(page, sessionId)
  const { response, payload } = await askAssistantQuestion(page, assistantSessionId, '請說明目前案件的估價依據。')
  expect(response.ok()).toBeTruthy()
  expect(payload.assistant_session_id).toBe(assistantSessionId)
  if (providerBacked) {
    expect(payload.answer_status).toBe('SUPPORTED')
    expect(payload.citations.length).toBeGreaterThan(0)

    await expect(page.getByTestId('assistant-answer')).toBeVisible()
    await page.getByTestId('assistant-citation-1').click()
    await expect(page.getByTestId('assistant-citation-panel-1')).toBeVisible()

    const { response: noSource, payload: noSourcePayload } = await askAssistantQuestion(page, assistantSessionId, TRUE_NO_SOURCE_QUESTION)
    expect(noSource.ok()).toBeTruthy()
    expect(noSourcePayload.assistant_session_id).toBe(assistantSessionId)
    await expectNoRelevantSourceRefusal(page, noSourcePayload)
  } else {
    await expectNonStrictProviderOutcome(page, payload, 'PRE_SUBMISSION')
  }
  return assistantSessionId
}

async function reviewAndFinalize(page: Page, reviewId: string): Promise<void> {
  const reviewResponse = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'GET'
      && path.endsWith(`/review/workbench/cases/${encodeURIComponent(reviewId)}`)
  })
  await page.goto(`/app/review/workbench/${encodeURIComponent(reviewId)}`)
  const response = await reviewResponse
  expect(response.ok()).toBeTruthy()
  const payload = await response.json() as ReviewDetailPayload
  expect(payload.review.review_id).toBe(reviewId)
  expect(caseIdentityMatches(payload.case, { caseId: demo.caseId, caseNo: demo.caseNo })).toBe(true)
  await expect(page.getByTestId('review-workbench')).toBeVisible()
  await expect(page.getByTestId('review-workbench')).toContainText(demo.caseNo)

  const startButton = page.getByTestId('start-review')
  await expect(startButton).toBeVisible()
  const preflightResponse = page.waitForResponse((candidate) => {
    const path = new URL(candidate.url()).pathname
    return candidate.request().method() === 'POST'
      && path.endsWith(`/review/workbench/cases/${encodeURIComponent(reviewId)}/start/preflight`)
  })
  const startResponse = page.waitForResponse((candidate) => {
    const path = new URL(candidate.url()).pathname
    return candidate.request().method() === 'POST'
      && path.endsWith(`/review/workbench/cases/${encodeURIComponent(reviewId)}/start`)
  })
  await startButton.click()
  const preflight = await preflightResponse
  expect(preflight.status()).toBe(200)
  const started = await startResponse
  expect(started.status()).toBe(200)
  expect(reviewStartHasCompletedRun(await started.json())).toBe(true)
  await expect(startButton).toHaveCount(0)

  while (true) {
    const openFindings = page.locator('[data-testid^="finding-select-"]').filter({ hasText: '待處理' })
    const openCount = await openFindings.count()
    if (openCount === 0) break
    await openFindings.first().click()
    await page.locator('#finding-decision').selectOption('DISMISSED_FALSE_POSITIVE')
    await page.getByTestId('finding-reason').fill('依據檢核規則結果完成判定。')
    const triageResponse = page.waitForResponse((candidate) => {
      const path = new URL(candidate.url()).pathname
      return candidate.request().method() === 'POST' && /\/review\/findings\/[^/]+\/triage$/.test(path)
    })
    await page.getByTestId('save-finding-decision').click()
    const triage = await triageResponse
    expect(triage.status()).toBe(201)
    await expect(page.locator('[data-testid^="finding-select-"]').filter({ hasText: '待處理' })).toHaveCount(openCount - 1)
  }

  const finalize = page.getByTestId('finalize-review')
  await expect(finalize).toBeEnabled()
  await finalize.click()
  await expect(page.locator(FINALIZE_CONFIRMATION_SELECTOR)).toBeVisible()
  await page.locator(FINALIZE_CONFIRMATION_SELECTOR).click()
  await expect(page.getByTestId('review-action-bar')).toContainText('已完成審查')
}

async function expectHistoryOutcome(page: Page): Promise<void> {
  await page.goto('/app/history/search')
  await page.getByTestId('history-keyword').fill(demo.caseNo)
  await page.getByTestId('history-search-submit').click()
  const row = page.getByTestId(`history-case-row-${demo.caseId}`)
  await expect(row).toContainText(demo.caseNo)

  const detailResponse = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname
    return response.request().method() === 'GET'
      && path.endsWith(`/history/cases/${encodeURIComponent(demo.caseId)}`)
  })
  await row.getByTestId(`history-open-${demo.caseId}`).click()
  const response = await detailResponse
  expect(response.ok()).toBeTruthy()
  const payload = await response.json() as HistoryDetailPayload
  expect(caseIdentityMatches(payload.case, { caseId: demo.caseId, caseNo: demo.caseNo })).toBe(true)
  await expect(page).toHaveURL(new RegExp(`/app/history/cases/${demo.caseId}`))
  await expect(page.getByTestId('history-case')).toBeVisible()
  await expect(page.locator('.history-case__identity-meta')).toContainText(demo.caseNo)
}

async function invokePermissionOperator(action: PermissionAction): Promise<void> {
  if (!permissionGateReady) {
    throw new Error('Permission operator gate is not ready; provide the documented development-only command and permission code.')
  }
  await execAsync(demo.permissionOperatorCommand, {
    env: {
      ...process.env,
      E2E_PERMISSION_ACTION: action,
      E2E_PERMISSION_CODE: demo.permissionCode.trim(),
    },
    cwd: frontendWorkingDirectory,
    windowsHide: true,
    maxBuffer: 1024 * 1024,
  })
}

test.describe('persistent three-role four-subsystem Demo (no route mocks)', () => {
  test.describe.configure({ mode: 'serial' })

  test('Assistant evidence is collected before the persistent case submission', async ({ page }, testInfo) => {
    test.skip(
      !persistentInputsReady,
      'BLOCKED: set the documented persistent Demo credentials and case/form IDs before running this real journey.',
    )

    await loginAs(page, 'APPRAISER', demo.appraiser, testInfo, {
      apiBaseUrl: diagnosticApiBaseUrl,
      appOrigin: e2eAppOrigin,
    })
    sharedAssistantSessionId = await askAndVerifyCitation(page)
    await logout(page)
  })

  test('Assistant permission revocation blocks the next question, then the case completes', async ({ page }, testInfo) => {
    test.skip(
      !persistentInputsReady || !permissionGateReady || !sharedAssistantSessionId,
      'BLOCKED: enable E2E_PERMISSION_GATE_ENABLED=true and provide the documented approved operator command, permission code, and persistent Demo inputs before running this real acceptance.',
    )

    await loginAs(page, 'APPRAISER', demo.appraiser, testInfo, {
      apiBaseUrl: diagnosticApiBaseUrl,
      appOrigin: e2eAppOrigin,
    })
    const sessionId = await openAssistantSession(page, sharedAssistantSessionId)
    const assistantUrl = page.url()

    let restoreRequired = false
    try {
      const answersBeforeDenied = await page.locator('.assistant-conversation').getByTestId('assistant-answer').count()
      expect(answersBeforeDenied).toBeGreaterThan(0)
      restoreRequired = true
      await invokePermissionOperator('revoke')
      const denied = await askAssistantQuestionDirect(page, sessionId, '請依現行法規再次確認本案的估價依據是否適用。')
      await expectAssistantPermissionDenied(denied)
      await page.reload()
      await expect(page).toHaveURL(assistantUrl)
      await expect(page.getByTestId('assistant-question')).toBeEnabled()
      try {
        await expect(page.locator('.assistant-conversation').getByTestId('assistant-answer')).toHaveCount(answersBeforeDenied)
      } catch {
        throw new Error(ASSISTANT_DENIED_NO_SIDE_EFFECT_FAILURE)
      }
      await invokePermissionOperator('restore')
      restoreRequired = false
      await page.goto(assistantUrl)
      await expect(page).toHaveURL(assistantUrl)
      await expect(page.getByTestId('assistant-question')).toBeEnabled()
      try {
        await expect(page.locator('.assistant-conversation').getByTestId('assistant-answer')).toHaveCount(answersBeforeDenied)
      } catch {
        throw new Error(ASSISTANT_DENIED_NO_SIDE_EFFECT_FAILURE)
      }
      const restored = await askAssistantQuestion(page, sessionId, '權限恢復後請依現行法規再次確認本案的估價依據是否適用。')
      expect(restored.response.ok()).toBeTruthy()
      expect(restored.payload.assistant_session_id).toBe(sessionId)
      if (providerBacked) {
        expect(restored.payload.answer_status).toBe('SUPPORTED')
        expect(restored.payload.citations.length).toBeGreaterThan(0)
      } else {
        await expectNonStrictProviderOutcome(page, restored.payload, 'RESTORED')
      }
      await expect(page).toHaveURL(assistantUrl)
    } finally {
      if (restoreRequired) await invokePermissionOperator('restore')
    }

    const reviewId = await submitPreparedValuation(page)
    await logout(page)

    await loginAs(page, 'REVIEWER', demo.reviewer, testInfo, {
      apiBaseUrl: diagnosticApiBaseUrl,
      appOrigin: e2eAppOrigin,
    })
    await reviewAndFinalize(page, reviewId)
    await logout(page)

    await loginAs(page, 'INSPECTOR', demo.inspector, testInfo, {
      apiBaseUrl: diagnosticApiBaseUrl,
      appOrigin: e2eAppOrigin,
    })
    await expectHistoryOutcome(page)
  })
})
