<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { PhArrowLeft as ArrowLeft } from '@phosphor-icons/vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import { statusLabel } from '../../../utils/enumLabels'
import { newTaipeiDistrictName } from '../newTaipei'
import { valuationStageRoute } from '../valuation.navigation'
import {
  createValuationRequestId,
  isDefinitiveValuationError,
  safeValuationErrorMessage,
  valuationApi,
} from '../valuation.api'
import {
  mapCaseResponse,
  mapDocumentResponse,
  mapFormalReportResponse,
  mapFormalValidationResponse,
  mapFormResponse,
  mapSubmitForReviewResult,
  selectAuthoritativeF02,
} from '../valuation.mappers'
import {
  resetValuationFlow,
  valuationFlowState,
  type FormalValidationFindingModel,
  type ReportPageCode,
  type ReportPageResponseDto,
} from '../valuation.types'
import ValuationCaseWorkspaceHeader, { type ValuationWorkspaceStage } from '../components/ValuationCaseWorkspaceHeader.vue'
import ValuationFormalValidationPanel from '../components/ValuationFormalValidationPanel.vue'
import ValuationGeneralValidationPanel from '../components/ValuationGeneralValidationPanel.vue'
import ValuationReportArtifacts from '../components/ValuationReportArtifacts.vue'
import ValuationReportPackageWorkspace from '../components/ValuationReportPackageWorkspace.vue'
import ValuationSubmissionBar from '../components/ValuationSubmissionBar.vue'
import ValuationSubmitReadiness, {
  type SubmitReadinessItem,
  type SubmitReadinessState,
} from '../components/ValuationSubmitReadiness.vue'
import ValuationSubmitSummary from '../components/ValuationSubmitSummary.vue'

const route = useRoute()
const router = useRouter()
const flow = valuationFlowState
const loading = ref(false)
const submitting = ref(false)
const formalValidating = ref(false)
const formalPdfGenerating = ref(false)
const error = ref('')
const refreshWarning = ref('')
const submitRequestId = ref<string | null>(null)
const submitTemplateDocumentIds = ref<string[] | null>(null)
const submitPrimaryTemplateDocumentId = ref<string | null>(null)
const formalPdfRequestId = ref<string | null>(null)
const acknowledgedWarningCodes = ref<string[]>([])
const reportPageDraftId = ref<string | null>(null)
const reportPageSaving = ref(false)
const reportPageCalculating = ref(false)
const reportPageValidating = ref(false)
const reportPageSaved = ref(false)
const reportPageCalculated = ref(false)
const reportPageConfirmations = ref({ s01: false, f02Rf: false, f02: false })
const reportPageEditors = ref<Partial<Record<ReportPageCode, ReportPageResponseDto>>>({})
const reportPageEditorsLoading = ref(false)
const reportPageEditorSaving = ref<ReportPageCode | null>(null)
const activeReportPageCode = ref<ReportPageCode>('S01')
const editorNotice = ref('')
const downloadingDocumentId = ref<string | null>(null)
const downloadingWorkbook = ref(false)
let activeCaseToken = 0

