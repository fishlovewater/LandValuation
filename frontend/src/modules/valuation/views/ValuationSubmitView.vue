<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { statusLabel } from '../../../utils/enumLabels'
import { formatDateZhTw } from '../../../utils/formatters'
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
import ComparisonSetupPanel from '../components/ComparisonSetupPanel.vue'
import ReportPageEditor from '../components/ReportPageEditor.vue'
import ValuationStepNavigator from '../components/ValuationStepNavigator.vue'

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
const REPORT_PAGE_CODES: readonly ReportPageCode[] = ['S01', 'F02-RF', 'F02']
let activeCaseToken = 0

const caseId = computed(() => String(route.params.caseId ?? ''))
const blockers = computed(
  () => flow.validation?.findings.filter((finding) => finding.severity === 'ERROR') ?? [],
)
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
const currentStep = computed<5 | 6>(() => formalOutputReady.value || flow.submission ? 6 : 5)
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
const activeReportPage = computed(() => reportPageEditors.value[activeReportPageCode.value] ?? null)
const readinessMessage = computed(() => {
  if (!flow.authoritativeF02) return '尚未取得 F02 最終表單，無法建立權威送審來源。'
  if (!flow.reportPackageId) return 'F02 尚未提供正式報告包識別碼。'
  if (!flow.completeReport && !flow.formalReport) return '尚未找到啟用中的完整估價報告文件，無法送審。'
  if (flow.validation && !flow.validation.canGenerateReport) return '送審動作依伺服器檢核結果暫停。'
  if (flow.validation && !flow.report) return '尚未取得伺服器正式輸出。'
  if (expectedCaseVersion.value === null) return '尚未取得權威 F02 版本，無法建立送審命令。'
  if (!flow.formalValidation) return '請先執行 F02 正式檢核。'
  if (!flow.formalValidation.canGenerateFormalReport) return 'F02 正式檢核回傳阻擋項目，暫停送審。'
  if (!warningsAcknowledged.value) return '請逐項確認正式檢核警示後產生 PDF。'
  if (!flow.formalReport) return '請先產生正式六頁 PDF。'
  if (!formalOutputReady.value) return '正式 PDF 或 F02 FINAL 狀態尚未完成，暫停送審。'
  return '伺服器已提供可送審的正式輸出。'
})

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
    editorNotice.value = '三頁草稿已由伺服器載入。可修改後逐頁儲存，再進行三頁確認、正式計算與檢核。'
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
    await router.push({
      name: 'valuation-prepare',
      params: { caseId: caseId.value },
      query: { focus: 'documents' },
    })
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
    editorNotice.value = `${finding.code}：正式規則版本由伺服器依案件適用範圍自動選用。若沒有可用的 PUBLISHED / VERIFIED 規則，需由規則管理流程處理，估價人員不應手動輸入 UUID。`
    return
  }
  if (!Object.keys(reportPageEditors.value).length) await loadReportPageEditors()
  if (target.comparison) {
    activeReportPageCode.value = 'F02'
    await nextTick()
    const setup = document.querySelector<HTMLElement>('[data-testid="comparison-setup"]')
    setup?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    setup?.focus?.()
    editorNotice.value = `${finding.code}：請在「比較法設定」建立或套用可追溯的比較分析；不需要手動修改比較分析 ID 或 raw JSON。`
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
  editorNotice.value = `${finding.code}：請在 ${target.pageCode}${target.field ? ` 的 ${target.field}` : ''} 修正後儲存，再重新計算與檢核。`
}

