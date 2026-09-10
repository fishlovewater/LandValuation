import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  FINALIZE_CONFIRMATION_SELECTOR,
  INSUFFICIENT_EVIDENCE_COPY,
  caseIdentityMatches,
  isDocumentedPermissionOperatorCommand,
  isPermissionGateReady,
  reviewIdFromSubmission,
  reviewStartHasCompletedRun,
} from '../e2e/demo-flow-contracts'

describe('persistent Demo browser-flow contracts', () => {
  it('requires the server case ID and case number to match the configured case', () => {
    expect(caseIdentityMatches(
      { case_id: 'case-1', case_no: 'F03-001' },
      { caseId: 'case-1', caseNo: 'F03-001' },
    )).toBe(true)
    expect(caseIdentityMatches(
      { case_id: 'different-case', case_no: 'F03-001' },
      { caseId: 'case-1', caseNo: 'F03-001' },
    )).toBe(false)
    expect(caseIdentityMatches(
      { case_id: 'case-1', case_no: 'different-number' },
      { caseId: 'case-1', caseNo: 'F03-001' },
    )).toBe(false)
  })

  it('requires the explicit permission gate, approved command, and supported permission code', () => {
    const documentedCommand = 'docker compose --project-directory .. -p landvaluation-persistent-demo -f ../docker-compose.yml -f ../docker-compose.demo.yml --env-file ../.env.example exec -T api python -m app.demo permission %E2E_PERMISSION_ACTION% %E2E_PERMISSION_CODE%'
    expect(isPermissionGateReady({ enabled: true, command: documentedCommand, permission: 'knowledge.read' })).toBe(true)
    expect(isDocumentedPermissionOperatorCommand(documentedCommand)).toBe(true)
    expect(isPermissionGateReady({ enabled: false, command: documentedCommand, permission: 'knowledge.read' })).toBe(false)
    expect(isPermissionGateReady({ enabled: true, command: '', permission: 'knowledge.read' })).toBe(false)
    expect(isPermissionGateReady({ enabled: true, command: 'approved-command', permission: 'role:APPRAISER' })).toBe(false)
    expect(isPermissionGateReady({
      enabled: true,
      command: 'docker compose --project-directory .. -p landvaluation-persistent-demo -f ../docker-compose.yml -f ../docker-compose.demo.yml --env-file ../.env.example exec -T api python -m app.demo permission revoke knowledge.read',
      permission: 'knowledge.read',
    })).toBe(false)
    expect(isDocumentedPermissionOperatorCommand(`${documentedCommand} && whoami`)).toBe(false)
    expect(isDocumentedPermissionOperatorCommand(documentedCommand.replace('../docker-compose.demo.yml', '../other-compose.yml'))).toBe(false)
  })

  it('requires a non-empty string review_id from the real submission response', () => {
    expect(reviewIdFromSubmission({ review_id: 'review-1' })).toBe('review-1')
    expect(() => reviewIdFromSubmission({})).toThrow('The real submission response did not provide review_id.')
    expect(() => reviewIdFromSubmission({ review_id: 42 })).toThrow('The real submission response did not provide review_id.')
  })

  it('requires the Review start response to contain a completed run', () => {
    expect(reviewStartHasCompletedRun({
      outcome: 'COMPLETED',
      run: { run_status: 'COMPLETED' },
    })).toBe(true)
    expect(reviewStartHasCompletedRun({ outcome: 'BLOCKED', run: null })).toBe(false)
    expect(reviewStartHasCompletedRun({ outcome: 'COMPLETED', run: { run_status: 'RUNNING' } })).toBe(false)
    expect(reviewStartHasCompletedRun({ outcome: 'COMPLETED' })).toBe(false)
  })

  it('scopes the finalization confirmation action inside the alert dialog', () => {
    expect(FINALIZE_CONFIRMATION_SELECTOR).toBe('[role="alertdialog"] [data-confirm]')
  })

  it('keeps the fixed insufficient-evidence copy exact', () => {
    expect(INSUFFICIENT_EVIDENCE_COPY).toBe('目前沒有足夠的可讀適用來源，無法支持這項回答。')
  })

  it('requires the safe-refusal matcher to allow only surrounding whitespace', () => {
    const source = readFileSync(resolve(import.meta.dirname, '../e2e/demo-flow.spec.ts'), 'utf8')
    expect(source).toContain('new RegExp(String.raw`^\\s*${INSUFFICIENT_EVIDENCE_COPY}\\s*$`)')

    const matcher = new RegExp(String.raw`^\s*${INSUFFICIENT_EVIDENCE_COPY}\s*$`)
    expect(matcher.test(` ${INSUFFICIENT_EVIDENCE_COPY} `)).toBe(true)
    expect(matcher.test(` ${INSUFFICIENT_EVIDENCE_COPY} 額外文字`)).toBe(false)
  })

  it('requires the local seeded-candidate refusal to stay EVIDENCE_ONLY', () => {
    const source = readFileSync(resolve(import.meta.dirname, '../e2e/demo-flow.spec.ts'), 'utf8')
    const helperStart = source.indexOf('async function expectSafeAssistantRefusal')
    const helperEnd = source.indexOf('\n}\n\nasync function askAndVerifyCitation', helperStart)
    const refusalHelper = source.slice(helperStart, helperEnd)
    expect(refusalHelper).toContain("expect(payload.answer_status).toBe('EVIDENCE_ONLY')")
    expect(refusalHelper).not.toContain("expect(['EVIDENCE_ONLY', 'NO_RELEVANT_SOURCE']).toContain(payload.answer_status)")
    const trueNoSourceHelperStart = source.indexOf('async function expectNoRelevantSourceRefusal')
    const trueNoSourceHelperEnd = source.indexOf('\n}\n\nasync function askAndVerifyCitation', trueNoSourceHelperStart)
    const trueNoSourceHelper = source.slice(trueNoSourceHelperStart, trueNoSourceHelperEnd)
    expect(trueNoSourceHelper).toContain("expect(payload.answer_status).toBe('NO_RELEVANT_SOURCE')")

    const citationFlowStart = source.indexOf('async function askAndVerifyCitation')
    const providerBranchStart = source.indexOf('if (providerBacked) {', citationFlowStart)
    const localBranchStart = source.indexOf('} else {', providerBranchStart)
    const citationFlowEnd = source.indexOf('\n  return assistantSessionId', localBranchStart)
    const providerBranch = source.slice(providerBranchStart, localBranchStart)
    const localBranch = source.slice(localBranchStart, citationFlowEnd)

    expect(providerBranch).toContain('askAssistantQuestion(page, assistantSessionId, TRUE_NO_SOURCE_QUESTION)')
    expect(providerBranch).toContain('await expectNoRelevantSourceRefusal(page, noSourcePayload)')
    expect(localBranch).toContain("await expectSafeAssistantRefusal(page, payload, 'PRE_SUBMISSION')")
    expect(localBranch).not.toContain('TRUE_NO_SOURCE_QUESTION')
    expect(localBranch).not.toContain('expectNoRelevantSourceRefusal')
  })

  it('tags every local safe-answer step and aspect without retaining raw assertion data', () => {
    const source = readFileSync(resolve(import.meta.dirname, '../e2e/demo-flow.spec.ts'), 'utf8')
    expect(source).toContain("type SafeAnswerStep = 'PRE_SUBMISSION' | 'BASELINE' | 'RESTORED'")
    expect(source).toContain("type SafeAnswerAspect = 'STATUS' | 'CITATIONS' | 'COPY' | 'UI'")
    expect(source).toContain('function assistantFailureCode(step: SafeAnswerStep, aspect: SafeAnswerAspect)')
    expect(source).toContain('throw new Error(assistantFailureCode(step, aspect))')
    expect(source).not.toContain('error.message')
    expect(source).not.toContain('cause: error')

    for (const aspect of ['STATUS', 'CITATIONS', 'COPY', 'UI']) {
      expect(source).toContain(`withAssistantFailureTag(step, '${aspect}'`)
    }

    expect(source).toContain("await expectSafeAssistantRefusal(page, payload, 'PRE_SUBMISSION')")
    expect(source).toContain("await expectSafeAssistantRefusal(page, initial.payload, 'BASELINE')")
    expect(source).toContain("await expectSafeAssistantRefusal(page, restored.payload, 'RESTORED')")
    expect(source).toContain('await expectAssistantPermissionDenied(page, denied.response)')
    expect(source).not.toContain("await expectSafeAssistantRefusal(page, denied.payload)")
  })

  it('tags denied permission checks with ordered fixed failures without raw assertion details', () => {
    const source = readFileSync(resolve(import.meta.dirname, '../e2e/demo-flow.spec.ts'), 'utf8')
    const helperStart = source.indexOf('async function expectAssistantPermissionDenied')
    const helperEnd = source.indexOf('\n}\n\nasync function expectNoRelevantSourceRefusal', helperStart)
    const helper = source.slice(helperStart, helperEnd)

    expect(source).toContain("const ASSISTANT_DENIED_STATUS_FAILURE = 'ASSISTANT_DENIED_STATUS'")
    expect(source).toContain("const ASSISTANT_DENIED_ALERT_FAILURE = 'ASSISTANT_DENIED_ALERT'")
    expect(source).toContain("const ASSISTANT_DENIED_NO_SIDE_EFFECT_FAILURE = 'ASSISTANT_DENIED_NO_SIDE_EFFECT'")
    expect(helper).toContain('expect(response.status()).toBe(403)')
    expect(helper).toContain("expectAssistantPermissionDenied")
    expect(helper).toContain('toContainText')
    expect(helper).toContain("toHaveCount(1)")
    expect(helper).toContain("await expect(page.locator('.assistant-conversation').getByTestId('assistant-answer')).toHaveCount(1)")
    expect(helper).not.toContain('ASSISTANT_HTTP_403')
    expect(helper).not.toContain('error.message')
    expect(helper).not.toContain('cause: error')

    const failureIndexes = [
      helper.indexOf('throw new Error(ASSISTANT_DENIED_STATUS_FAILURE)'),
      helper.indexOf('throw new Error(ASSISTANT_DENIED_ALERT_FAILURE)'),
      helper.indexOf('throw new Error(ASSISTANT_DENIED_NO_SIDE_EFFECT_FAILURE)'),
    ]
    expect(failureIndexes.every((index) => index >= 0)).toBe(true)
    expect(failureIndexes[0]).toBeLessThan(failureIndexes[1])
    expect(failureIndexes[1]).toBeLessThan(failureIndexes[2])
  })

  it('uses an independent question for the true no-source path', () => {
    const source = readFileSync(resolve(import.meta.dirname, '../e2e/demo-flow.spec.ts'), 'utf8')
    expect(source).toContain("const TRUE_NO_SOURCE_QUESTION = '量子泡沫黑洞磁場是否影響木星環？'")
    expect(source).toContain('askAssistantQuestion(page, assistantSessionId, TRUE_NO_SOURCE_QUESTION)')
    expect(source).not.toContain('askAssistantQuestion(page, assistantSessionId, demo.noSourceQuestion)')
  })

  it('keeps Assistant evidence and permission checks before the real submission', () => {
    const source = readFileSync(resolve(import.meta.dirname, '../e2e/demo-flow.spec.ts'), 'utf8')
    const firstJourneyStart = source.indexOf("test('Assistant evidence is collected before the persistent case submission'")
    const permissionJourneyStart = source.indexOf("test('Assistant permission revocation blocks the next question, then the case completes'")
    expect(firstJourneyStart).toBeGreaterThanOrEqual(0)
    expect(permissionJourneyStart).toBeGreaterThan(firstJourneyStart)

    const firstJourney = source.slice(firstJourneyStart, permissionJourneyStart)
    const assistantEvidenceIndex = firstJourney.indexOf('sharedAssistantSessionId = await askAndVerifyCitation(page)')
    const firstSubmissionIndex = firstJourney.indexOf('await submitPreparedValuation(page)')
    expect(assistantEvidenceIndex).toBeGreaterThanOrEqual(0)
    expect(firstSubmissionIndex).toBe(-1)

    const permissionJourney = source.slice(permissionJourneyStart)
    const flowMarkers = [
      'const sessionId = await openAssistantSession(page, sharedAssistantSessionId)',
      "const initial = await askAssistantQuestion(page, sessionId, '請先確認目前案件的可讀來源。')",
      "expect(initial.payload.answer_status).toBe('SUPPORTED')",
      'expect(initial.payload.citations.length).toBeGreaterThan(0)',
      "await expectSafeAssistantRefusal(page, initial.payload, 'BASELINE')",
      "await invokePermissionOperator('revoke')",
      'await expectAssistantPermissionDenied(page, denied.response)',
      "await invokePermissionOperator('restore')",
      "const restored = await askAssistantQuestion(page, sessionId, '權限恢復後請再次確認目前案件的可讀來源。')",
      'expect(restored.payload.assistant_session_id).toBe(sessionId)',
      'await submitPreparedValuation(page)',
    ]

    let previousMarkerIndex = -1
    for (const marker of flowMarkers) {
      const markerIndex = permissionJourney.indexOf(marker)
      expect(markerIndex, `missing flow marker: ${marker}`).toBeGreaterThan(previousMarkerIndex)
      previousMarkerIndex = markerIndex
    }
  })
})