const caseId = computed(() => String(route.params.caseId ?? ''))
const displayedCaseStatus = computed(() =>
  statusLabel(flow.submission?.caseStatus ?? flow.case?.status),
)
// The submit contract uses the authoritative F02 form version exposed by the
// server; without it the command cannot be constructed safely.
const expectedCaseVersion = computed(
  () => flow.authoritativeF02?.versionNo ?? null,
)
const formalWarningCodes = computed(() => Array.from(new Set(
  flow.formalValidation?.findings
    .filter((finding) => finding.severity === 'WARNING')
    .map((finding) => finding.code) ?? [],
)))
const warningsAcknowledged = computed(() => Boolean(
  flow.formalValidation &&
    flow.formalValidation.canGenerateFormalReport &&
    formalWarningCodes.value.every((code) => acknowledgedWarningCodes.value.includes(code)),
))
const formalOutputReady = computed(() => {
  const formalReport = flow.formalReport
  const formalValidation = flow.formalValidation
  const authoritativeF02 = flow.authoritativeF02
  return Boolean(
    formalReport &&
      formalValidation?.canGenerateFormalReport &&
      formalValidation.runStatus === 'COMPLETED' &&
      formalValidation.caseId === caseId.value &&
      formalReport.caseId === caseId.value &&
      formalReport.reportId === flow.reportPackageId &&
      formalReport.validationRunId === formalValidation.validationRunId &&
      formalReport.mimeType === 'application/pdf' &&
      authoritativeF02?.formCode === 'F02' &&
      authoritativeF02.status === 'FINAL' &&
      authoritativeF02.outputDocumentId === formalReport.documentId,
  )
})
const valuationOutputReady = computed(() => Boolean(
  !flow.validation || (flow.validation.canGenerateReport && flow.report),
))
const canSubmit = computed(
  () => Boolean(
    valuationOutputReady.value &&
      flow.authoritativeF02 &&
      (flow.completeReport || flow.formalReport) &&
      flow.reportPackageId &&
      expectedCaseVersion.value !== null &&
      flow.formalValidation?.canGenerateFormalReport &&
      warningsAcknowledged.value &&
      formalOutputReady.value &&
      !flow.submission,
  ),
)
const reportPagesConfirmed = computed(() => {
  const value = reportPageConfirmations.value
  return value.s01 && value.f02Rf && value.f02
})
const submitIssues = computed(() => {
  if (flow.submission) return []
  const items: Array<{ id: string; title: string; detail: string; target: string; severity: 'error' | 'warning' | 'pending' }> = []
  if (!flow.authoritativeF02) {
    items.push({ id: 'report-pages', title: '完整查估書尚未確認完成', detail: '檢視三頁資料、逐頁確認並完成正式計算與檢核。', target: 'report-pages', severity: 'pending' })
  }
  if (flow.formalValidation?.failedCount) {
    items.push({ id: 'formal-errors', title: '正式檢核仍有阻擋項目', detail: `${flow.formalValidation.failedCount} 個錯誤必須修正後才能產生正式 PDF。`, target: 'formal-validation', severity: 'error' })
  } else if (!flow.formalValidation) {
    items.push({ id: 'formal-validation', title: '尚未完成正式檢核', detail: '完成查估書資料後執行正式檢核。', target: 'formal-validation', severity: 'pending' })
  } else if (!warningsAcknowledged.value) {
    items.push({ id: 'formal-warnings', title: '正式檢核警示待人工確認', detail: `還有 ${formalWarningCodes.value.length} 個警示需要人工確認。`, target: 'formal-validation', severity: 'warning' })
  }
  if (!flow.formalReport) {
    items.push({ id: 'formal-pdf', title: '尚未產生正式 PDF', detail: '正式檢核通過後產生送審用完整正式 PDF。', target: 'formal-pdf', severity: 'pending' })
  }
  if (!flow.submission) {
    items.push({ id: 'submission', title: '案件尚未送審', detail: '完整送審 PDF 完成後即可送出審查。', target: 'submission', severity: 'pending' })
  }
  return items
})
const readinessMessage = computed(() => {
  if (!flow.authoritativeF02) return '尚未完成 F02 最終版本，暫時無法送審。'
  if (!flow.reportPackageId) return '完整查估書尚未準備完成。'
  if (!flow.completeReport && !flow.formalReport) return '尚未找到可送審的完整 PDF，無法送審。'
  if (flow.validation && !flow.validation.canGenerateReport) return '目前仍有待修正的檢核項目，暫時無法送審。'
  if (flow.validation && !flow.report) return '尚未產生比準地地價估計表單表輸出。'
  if (expectedCaseVersion.value === null) return '尚未取得可送審的 F02 版本。'
  if (!flow.formalValidation) return '請先執行 F02 正式檢核。'
  if (!flow.formalValidation.canGenerateFormalReport) return 'F02 正式檢核仍有待修正項目，暫時無法送審。'
  if (!warningsAcknowledged.value) return '請逐項確認正式檢核警示後產生 PDF。'
  if (!flow.formalReport) return '請先產生完整送審 PDF。'
  if (!formalOutputReady.value) return '正式 PDF 或 F02 最終版本尚未完成，暫時無法送審。'
  return '完整送審 PDF 已準備完成，可以送審。'
})
const submitReadinessSteps = computed<SubmitReadinessItem[]>(() => {
  const formalValidation = flow.formalValidation
  const validationState: SubmitReadinessState = !formalValidation
    ? (flow.authoritativeF02 ? 'active' : 'pending')
    : formalValidation.failedCount > 0
      ? 'blocked'
      : warningsAcknowledged.value
        ? 'done'
        : 'active'
  const pdfState: SubmitReadinessState = formalOutputReady.value
    ? 'done'
    : formalValidation?.canGenerateFormalReport && warningsAcknowledged.value
      ? 'active'
      : 'pending'
  const submissionState: SubmitReadinessState = flow.submission
    ? 'done'
    : canSubmit.value
      ? 'active'
      : 'pending'
  return [
    {
      key: 'report-pages',
      title: '確認完整查估書',
      detail: flow.authoritativeF02 ? `F02 第 ${flow.authoritativeF02.versionNo} 版已完成` : '確認 S01、F02-RF、F02 三頁資料',
      target: 'report-pages',
      state: flow.authoritativeF02 ? 'done' : 'active',
    },
    {
      key: 'formal-validation',
      title: '完成正式檢核',
      detail: formalValidation
        ? formalValidation.failedCount > 0
          ? `仍有 ${formalValidation.failedCount} 個錯誤待修正`
          : warningsAcknowledged.value
            ? '正式檢核與警示確認已完成'
            : `還有 ${formalWarningCodes.value.length} 個警示待人工確認`
        : '查估書確認後執行正式檢核',
      target: 'formal-validation',
      state: validationState,
    },
    {
      key: 'formal-pdf',
      title: '產生完整送審 PDF',
      detail: flow.formalReport ? flow.formalReport.filename : '正式檢核完成後產生送審文件',
      target: 'formal-pdf',
      state: pdfState,
    },
    {
      key: 'submission',
      title: '送出審查',
      detail: flow.submission ? `第 ${flow.submission.submissionNo} 次送審已完成` : canSubmit.value ? '所有送審條件已完成' : '前述項目完成後即可送審',
      target: 'submission',
      state: submissionState,
    },
  ]
})
const completedSubmitStepCount = computed(() => submitReadinessSteps.value.filter((item) => item.state === 'done').length)
const currentSubmitStep = computed(() => submitReadinessSteps.value.find((item) => item.state !== 'done') ?? null)
const submitProgressPercent = computed(() => Math.min(100, 80 + completedSubmitStepCount.value * 5))
const submitWorkspaceIssueCounts = computed(() => ({
  documents: 0,
  'ai-review': 0,
  data: 0,
  calculation: 0,
  report: submitIssues.value.length,
}))

function reportPageLabel(code: ReportPageCode): string {
  return ({ S01: '勘查資料（S01）', 'F02-RF': '影響因素（F02-RF）', F02: '比較法資料（F02）' } as Record<ReportPageCode, string>)[code]
}