function goBackToGeneralFinding(fieldPath: string | null): void {
  const query = fieldPath === 'documents' || fieldPath === 'object_key'
    ? { focus: 'documents' }
    : fieldPath ? { field: fieldPath } : undefined
  void router.push({ name: 'valuation-prepare', params: { caseId: caseId.value }, query })
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
      error.value = '三頁正式檢核與目前報告包不一致，暫停正式輸出。'
      return
    }
    flow.formalValidation = formalValidation
    flow.formalReport = null
    acknowledgedWarningCodes.value = []
    if (!result.can_generate_formal_report) {
      error.value = '三頁正式檢核仍有阻擋項目，請依伺服器結果補正。'
      return
    }
    if (!(await refreshAuthoritativePackage(token, requestedCaseId))) {
      error.value = '三頁檢核已回傳，但尚未取得 CHECKED 權威 F02。'
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
    formalPdfRequestId.value = null
  }
  submitting.value = false
  formalValidating.value = false
  formalPdfGenerating.value = false
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

      if (
        restoredValidation &&
        (restoredValidation.caseId !== requestedCaseId ||
          restoredValidation.reportId !== reportProgressDto.report_id)
      ) {
        error.value = '正式檢核狀態與目前案件或報告包不一致，暫停正式輸出。'
      } else if (formalStatus.requires_revalidation_for_submission) {
        flow.formalValidation = restoredValidation
        flow.formalReport = null
        acknowledgedWarningCodes.value = []
        refreshWarning.value = '既有正式檢核缺少送審所需的不可變輸入快照，請重新執行正式計算與檢核。'
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
          error.value = 'F02 正式檢核回傳阻擋項目，請先完成補正。'
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
  acknowledgedWarningCodes.value = []
  try {
    const formalValidationDto = await valuationApi.formalValidate(requestedCaseId, reportPackageId)
    if (!isCurrentCase(token, requestedCaseId)) return
    const formalValidation = mapFormalValidationResponse(formalValidationDto)
    if (formalValidation.reportId !== reportPackageId) {
      error.value = 'F02 正式檢核與目前報告包不一致，暫停正式輸出。'
      return
    }
    flow.formalValidation = formalValidation
    if (!formalValidation.canGenerateFormalReport) {
      error.value = 'F02 正式檢核回傳阻擋項目，請先完成補正。'
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
      error.value = '請先逐項確認所有正式檢核 WARNING，不能由系統代為確認。'
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
      error.value = '正式 PDF 回傳的案件、報告或檢核批次不一致，暫停送審。'
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
    const result = await valuationApi.submitForReview(requestedCaseId, {
      request_id: requestId,
      expected_case_version: authoritativeF02.versionNo,
      source_validation_run_id: formalReport.validationRunId,
      source_report_document_id: formalReport.documentId,
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
    if (isDefinitiveValuationError(caught)) submitRequestId.value = null
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
    <ValuationStepNavigator :current-step="currentStep" />
    <PageHeader
      eyebrow="SUBMIT FOR REVIEW"
      title="送審確認"
      description="送審命令只帶入伺服器回傳的檢核、正式輸出與版本資訊；前端不自行判定或計算門檻。"
    />

    <LoadingSkeleton v-if="loading" :rows="6" label="送審資料載入中" />
    <ErrorState v-else-if="error && !flow.case" :message="error" @retry="loadData" />

    <template v-else-if="flow.case">
      <section v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="submit-summary-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">案件與輸出</p>
            <h2 id="submit-summary-title">{{ flow.case.caseNo }}｜{{ flow.case.name }}</h2>
          </div>
          <span class="source-marker" :data-status="flow.submission?.caseStatus ?? flow.case.status">案件狀態：{{ displayedCaseStatus }}</span>
        </div>
        <div class="summary-grid">
          <div><span>案件來源</span><strong>伺服器案件資料</strong></div>
          <div><span>F02 權威版本</span><strong>{{ flow.authoritativeF02 ? `第 ${flow.authoritativeF02.versionNo} 版` : '尚未取得' }}</strong></div>
          <div><span>完整估價報告</span><strong>{{ flow.formalReport?.filename || flow.completeReport?.filename || '尚未找到啟用文件' }}</strong></div>
          <div><span>檢核批次</span><strong>{{ flow.validation?.validationRunId || '尚未執行' }}</strong></div>
          <div><span>送審準備</span><strong>{{ readinessMessage }}</strong></div>
        </div>
      </section>

      <section v-if="reportPageDraftId" v-liquid-glass data-lg class="valuation-surface report-package-flow lg" data-testid="report-package-draft-flow" aria-labelledby="report-package-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">REPORT PACKAGE DRAFT</p>
            <h2 id="report-package-title">完整查估書三頁確認</h2>
          </div>
          <span class="value-kind">報告包：{{ reportPageDraftId }}</span>
        </div>
        <div v-if="flow.authoritativeF02" class="package-authoritative" data-testid="report-package-authoritative">
          <strong>三頁已完成伺服器正式檢核</strong>
          <span>F02 第 {{ flow.authoritativeF02.versionNo }} 版｜權威識別碼：{{ flow.reportPackageId }}</span>
        </div>
        <template v-else>
          <p class="empty-copy">先檢視或修改 S01、F02-RF、F02，再逐頁確認。修改後必須重新保存確認、正式計算與檢核。</p>
          <div class="report-page-editor-shell">
            <button
              v-if="!Object.keys(reportPageEditors).length"
              class="solid-button"
              type="button"
              data-testid="open-report-page-editors"
              :disabled="reportPageEditorsLoading"
              @click="loadReportPageEditors"
            >
              {{ reportPageEditorsLoading ? '三頁載入中…' : '檢視／修改三頁資料' }}
            </button>
            <template v-else>
              <nav class="report-page-tabs" aria-label="三頁表單切換">
                <button
                  v-for="pageCode in REPORT_PAGE_CODES"
                  :key="pageCode"
                  type="button"
                  :class="{ 'is-active': activeReportPageCode === pageCode }"
                  :aria-current="activeReportPageCode === pageCode ? 'page' : undefined"
                  @click="activeReportPageCode = pageCode"
                >
                  {{ pageCode }}
                </button>
              </nav>
              <ComparisonSetupPanel
                v-if="activeReportPageCode === 'F02' && reportPageEditors.F02 && reportPageDraftId"
                :case-id="caseId"
                :report-id="reportPageDraftId"
                :page="reportPageEditors.F02"
                @changed="handleComparisonChanged"
              />
              <ReportPageEditor
                v-if="activeReportPage"
                :page="activeReportPage"
                :saving="reportPageEditorSaving === activeReportPageCode"
                @save="saveReportPageEditor"
              />
            </template>
            <p v-if="editorNotice" class="editor-notice" role="status">{{ editorNotice }}</p>
          </div>
          <div class="package-confirmations">
            <label><input v-model="reportPageConfirmations.s01" data-testid="report-page-s01-confirm" type="checkbox" /> 我已確認 S01 勘查資料與來源</label>
            <label><input v-model="reportPageConfirmations.f02Rf" data-testid="report-page-f02-rf-confirm" type="checkbox" /> 我已確認 F02-RF 全部因素級距</label>
            <label><input v-model="reportPageConfirmations.f02" data-testid="report-page-f02-confirm" type="checkbox" /> 我已確認 F02 比較標的與權重</label>
          </div>
          <div class="formal-actions">
            <button class="solid-button" type="button" data-testid="save-report-pages" :disabled="!reportPagesConfirmed || reportPageSaving || reportPageCalculating || reportPageValidating" @click="saveReportPages">
              {{ reportPageSaving ? '三頁保存中…' : '保存三頁確認' }}
            </button>
            <button class="solid-button" type="button" data-testid="run-formal-calculation" :disabled="!reportPageSaved || reportPageCalculating || reportPageValidating" @click="calculateReportPages">
              {{ reportPageCalculating ? '正式計算中…' : '執行正式計算' }}
            </button>
            <button class="solid-button solid-button--primary" type="button" data-testid="run-report-formal-validation" :disabled="!reportPageCalculated || reportPageValidating" @click="validateReportPages">
              {{ reportPageValidating ? '三頁正式檢核中…' : '執行三頁正式檢核' }}
            </button>
          </div>
        </template>
      </section>

      <section v-if="flow.validation" v-liquid-glass data-lg class="valuation-surface lg" data-testid="submit-validation" aria-labelledby="submit-validation-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">SERVER RESULT</p>
            <h2 id="submit-validation-title">檢核與未解決項目</h2>
          </div>
          <span class="value-kind" :data-validation-state="flow.validation.canGenerateReport ? 'ready' : 'blocked'">
            {{ flow.validation.canGenerateReport ? '伺服器允許產出' : '伺服器回傳阻擋' }}
          </span>
        </div>
        <div class="validation-counts">
          <span>通過 {{ flow.validation.passedCount }}</span>
          <span>警示 {{ flow.validation.warningCount }}</span>
          <span>錯誤 {{ flow.validation.failedCount }}</span>
        </div>
        <ul v-if="flow.validation.findings.length" class="finding-list">
          <li v-for="finding in flow.validation.findings" :key="finding.findingId" :data-severity="finding.severity">
            <strong>{{ finding.severity === 'ERROR' ? '阻擋' : '警示' }}｜{{ finding.ruleCode }}</strong>
            <span>{{ finding.message }}</span>
            <small>實際值：{{ finding.actualValue ?? '—' }}</small>
            <small>預期值（expected）：{{ finding.expectedValue ?? '—' }}</small>
            <button class="finding-action" type="button" @click="goBackToGeneralFinding(finding.fieldPath)">返回資料確認修正</button>
          </li>
        </ul>
        <p v-else class="empty-copy">伺服器沒有回傳其他檢核訊息。</p>
        <p v-if="blockers.length" class="blocker-note">仍有 {{ blockers.length }} 項伺服器阻擋項目，請回到資料確認頁處理。</p>
      </section>

      <section v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="formal-validation-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">F02 FORMAL VALIDATION</p>
            <h2 id="formal-validation-title">完整報告正式檢核</h2>
          </div>
          <span v-if="flow.formalValidation" class="value-kind" :data-validation-state="flow.formalValidation.canGenerateFormalReport ? 'ready' : 'blocked'">
            {{ flow.formalValidation.canGenerateFormalReport ? '伺服器允許正式報告' : '伺服器回傳阻擋' }}
          </span>
          <span v-else class="value-kind" data-validation-state="pending">尚未執行</span>
        </div>
        <div v-if="flow.formalValidation" data-testid="formal-validation-result">
          <div class="validation-counts">
            <span>通過 {{ flow.formalValidation.passedCount }}</span>
            <span>警示 {{ flow.formalValidation.warningCount }}</span>
            <span>錯誤 {{ flow.formalValidation.failedCount }}</span>
          </div>
          <ul v-if="flow.formalValidation.findings.length" class="finding-list">
            <li v-for="finding in flow.formalValidation.findings" :key="`${finding.code}-${finding.fieldCode ?? ''}`" :data-severity="finding.severity">
              <strong>{{ finding.severity === 'ERROR' ? '阻擋' : '警示' }}｜{{ finding.code }}</strong>
              <span>{{ finding.message }}</span>
              <small v-if="finding.fieldCode">欄位：{{ finding.fieldCode }}</small>
              <button
                v-if="finding.severity === 'ERROR'"
                class="finding-action"
                type="button"
                :data-testid="`fix-formal-finding-${finding.code}`"
                @click="goToFormalFinding(finding)"
              >
                前往修正
              </button>
              <label v-if="finding.severity === 'WARNING'" class="warning-acknowledgement">
                <input
                  type="checkbox"
                  :data-testid="`formal-warning-${finding.code}`"
                  :checked="acknowledgedWarningCodes.includes(finding.code)"
                  @change="setWarningAcknowledged(finding.code, ($event.target as HTMLInputElement).checked)"
                />
                <span>我已確認此警示，允許產生正式 PDF</span>
              </label>
            </li>
          </ul>
          <p v-else class="empty-copy">正式檢核沒有回傳其他訊息。</p>
          <p v-if="flow.formalValidation.canGenerateFormalReport && formalWarningCodes.length && !warningsAcknowledged" class="blocker-note">
            請逐項確認所有 WARNING 後，才能產生正式 PDF；系統不會代為確認。
          </p>
        </div>
        <p v-else class="empty-copy">正式 PDF 產出前，必須先執行伺服器正式檢核。</p>
        <div class="formal-actions">
          <button
            class="solid-button"
            type="button"
            data-testid="run-formal-validation"
            :disabled="formalValidating || formalPdfGenerating || submitting || !flow.reportPackageId"
            @click="runFormalValidation"
          >
            {{ formalValidating ? '正式檢核中…' : '執行正式檢核' }}
          </button>
          <button
            v-if="flow.formalValidation"
            class="solid-button solid-button--primary"
            type="button"
            data-testid="generate-formal-pdf"
            :disabled="formalPdfGenerating || formalValidating || submitting || !flow.formalValidation.canGenerateFormalReport || !warningsAcknowledged || flow.authoritativeF02?.status !== 'CHECKED'"
            @click="generateFormalPdf"
          >
            {{ formalPdfGenerating ? '正式 PDF 產生中…' : '產生正式六頁 PDF' }}
          </button>
        </div>
      </section>

      <section v-if="flow.formalReport" v-liquid-glass data-lg class="valuation-surface lg" data-testid="formal-pdf-result" aria-labelledby="formal-pdf-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">FORMAL PDF</p>
            <h2 id="formal-pdf-title">正式六頁 PDF</h2>
          </div>
          <span class="source-marker" data-source-kind="calculated">狀態：F02 FINAL</span>
        </div>
        <div class="artifact-card">
          <strong>{{ flow.formalReport.filename }}</strong>
          <span>第 {{ flow.formalReport.versionNo }} 版｜{{ flow.formalReport.mimeType }}｜{{ flow.formalReport.fileSizeBytes }} bytes</span>
          <small>正式 PDF 文件與檢核批次均由伺服器回傳，並作為送審來源。</small>
        </div>
      </section>

      <section v-if="flow.report" v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="artifact-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">AVAILABLE OUTPUT</p>
            <h2 id="artifact-title">正式輸出</h2>
          </div>
          <span class="source-marker" data-source-kind="calculated">來源：伺服器輸出</span>
        </div>
        <div class="artifact-card">
          <strong>{{ flow.report.filename }}</strong>
          <span>第 {{ flow.report.versionNo }} 版｜{{ flow.report.mimeType }}｜{{ flow.report.fileSizeBytes }} bytes</span>
          <small>文件識別碼已由伺服器回傳並用於送審來源追溯。</small>
        </div>
      </section>

      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <p v-if="refreshWarning" class="inline-notice" role="status">{{ refreshWarning }}</p>

      <section v-liquid-glass data-lg class="submit-bar lg" aria-label="送審操作">
        <div>
          <strong>{{ flow.submission ? '案件已送出審查' : readinessMessage }}</strong>
          <p v-if="flow.submission">送審時間：{{ formatDateZhTw(flow.submission.submittedAt) }}</p>
          <p v-else>送審按鈕狀態只依伺服器回傳結果與正式輸出是否存在。</p>
        </div>
        <button
          v-if="!flow.submission"
          class="solid-button solid-button--primary"
          type="button"
          data-testid="submit-for-review"
          :disabled="!canSubmit || submitting"
          @click="submitForReview"
        >
          {{ submitting ? '送審中…' : '送出審查' }}
        </button>
        <div v-else class="submission-complete" data-testid="submission-result" :data-status="flow.submission.caseStatus">
          <strong>第 {{ flow.submission.submissionNo }} 次送審</strong>
          <span>案件狀態：{{ statusLabel(flow.submission.caseStatus) }}</span>
        </div>
      </section>

      <RouterLink class="back-link" :to="{ name: 'valuation-prepare', params: { caseId } }">
        返回資料確認
      </RouterLink>
    </template>
  </div>
</template>

<style scoped>
.valuation-view { display: grid; gap: 18px; padding: 24px 28px 34px; }
.valuation-surface { padding: 22px; border: 1px solid rgba(255,255,255,.72); border-radius: var(--app-radius-md); background: rgba(255,255,255,.72); box-shadow: var(--app-shadow-soft); }
.surface-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.surface-heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; font-weight: 600; letter-spacing: -0.04em; }
.valuation-eyebrow { margin: 0 0 6px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: 0.12em; }
.source-marker, .value-kind { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 10px; border: 1px solid var(--app-line); border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f8fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.source-marker[data-source-kind="calculated"] { border-color: rgba(46, 89, 132, 0.22); color: #2e5984; background: #edf4fb; }
.source-marker:first-letter { color: inherit; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.summary-grid div { display: grid; gap: 5px; padding: 13px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.summary-grid span { color: var(--app-muted); font-size: 11px; font-weight: 800; }
.summary-grid strong { color: var(--app-ink); font-size: 13px; line-height: 1.5; overflow-wrap: anywhere; }
.validation-counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.validation-counts span { padding: 8px 11px; border-radius: 8px; color: var(--app-ink-soft); background: #f5f7fb; font-size: 12px; font-weight: 800; }
.finding-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.finding-list li { display: grid; gap: 4px; padding: 12px 14px; border-left: 4px solid #d6a63e; background: #fffaf0; color: var(--app-ink-soft); font-size: 13px; }
.finding-list li[data-severity="ERROR"] { border-left-color: #c85b43; background: #fff3f0; }
.finding-list strong { color: var(--app-ink); font-size: 12px; }
.finding-action { justify-self: start; min-height: 36px; margin-top: 5px; padding: 6px 11px; border: 1px solid rgba(200,91,67,.26); border-radius: 8px; color: var(--app-accent-deep); background: #fff; cursor: pointer; font-size: 11px; font-weight: 900; }
.package-confirmations { display: grid; gap: 10px; margin: 16px 0; }
.package-confirmations label { display: flex; align-items: flex-start; gap: 8px; color: var(--app-ink); font-size: 13px; font-weight: 700; }
.package-confirmations input { margin-top: 2px; accent-color: var(--app-accent); }
.report-page-editor-shell { display: grid; gap: 12px; margin-top: 16px; }
.report-page-editor-shell > .solid-button { justify-self: start; }
.report-page-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.report-page-tabs button { min-height: 38px; padding: 7px 13px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 12px; font-weight: 900; }
.report-page-tabs button.is-active { border-color: rgba(200,91,67,.32); color: var(--app-accent-deep); background: var(--app-accent-soft); }
.editor-notice { margin: 0; padding: 10px 12px; border-radius: 8px; color: #2e5984; background: #edf4fb; font-size: 12px; line-height: 1.6; }
.package-authoritative { display: grid; gap: 5px; padding: 14px; border: 1px solid rgba(59, 129, 102, 0.24); border-radius: var(--app-radius-sm); color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.package-authoritative span { color: var(--app-ink-soft); font-size: 12px; overflow-wrap: anywhere; }
.warning-acknowledgement { display: flex; align-items: flex-start; gap: 8px; margin-top: 6px; color: var(--app-ink); font-size: 12px; font-weight: 700; }
.warning-acknowledgement input { margin-top: 2px; accent-color: var(--app-accent); }
.empty-copy { margin: 0; color: var(--app-muted); font-size: 13px; }
.blocker-note { margin: 14px 0 0; color: #a44334; font-size: 13px; font-weight: 700; }
.artifact-card { display: grid; gap: 5px; padding: 16px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.artifact-card strong { color: var(--app-ink); font-size: 15px; }
.artifact-card span, .artifact-card small { color: var(--app-ink-soft); font-size: 12px; }
.artifact-card small { color: var(--app-muted); }
.formal-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.submit-bar { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 18px 20px; border: 1px solid rgba(255,255,255,.72); border-radius: var(--app-radius-md); background: rgba(255,250,247,.74); box-shadow: var(--app-shadow-soft); }
.submit-bar strong { color: var(--app-ink); font-size: 15px; }
.submit-bar p { margin: 5px 0 0; color: var(--app-ink-soft); font-size: 12px; }
.solid-button { min-height: 44px; padding: 10px 18px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 13px; font-weight: 800; }
.solid-button--primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.solid-button:disabled { cursor: not-allowed; opacity: 0.55; }
.submission-complete { display: grid; gap: 4px; padding: 10px 14px; border: 1px solid rgba(59, 129, 102, 0.24); border-radius: 9px; color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.submission-complete span { font-size: 12px; }
.inline-error, .inline-notice { margin: 0; padding: 12px 14px; border-radius: var(--app-radius-sm); font-size: 13px; }
.inline-error { color: #a44334; background: #fff0ed; }
.inline-notice { color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.back-link { color: var(--app-accent-deep); font-size: 13px; font-weight: 800; }

@media (max-width: 760px) {
  .valuation-view { padding: 18px 16px 28px; }
  .valuation-surface { padding: 16px; }
  .surface-heading, .submit-bar { align-items: flex-start; flex-direction: column; }
  .summary-grid { grid-template-columns: 1fr; }
  .solid-button { width: 100%; }
  .formal-actions { width: 100%; }
  .report-page-editor-shell > .solid-button { justify-self: stretch; }
}
</style>