function formalEditorFieldLabel(code: string): string {
  const labels: Readonly<Record<string, string>> = {
    district_name: '行政區',
    district_boundary: '行政區界',
    survey_date: '勘查日期',
    urban_plan_status: '都市計畫狀態',
    land_use_zone: '使用分區',
    building_coverage_rate: '建蔽率',
    floor_area_ratio: '容積率',
    prohibited_building: '禁建狀態',
    restricted_building: '限建狀態',
    main_road_name: '主要道路',
    main_road_width_m: '主要道路寬度',
    average_road_width_m: '平均道路寬度',
    observations: '勘查觀察',
    site_opinion: '現場意見',
    benchmark_land_id: '比準地',
    comparison_analysis_id: '比較分析',
    rule_version_id: '正式計算規則',
    comparison_targets: '比較案例',
    factor_rows: '影響因素',
    other_influences: '其他影響因素',
    benchmark_notes: '比準地說明',
    appraiser_name: '估價人員',
  }
  return labels[code] ?? '查估書資料欄位'
}

function focusSubmitTarget(target: string): void {
  const selectors: Readonly<Record<string, string>> = {
    'report-pages': '[data-testid="report-package-draft-flow"]',
    'formal-validation': '[aria-labelledby="formal-validation-title"]',
    'formal-pdf': '[data-testid="generate-formal-pdf"]',
    submission: '[data-testid="submit-for-review"]',
  }
  const element = document.querySelector<HTMLElement>(selectors[target] ?? '')
  element?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  element?.focus?.()
}

function backToDashboard(): void {
  void router.push({ name: 'valuation-dashboard' })
}

function navigateWorkspaceStage(stage: ValuationWorkspaceStage): void {
  if (stage === 'report') return
  void router.push(valuationStageRoute(caseId.value, stage))
}

function isCurrentCase(token: number, requestedCaseId: string): boolean {
  return token === activeCaseToken && requestedCaseId === caseId.value
}

function recordValue(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function recordList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(recordValue) : []
}

function confirmationNote(value: unknown): string {
  return typeof value === 'string' && value.trim()
    ? value
    : '估價人員依案件來源資料確認。'
}

function saveS01Payload(page: ReportPageResponseDto): Record<string, unknown> {
  const data = page.data
  return {
    ...data,
    observations: recordList(data.observations).map((observation) => ({
      ...observation,
      source_type: 'MANUAL_CONFIRMED',
      source_notes: confirmationNote(observation.source_notes),
      confirmed_by_user: true,
    })),
  }
}

function saveF02RfPayload(page: ReportPageResponseDto): Record<string, unknown> {
  const data = page.data
  return {
    benchmark_land_id: data.benchmark_land_id,
    comparison_analysis_id: data.comparison_analysis_id,
    rule_version_id: data.rule_version_id,
    factor_rows: recordList(data.factor_rows).map((factor) => ({
      ...factor,
      source_notes: confirmationNote(factor.source_notes),
      confirmed_by_user: true,
      targets: recordList(factor.targets).map((target) => ({
        ...target,
        source_notes: confirmationNote(target.source_notes),
        confirmed_by_user: true,
      })),
    })),
    other_influences: data.other_influences,
    notes: data.notes,
    appraiser_name: data.appraiser_name,
  }
}

function saveF02Payload(page: ReportPageResponseDto): Record<string, unknown> {
  const data = page.data
  return {
    benchmark_land_id: data.benchmark_land_id,
    comparison_analysis_id: data.comparison_analysis_id,
    comparison_targets: recordList(data.comparison_targets).map((target) => ({
      ...target,
      weight_confirmed_by_user: true,
      weight_reason: confirmationNote(target.weight_reason),
      individual_factors: recordList(target.individual_factors).map((factor) => ({
        ...factor,
        source_notes: confirmationNote(factor.source_notes),
        confirmed_by_user: true,
      })),
    })),
    benchmark_notes: data.benchmark_notes,
    notes: data.notes,
    handler_name: data.handler_name,
    section_head_name: data.section_head_name,
    director_name: data.director_name,
    appraiser_name: data.appraiser_name,
  }
}

async function loadReportPageEditors(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const reportId = reportPageDraftId.value
  if (!reportId || reportPageEditorsLoading.value || !isCurrentCase(token, requestedCaseId)) return

  reportPageEditorsLoading.value = true
  editorNotice.value = ''
  error.value = ''
  try {
    const [s01, f02Rf, f02] = await Promise.all([
      valuationApi.getReportPage(requestedCaseId, reportId, 'S01'),
      valuationApi.getReportPage(requestedCaseId, reportId, 'F02-RF'),
      valuationApi.getReportPage(requestedCaseId, reportId, 'F02'),
    ])
    if (!isCurrentCase(token, requestedCaseId)) return
    reportPageEditors.value = { S01: s01, 'F02-RF': f02Rf, F02: f02 }
    editorNotice.value = '三頁草稿已載入。可修改後逐頁儲存，再進行確認、正式計算與檢核。'
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) reportPageEditorsLoading.value = false
  }
}

function resetPageConfirmation(pageCode: ReportPageCode): void {
  reportPageConfirmations.value = {
    ...reportPageConfirmations.value,
    s01: pageCode === 'S01' ? false : reportPageConfirmations.value.s01,
    f02Rf: pageCode === 'F02-RF' ? false : reportPageConfirmations.value.f02Rf,
    f02: pageCode === 'F02' ? false : reportPageConfirmations.value.f02,
  }
}

function updateReportPageConfirmation(key: 's01' | 'f02Rf' | 'f02', checked: boolean): void {
  reportPageConfirmations.value = {
    ...reportPageConfirmations.value,
    [key]: checked,
  }
}

async function saveReportPageEditor(value: {
  pageCode: ReportPageCode
  payload: Record<string, unknown>
}): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const reportId = reportPageDraftId.value
  if (!reportId || reportPageEditorSaving.value || !isCurrentCase(token, requestedCaseId)) return

  reportPageEditorSaving.value = value.pageCode
  editorNotice.value = ''
  error.value = ''
  try {
    const updated = await valuationApi.updateReportPage(requestedCaseId, reportId, value.pageCode, value.payload)
    if (!isCurrentCase(token, requestedCaseId)) return
    reportPageEditors.value = { ...reportPageEditors.value, [value.pageCode]: updated }
    resetPageConfirmation(value.pageCode)
    reportPageSaved.value = false
    reportPageCalculated.value = false
    flow.formalValidation = null
    flow.formalReport = null
    submitTemplateDocumentIds.value = null
    submitPrimaryTemplateDocumentId.value = null
    acknowledgedWarningCodes.value = []
    editorNotice.value = `${value.pageCode} 已儲存。因輸入已變更，請重新確認本頁並重新執行正式計算與檢核。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) reportPageEditorSaving.value = null
  }
}

async function handleComparisonChanged(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (!isCurrentCase(token, requestedCaseId)) return
  await loadReportPageEditors()
  if (!isCurrentCase(token, requestedCaseId)) return
  reportPageConfirmations.value = {
    ...reportPageConfirmations.value,
    f02Rf: false,
    f02: false,
  }
  reportPageSaved.value = false
  reportPageCalculated.value = false
  flow.formalValidation = null
  flow.formalReport = null
  submitTemplateDocumentIds.value = null
  submitPrimaryTemplateDocumentId.value = null
  acknowledgedWarningCodes.value = []
  editorNotice.value = '比較法設定已變更。F02 / F02-RF 已重新載入；請重新確認兩頁並執行正式計算與檢核。'
}

function formalFindingTarget(finding: FormalValidationFindingModel): {
  pageCode?: ReportPageCode
  field?: string
  documents?: boolean
  calculation?: boolean
  comparison?: boolean
  systemRule?: boolean
} {
  if (finding.fieldCode) {
    const inS01 = new Set([
      'district_name', 'district_boundary', 'survey_date', 'urban_plan_status', 'land_use_zone',
      'building_coverage_rate', 'floor_area_ratio', 'prohibited_building', 'restricted_building',
      'main_road_name', 'main_road_width_m', 'average_road_width_m', 'observations', 'site_opinion',
      'handler_name', 'section_head_name', 'director_name',
    ])
    const inF02Rf = new Set(['factor_rows', 'other_influences'])
    if (['benchmark_land_id', 'comparison_analysis_id', 'comparison_targets'].includes(finding.fieldCode)) {
      return { comparison: true }
    }
    if (finding.fieldCode === 'rule_version_id') return { systemRule: true }
    if (inS01.has(finding.fieldCode)) return { pageCode: 'S01', field: finding.fieldCode }
    if (inF02Rf.has(finding.fieldCode)) return { pageCode: 'F02-RF', field: finding.fieldCode }
    return { pageCode: 'F02', field: finding.fieldCode }
  }
  if (finding.code.startsWith('S01_')) {
    return { pageCode: 'S01', field: finding.code.includes('OBSERVATION') ? 'observations' : undefined }
  }
  if (finding.code === 'FORMAL_RULE_VERSION_INVALID' || finding.code.includes('RULE_VERSION')) {
    return { systemRule: true }
  }
  if (finding.code === 'FORMAL_REFERENCES_REQUIRED') return { comparison: true }
  if (finding.code.startsWith('F02_RF_')) {
    return { pageCode: 'F02-RF', field: 'factor_rows' }
  }
  if (finding.code === 'F02_BENCHMARK_NOTES_MISSING') return { pageCode: 'F02', field: 'benchmark_notes' }
  if (finding.code === 'F02_TARGETS_REQUIRED' || finding.code.includes('COMPARISON')) return { comparison: true }
  if (finding.code === 'APPRAISER_NAME_MISSING') return { pageCode: 'F02', field: 'appraiser_name' }
  if (finding.code.startsWith('FORMAL_MAP_')) return { documents: true }
  if (finding.code.includes('CALCULATION')) return { calculation: true }
  return { pageCode: 'F02' }
}

async function goToFormalFinding(finding: FormalValidationFindingModel): Promise<void> {
  const target = formalFindingTarget(finding)
  if (target.documents) {
    await router.push(valuationStageRoute(caseId.value, 'documents'))
    return
  }
  if (target.calculation) {
    const calculationButton = document.querySelector<HTMLElement>('[data-testid="run-formal-calculation"]')
      ?? document.querySelector<HTMLElement>('[data-testid="run-formal-validation"]')
    calculationButton?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    calculationButton?.focus()
    editorNotice.value = '此問題來自正式計算狀態；請確認輸入資料後重新執行正式計算，再執行正式檢核。'
    return
  }
  if (target.systemRule) {
    editorNotice.value = '正式規則會依案件適用範圍自動選用；若目前沒有可用規則，請由規則管理人員處理。'
    return
  }
  if (!Object.keys(reportPageEditors.value).length) await loadReportPageEditors()
  if (target.comparison) {
    activeReportPageCode.value = 'F02'
    await nextTick()
    const setup = document.querySelector<HTMLElement>('[data-testid="comparison-setup"]')
    setup?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    setup?.focus?.()
    editorNotice.value = '請在「比較法設定」建立或套用可追溯的比較分析。'
    return
  }
  if (!target.pageCode) return
  activeReportPageCode.value = target.pageCode
  await nextTick()
  const editor = document.querySelector<HTMLElement>(`[data-page-code="${target.pageCode}"]`)
  const field = target.field
    ? editor?.querySelector<HTMLElement>(`[data-report-field="${target.field}"]`)
    : editor
  ;(field ?? editor)?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  ;(field ?? editor)?.focus?.()
  const pageLabel = reportPageLabel(target.pageCode)
  const fieldLabel = target.field ? formalEditorFieldLabel(target.field) : ''
  editorNotice.value = `請在「${pageLabel}」${fieldLabel ? `的「${fieldLabel}」` : ''}修正後儲存，再重新計算與檢核。`
}

function goBackToGeneralFinding(fieldPath: string | null): void {
  if (fieldPath === 'documents' || fieldPath === 'object_key') {
    void router.push(valuationStageRoute(caseId.value, 'documents'))
    return
  }
  void router.push(valuationStageRoute(
    caseId.value,
    'data',
    fieldPath ? { field: fieldPath } : undefined,
  ))
}

async function refreshAuthoritativePackage(
  token: number,
  requestedCaseId: string,
): Promise<boolean> {
  const [formDtos, documentDtos, reportProgressDto] = await Promise.all([
    valuationApi.listForms(requestedCaseId),
    valuationApi.listDocuments(requestedCaseId),
    valuationApi.getReportProgress(requestedCaseId),
  ])
  if (!isCurrentCase(token, requestedCaseId)) return false
  const forms = formDtos.map(mapFormResponse)
  const documents = documentDtos.map(mapDocumentResponse)
  const authoritative = selectAuthoritativeF02(forms, documents, reportProgressDto)
  flow.forms = forms
  flow.documents = documents
  flow.authoritativeF02 = authoritative.form
  flow.completeReport = authoritative.completeReport
  flow.reportPackageId = authoritative.reportPackageId
  reportPageDraftId.value = reportProgressDto.report_id
  return Boolean(authoritative.form && authoritative.reportPackageId)
}

async function saveReportPages(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const reportId = reportPageDraftId.value
  if (
    reportPageSaving.value ||
    !reportId ||
    !reportPagesConfirmed.value ||
    !isCurrentCase(token, requestedCaseId)
  ) return

  reportPageSaving.value = true
  error.value = ''
  try {
    const s01 = await valuationApi.getReportPage(requestedCaseId, reportId, 'S01')
    const f02Rf = await valuationApi.getReportPage(requestedCaseId, reportId, 'F02-RF')
    const f02 = await valuationApi.getReportPage(requestedCaseId, reportId, 'F02')
    await valuationApi.updateReportPage(requestedCaseId, reportId, 'S01', saveS01Payload(s01))
    await valuationApi.updateReportPage(requestedCaseId, reportId, 'F02-RF', saveF02RfPayload(f02Rf))
    await valuationApi.updateReportPage(requestedCaseId, reportId, 'F02', saveF02Payload(f02))
    if (!isCurrentCase(token, requestedCaseId)) return
    reportPageSaved.value = true
    reportPageCalculated.value = false
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) reportPageSaving.value = false
  }
}

async function calculateReportPages(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const reportId = reportPageDraftId.value
  if (
    reportPageCalculating.value ||
    !reportId ||
    !reportPageSaved.value ||
    !isCurrentCase(token, requestedCaseId)
  ) return

  reportPageCalculating.value = true
  error.value = ''
  try {
    await valuationApi.calculateFormalReport(requestedCaseId, reportId, { confirm_calculation: true })
    if (!isCurrentCase(token, requestedCaseId)) return
    reportPageCalculated.value = true
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) reportPageCalculating.value = false
  }
}

async function validateReportPages(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const reportId = reportPageDraftId.value
  if (
    reportPageValidating.value ||
    !reportId ||
    !reportPageCalculated.value ||
    !isCurrentCase(token, requestedCaseId)
  ) return

  reportPageValidating.value = true
  error.value = ''
  try {
    const result = await valuationApi.formalValidate(requestedCaseId, reportId)
    if (!isCurrentCase(token, requestedCaseId)) return
    const formalValidation = mapFormalValidationResponse(result)
    if (formalValidation.reportId !== reportId) {
      error.value = '三頁正式檢核與目前查估書版本不一致，請重新執行檢核。'
      return
    }
    flow.formalValidation = formalValidation
    flow.formalReport = null
    acknowledgedWarningCodes.value = []
    if (!result.can_generate_formal_report) {
      error.value = '三頁正式檢核仍有待修正項目，請依檢核結果補正。'
      return
    }
    if (!(await refreshAuthoritativePackage(token, requestedCaseId))) {
      error.value = '三頁檢核已完成，但尚未取得已完成正式檢核的 F02 版本。'
    }
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) reportPageValidating.value = false
  }
}

async function loadData(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = ++activeCaseToken
  const sameCase = flow.case?.caseId === requestedCaseId
  const previousReportPackageId = flow.reportPackageId
  if (!sameCase) {
    resetValuationFlow()
    submitRequestId.value = null
    submitTemplateDocumentIds.value = null
    submitPrimaryTemplateDocumentId.value = null
    formalPdfRequestId.value = null
  }
  submitting.value = false
  formalValidating.value = false
  formalPdfGenerating.value = false
  submitTemplateDocumentIds.value = null
  submitPrimaryTemplateDocumentId.value = null
  acknowledgedWarningCodes.value = []
  reportPageDraftId.value = null
  reportPageSaving.value = false
  reportPageCalculating.value = false
  reportPageValidating.value = false
  reportPageSaved.value = false
  reportPageCalculated.value = false
  reportPageConfirmations.value = { s01: false, f02Rf: false, f02: false }
  reportPageEditors.value = {}
  reportPageEditorsLoading.value = false
  reportPageEditorSaving.value = null
  activeReportPageCode.value = 'S01'
  editorNotice.value = ''
  error.value = ''
  refreshWarning.value = ''

  if (!requestedCaseId) {
    error.value = '找不到案件識別資訊，請從估價案件清單重新進入。'
    loading.value = false
    return
  }

  loading.value = true
  try {
    const [caseDto, formDtos, documentDtos, reportProgressDto] = await Promise.all([
      valuationApi.getCase(requestedCaseId),
      valuationApi.listForms(requestedCaseId),
      valuationApi.listDocuments(requestedCaseId),
      valuationApi.getReportProgress(requestedCaseId),
    ])
    if (!isCurrentCase(token, requestedCaseId)) return

    const forms = formDtos.map(mapFormResponse)
    const documents = documentDtos.map(mapDocumentResponse)
    const authoritative = selectAuthoritativeF02(forms, documents, reportProgressDto)
    flow.case = mapCaseResponse(caseDto)
    flow.forms = forms
    flow.documents = documents
    flow.authoritativeF02 = authoritative.form
    flow.completeReport = authoritative.completeReport
    flow.reportPackageId = authoritative.reportPackageId
    reportPageDraftId.value = reportProgressDto.report_id
    const reportChanged = previousReportPackageId !== flow.reportPackageId
    if (
      reportChanged ||
      (flow.formalValidation &&
        (!flow.reportPackageId || flow.formalValidation.reportId !== flow.reportPackageId))
    ) {
      flow.formalValidation = null
      flow.formalReport = null
      acknowledgedWarningCodes.value = []
      formalPdfRequestId.value = null
    }

    // Page load must be read-only. Restore the latest persisted formal result
    // via the status endpoint instead of creating a new validation run merely
    // because the browser refreshed.
    if (reportProgressDto.report_id) {
      const formalStatus = await valuationApi.getFormalStatus(
        requestedCaseId,
        reportProgressDto.report_id,
      )
      if (!isCurrentCase(token, requestedCaseId)) return
      const restoredValidation = formalStatus.validation
        ? mapFormalValidationResponse(formalStatus.validation)
        : null
      const restoredReport = formalStatus.report
        ? mapFormalReportResponse(formalStatus.report)
        : null
      const existingTemplateExports = formalStatus.template_exports ?? []
      submitTemplateDocumentIds.value = existingTemplateExports.length
        ? existingTemplateExports.map((item) => item.document_id)
        : null
      submitPrimaryTemplateDocumentId.value =
        existingTemplateExports.find((item) => item.form_code === 'F02')?.document_id
        ?? existingTemplateExports[0]?.document_id
        ?? null

      if (
        restoredValidation &&
        (restoredValidation.caseId !== requestedCaseId ||
          restoredValidation.reportId !== reportProgressDto.report_id)
      ) {
        error.value = '正式檢核結果與目前案件或查估書版本不一致，請重新執行檢核。'
      } else if (formalStatus.requires_revalidation_for_submission) {
        flow.formalValidation = restoredValidation
        flow.formalReport = null
        acknowledgedWarningCodes.value = []
        refreshWarning.value = '既有正式檢核資料不完整，無法直接送審；請重新執行正式計算與檢核。'
      } else {
        flow.formalValidation = restoredValidation
        flow.formalReport = restoredReport
        if (restoredReport && restoredValidation) {
          // A persisted formal PDF can only exist after the server accepted
          // every warning acknowledgement for this validation run. Restoring
          // those codes here does not create a new acknowledgement; it merely
          // reflects the already-authorized server result.
          acknowledgedWarningCodes.value = Array.from(new Set(
            restoredValidation.findings
              .filter((finding) => finding.severity === 'WARNING')
              .map((finding) => finding.code),
          ))
        }
        if (restoredValidation && !restoredValidation.canGenerateFormalReport) {
          error.value = 'F02 正式檢核仍有待修正項目，請先完成補正。'
        }
      }
    }
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) loading.value = false
  }
}

function setWarningAcknowledged(code: string, checked: boolean): void {
  const next = new Set(acknowledgedWarningCodes.value)
  if (checked) next.add(code)
  else next.delete(code)
  acknowledgedWarningCodes.value = formalWarningCodes.value.filter((item) => next.has(item))
}

function setFormalFormStatus(status: 'CHECKED' | 'FINAL', outputDocumentId: string | null): void {
  if (!flow.authoritativeF02) return
  const updated = {
    ...flow.authoritativeF02,
    status,
    outputDocumentId,
  }
  flow.authoritativeF02 = updated
  flow.forms = flow.forms.map((form) =>
    form.formInstanceId === updated.formInstanceId ? updated : form,
  )
}

async function downloadOutput(documentId: string, filename: string): Promise<void> {
  const requestedCaseId = caseId.value
  if (!requestedCaseId || !documentId || downloadingDocumentId.value) return

  downloadingDocumentId.value = documentId
  error.value = ''
  try {
    const blob = await valuationApi.downloadDocument(requestedCaseId, documentId)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    downloadingDocumentId.value = null
  }
}

async function downloadFormalWorkbook(): Promise<void> {
  const requestedCaseId = caseId.value
  const reportId = flow.reportPackageId
  if (!requestedCaseId || !reportId || downloadingWorkbook.value) return
  downloadingWorkbook.value = true
  error.value = ''
  try {
    const blob = await valuationApi.downloadFormalWorkbook(requestedCaseId, reportId)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const safeCaseNo = (flow.case?.caseNo || 'case').replace(/[\\/:*?"<>|]+/g, '_')
    const versionNo = flow.formalReport?.versionNo ?? flow.authoritativeF02?.versionNo ?? 1
    anchor.href = url
    anchor.download = `查估資料_${safeCaseNo}_v${versionNo}.xlsx`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    downloadingWorkbook.value = false
  }
}

async function runFormalValidation(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const reportPackageId = flow.reportPackageId
  if (
    formalValidating.value ||
    submitting.value ||
    !reportPackageId ||
    !isCurrentCase(token, requestedCaseId)
  ) return

  formalValidating.value = true
  error.value = ''
  refreshWarning.value = ''
  flow.formalValidation = null
  flow.formalReport = null
  submitTemplateDocumentIds.value = null
  submitPrimaryTemplateDocumentId.value = null
  acknowledgedWarningCodes.value = []
  try {
    const formalValidationDto = await valuationApi.formalValidate(requestedCaseId, reportPackageId)
    if (!isCurrentCase(token, requestedCaseId)) return
    const formalValidation = mapFormalValidationResponse(formalValidationDto)
    if (formalValidation.reportId !== reportPackageId) {
      error.value = 'F02 正式檢核與目前查估書版本不一致，請重新執行檢核。'
      return
    }
    flow.formalValidation = formalValidation
    if (!formalValidation.canGenerateFormalReport) {
      error.value = 'F02 正式檢核仍有待修正項目，請先完成補正。'
      return
    }
    setFormalFormStatus('CHECKED', flow.authoritativeF02?.outputDocumentId ?? null)
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) formalValidating.value = false
  }
}

async function generateFormalPdf(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const formalValidation = flow.formalValidation
  const reportPackageId = flow.reportPackageId
  if (
    formalPdfGenerating.value ||
    submitting.value ||
    !formalValidation ||
    !formalValidation.canGenerateFormalReport ||
    formalValidation.runStatus !== 'COMPLETED' ||
    formalValidation.caseId !== requestedCaseId ||
    formalValidation.reportId !== reportPackageId ||
    !reportPackageId ||
    !warningsAcknowledged.value ||
    flow.authoritativeF02?.status !== 'CHECKED' ||
    !isCurrentCase(token, requestedCaseId)
  ) {
    if (formalValidation && !warningsAcknowledged.value) {
      error.value = '請先逐項確認所有正式檢核警示；系統不會代為確認。'
    }
    return
  }

  formalPdfGenerating.value = true
  error.value = ''
  refreshWarning.value = ''
  const requestId = formalPdfRequestId.value ?? createValuationRequestId()
  formalPdfRequestId.value = requestId
  try {
    const formalReportDto = await valuationApi.generateFormalPdf(requestedCaseId, reportPackageId, {
      confirm_generate: true,
      acknowledged_warning_codes: [...acknowledgedWarningCodes.value],
    }, requestId)
    if (!isCurrentCase(token, requestedCaseId)) return
    formalPdfRequestId.value = null
    const formalReport = mapFormalReportResponse(formalReportDto)
    if (
      formalReport.caseId !== requestedCaseId ||
      formalReport.reportId !== reportPackageId ||
      formalReport.validationRunId !== formalValidation.validationRunId ||
      formalReport.mimeType !== 'application/pdf'
    ) {
      error.value = '正式 PDF 與目前案件或檢核結果不一致，暫時無法送審。請重新產生正式文件。'
      return
    }
    flow.formalReport = formalReport
    setFormalFormStatus('FINAL', formalReport.documentId)
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    if (isDefinitiveValuationError(caught)) formalPdfRequestId.value = null
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) formalPdfGenerating.value = false
  }
}

async function submitForReview(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const authoritativeF02 = flow.authoritativeF02
  const completeReport = flow.completeReport
  const reportPackageId = flow.reportPackageId
  const formalReport = flow.formalReport
  if (
    submitting.value ||
    flow.submission ||
    !flow.case ||
    !valuationOutputReady.value ||
    !authoritativeF02 ||
    !(completeReport || formalReport) ||
    !reportPackageId ||
    !formalReport ||
    expectedCaseVersion.value === null ||
    !formalOutputReady.value ||
    !isCurrentCase(token, requestedCaseId)
  ) return

  submitting.value = true
  error.value = ''
  refreshWarning.value = ''
  try {
    const requestId = submitRequestId.value ?? createValuationRequestId()
    submitRequestId.value = requestId
    let templateDocumentIds = submitTemplateDocumentIds.value
    let primaryTemplateDocumentId = submitPrimaryTemplateDocumentId.value
    if (!templateDocumentIds?.length || !primaryTemplateDocumentId) {
      const templateExports = await valuationApi.generateTemplateExports(requestedCaseId, reportPackageId)
      if (!isCurrentCase(token, requestedCaseId)) return
      templateDocumentIds = templateExports.map((item) => item.document_id)
      primaryTemplateDocumentId =
        templateExports.find((item) => item.form_code === 'F02')?.document_id
        ?? templateExports[0]?.document_id
        ?? null
      if (!templateDocumentIds.length || !primaryTemplateDocumentId) {
        error.value = '正式送審附件未產生，暫時無法送審。請重新產生查估書附件後再試。'
        return
      }
      submitTemplateDocumentIds.value = templateDocumentIds
      submitPrimaryTemplateDocumentId.value = primaryTemplateDocumentId
    }
    const result = await valuationApi.submitForReview(requestedCaseId, {
      request_id: requestId,
      expected_case_version: authoritativeF02.versionNo,
      source_validation_run_id: formalReport.validationRunId,
      source_report_document_id: primaryTemplateDocumentId,
      source_template_document_ids: [...templateDocumentIds],
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    submitRequestId.value = null
    flow.submission = mapSubmitForReviewResult(result)

    try {
      const refreshedCase = await valuationApi.getCase(requestedCaseId)
      if (!isCurrentCase(token, requestedCaseId)) return
      flow.case = mapCaseResponse(refreshedCase)
    } catch {
      if (isCurrentCase(token, requestedCaseId)) {
        refreshWarning.value = '送審結果已回傳；案件最新摘要暫時無法重新載入。'
      }
    }
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    if (isDefinitiveValuationError(caught)) {
      submitRequestId.value = null
      submitTemplateDocumentIds.value = null
      submitPrimaryTemplateDocumentId.value = null
    }
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) submitting.value = false
  }
}

watch(caseId, () => {
  void loadData()
}, { immediate: true })
</script>

<template>
  <div class="valuation-view">
    <LoadingSkeleton v-if="loading" :rows="6" label="送審資料載入中" />
    <ErrorState v-else-if="error && !flow.case" :message="error" @retry="loadData" />

    <template v-else-if="flow.case">
      <ValuationCaseWorkspaceHeader
        :case-model="flow.case"
        :district-label="newTaipeiDistrictName(flow.case.districtCode)"
        :status-label="displayedCaseStatus"
        current-stage="report"
        :progress-percent="submitProgressPercent"
        :issue-counts="submitWorkspaceIssueCounts"
        :report-available="true"
        @back="backToDashboard"
        @navigate="navigateWorkspaceStage"
      />

      <ValuationSubmitSummary
        :case-model="flow.case"
        :authoritative-f02="flow.authoritativeF02"
        :formal-report="flow.formalReport"
        :complete-report="flow.completeReport"
        :validation="flow.validation"
        :readiness-message="readinessMessage"
        :displayed-case-status="displayedCaseStatus"
        :status-value="flow.submission?.caseStatus ?? flow.case.status"
      />

      <ValuationSubmitReadiness
        :steps="submitReadinessSteps"
        :current-step="currentSubmitStep"
        :completed-step-count="completedSubmitStepCount"
        :submitted="Boolean(flow.submission)"
        :readiness-message="readinessMessage"
        @select="focusSubmitTarget"
      />

      <ValuationReportPackageWorkspace
        v-if="reportPageDraftId"
        :case-id="caseId"
        :report-id="reportPageDraftId"
        :authoritative-f02="flow.authoritativeF02"
        :editors="reportPageEditors"
        :active-page-code="activeReportPageCode"
        :editors-loading="reportPageEditorsLoading"
        :editor-saving="reportPageEditorSaving"
        :editor-notice="editorNotice"
        :confirmations="reportPageConfirmations"
        :pages-confirmed="reportPagesConfirmed"
        :page-saving="reportPageSaving"
        :page-calculating="reportPageCalculating"
        :page-validating="reportPageValidating"
        :page-saved="reportPageSaved"
        :page-calculated="reportPageCalculated"
        @load-editors="loadReportPageEditors"
        @update:active-page-code="activeReportPageCode = $event"
        @comparison-changed="handleComparisonChanged"
        @save-editor="saveReportPageEditor"
        @update-confirmation="updateReportPageConfirmation"
        @save-pages="saveReportPages"
        @calculate="calculateReportPages"
        @validate="validateReportPages"
      />

      <ValuationGeneralValidationPanel
        v-if="flow.validation"
        :validation="flow.validation"
        @fix="goBackToGeneralFinding"
      />

      <ValuationFormalValidationPanel
        :validation="flow.formalValidation"
        :formal-warning-codes="formalWarningCodes"
        :acknowledged-warning-codes="acknowledgedWarningCodes"
        :warnings-acknowledged="warningsAcknowledged"
        :formal-validating="formalValidating"
        :formal-pdf-generating="formalPdfGenerating"
        :submitting="submitting"
        :report-package-ready="Boolean(flow.reportPackageId)"
        :authoritative-f02-status="flow.authoritativeF02?.status ?? null"
        @run-validation="runFormalValidation"
        @generate-pdf="generateFormalPdf"
        @fix="goToFormalFinding"
        @acknowledge="setWarningAcknowledged"
      />

      <ValuationReportArtifacts
        :formal-report="flow.formalReport"
        :report="flow.report"
        :downloading-document-id="downloadingDocumentId"
        :downloading-workbook="downloadingWorkbook"
        @download="downloadOutput"
        @download-workbook="downloadFormalWorkbook"
      />

      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <p v-if="refreshWarning" class="inline-notice" role="status">{{ refreshWarning }}</p>

      <ValuationSubmissionBar
        :submission="flow.submission"
        :readiness-message="readinessMessage"
        :can-submit="canSubmit"
        :submitting="submitting"
        @submit="submitForReview"
      />

      <RouterLink class="back-link" :to="valuationStageRoute(caseId, 'data')">
        <ArrowLeft :size="15" weight="bold" aria-hidden="true" />
        <span>返回資料確認</span>
      </RouterLink>
    </template>
  </div>
</template>

<style scoped>
.valuation-view { display: grid; gap: 18px; padding: 0 28px 34px; }
.valuation-view :deep(.case-workspace-header) { margin-inline: -28px; }
.inline-error, .inline-notice { margin: 0; padding: 12px 14px; border-radius: var(--app-radius-sm); font-size: 13px; }
.inline-error { color: #a44334; background: #fff0ed; }
.inline-notice { color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.back-link { display: inline-flex; width: fit-content; align-items: center; gap: 6px; color: var(--app-accent-deep); font-size: 13px; font-weight: 800; }

@media (max-width: 760px) {
  .valuation-view { padding: 18px 16px 28px; }
  .valuation-view :deep(.case-workspace-header) { margin: -18px -16px 0; }
}
</style>
