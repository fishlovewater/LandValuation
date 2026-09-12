<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
  mapFormalValidationResponse,
  mapTemplateExportResponse,
  mapFormResponse,
  mapSubmitForReviewResult,
  selectAuthoritativeF02,
} from '../valuation.mappers'
import {
  resetValuationFlow,
  valuationFlowState,
  type ReportPageCode,
  type ReportPageResponseDto,
} from '../valuation.types'
import ComparisonSetupPanel from '../components/ComparisonSetupPanel.vue'
import ReportPageEditor from '../components/ReportPageEditor.vue'
import ValuationIssueDrawer from '../components/ValuationIssueDrawer.vue'
import ValuationStepNavigator from '../components/ValuationStepNavigator.vue'

const route = useRoute()
const router = useRouter()
const flow = valuationFlowState
const loading = ref(false)
const submitting = ref(false)
const formalValidating = ref(false)
const error = ref('')
const refreshWarning = ref('')
const submitRequestId = ref<string | null>(null)
const reportPageDraftId = ref<string | null>(null)
const reportPageEditors = ref<Partial<Record<ReportPageCode, ReportPageResponseDto>>>({})
const reportPageEditorsLoading = ref(false)
const reportPageEditorSaving = ref<ReportPageCode | null>(null)
const activeReportPageCode = ref<ReportPageCode>('S01')
const editorNotice = ref('')
const downloadingDocumentId = ref<string | null>(null)
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
const templateOutputReady = computed(() => flow.templateExports.length >= 3)
const excelSubmissionReady = computed(() => Boolean(
  templateOutputReady.value &&
  flow.formalValidation?.validationRunId &&
  flow.formalValidation.runStatus === "COMPLETED",
))
const currentStep = computed<5 | 6>(() => excelSubmissionReady.value || flow.submission ? 6 : 5)
const canSubmit = computed(() => Boolean(
  templateOutputReady.value &&
  flow.authoritativeF02 &&
  flow.reportPackageId &&
  expectedCaseVersion.value !== null &&
  !flow.submission &&
  !formalValidating.value,
))
const activeReportPage = computed(() => reportPageEditors.value[activeReportPageCode.value] ?? null)
const submitIssues = computed(() => {
  if (flow.templateExports.length) return []
  return [{
    id: 'template-exports',
    title: '尚未產生 Excel 範本',
    detail: '按「產生 Excel 範本」即可將已確認資料寫入範本；缺少資料會保留空白。',
    target: 'formal-validation',
    severity: 'pending' as const,
  }]
})
const readinessMessage = computed(() => {
  if (!flow.authoritativeF02) return "尚未取得案件版本資訊。"
  if (!flow.reportPackageId) return "尚未建立 Excel 產出資料包。"
  if (!templateOutputReady.value) return "請先產生六份 Excel 成果。"
  if (!flow.formalValidation) return "Excel 已產生，正在建立送審追蹤資料。"
  if (flow.formalValidation.runStatus !== "COMPLETED") return "送審追蹤資料尚未完成。"
  return "六份 Excel 已準備完成，可以送審。"
})
function reportPageLabel(code: ReportPageCode): string {
  return ({ S01: '勘查資料（S01）', 'F02-RF': '影響因素（F02-RF）', F02: '比較法資料（F02）' } as Record<ReportPageCode, string>)[code]
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

function isCurrentCase(token: number, requestedCaseId: string): boolean {
  return token === activeCaseToken && requestedCaseId === caseId.value
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
    editorNotice.value = '三頁資料已載入。可選擇修改並逐頁儲存，或直接略過並產生 Excel 範本。'
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) reportPageEditorsLoading.value = false
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
    flow.formalValidation = null
    flow.formalReport = null
    flow.templateExports = []
    editorNotice.value = `${value.pageCode} 已儲存。資料已儲存；需要時可繼續修改其他頁面，Excel 輸出會保留空白欄位。`
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
  flow.formalValidation = null
  flow.formalReport = null
  editorNotice.value = '比較法設定已變更。F02 / F02-RF 已重新載入；可直接產生 Excel 範本，未填資料會保留空白。'
}

function goBackToGeneralFinding(fieldPath: string | null): void {
  const query = fieldPath === 'documents' || fieldPath === 'object_key'
    ? { focus: 'documents' }
    : fieldPath ? { field: fieldPath } : undefined
  void router.push({ name: 'valuation-prepare', params: { caseId: caseId.value }, query })
}


async function loadData(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = ++activeCaseToken
  const sameCase = flow.case?.caseId === requestedCaseId
  const previousReportPackageId = flow.reportPackageId
  if (!sameCase) {
    resetValuationFlow()
    submitRequestId.value = null
  }
  submitting.value = false
  formalValidating.value = false
  reportPageDraftId.value = null
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
    const [caseDto, formDtos, documentDtos, initialReportProgressDto] = await Promise.all([
      valuationApi.getCase(requestedCaseId),
      valuationApi.listForms(requestedCaseId),
      valuationApi.listDocuments(requestedCaseId),
      valuationApi.getReportProgress(requestedCaseId),
    ])
    if (!isCurrentCase(token, requestedCaseId)) return

    let reportProgressDto = initialReportProgressDto
    if (!reportProgressDto.report_id) {
      await valuationApi.createReportPackage(requestedCaseId, {
        report_type: 'REPORT_COMPARISON_COMMERCIAL',
      })
      const [createdForms, createdProgress] = await Promise.all([
        valuationApi.listForms(requestedCaseId),
        valuationApi.getReportProgress(requestedCaseId),
      ])
      formDtos.splice(0, formDtos.length, ...createdForms)
      reportProgressDto = createdProgress
      editorNotice.value = '已自動建立 Excel 範本資料包；可直接產生三份範本，缺少資料會保留空白。'
    }

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
      flow.templateExports = []
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
      if (
        restoredValidation &&
        (restoredValidation.caseId !== requestedCaseId ||
          restoredValidation.reportId !== reportProgressDto.report_id)
      ) {
        error.value = "送審追蹤狀態與目前案件或報告包不一致。"
      } else {
        flow.formalValidation = restoredValidation
        flow.formalReport = null
        flow.templateExports = formalStatus.template_exports.map(mapTemplateExportResponse)
      }
    }
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) loading.value = false
  }
}

async function downloadOutput(documentId: string, filename: string): Promise<void> {
  const requestedCaseId = caseId.value
  if (!requestedCaseId || !documentId || downloadingDocumentId.value) return

  downloadingDocumentId.value = documentId
  error.value = ""
  try {
    const blob = await valuationApi.downloadDocument(requestedCaseId, documentId)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
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


async function generateTemplateExports(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  let reportPackageId = flow.reportPackageId
  if (formalValidating.value || submitting.value || !isCurrentCase(token, requestedCaseId)) return

  formalValidating.value = true
  error.value = ""
  refreshWarning.value = ""
  try {
    if (!reportPackageId) {
      const createdPackage = await valuationApi.createReportPackage(requestedCaseId, {
        report_type: "REPORT_COMPARISON_COMMERCIAL",
      })
      if (!isCurrentCase(token, requestedCaseId)) return
      reportPackageId = createdPackage.report_id
      flow.reportPackageId = reportPackageId
    }
    const templateDtos = await valuationApi.generateTemplateExports(requestedCaseId, reportPackageId)
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.templateExports = templateDtos.map(mapTemplateExportResponse)
    const validationDto = await valuationApi.formalValidate(requestedCaseId, reportPackageId)
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.formalValidation = mapFormalValidationResponse(validationDto)
    flow.formalReport = null
    editorNotice.value = '已產生 ' + flow.templateExports.length + ' 份 Excel 成果；空白欄位保留空白，送審時會直接交給第二系統審查。'
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) formalValidating.value = false
  }
}

async function submitForReview(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const authoritativeF02 = flow.authoritativeF02
  const sourceTemplateDocumentIds = flow.templateExports.map((item) => item.documentId)
  const sourceValidationRunId = flow.formalValidation?.validationRunId ?? flow.validation?.validationRunId
  if (
    submitting.value ||
    formalValidating.value ||
    flow.submission ||
    !flow.case ||
    !authoritativeF02 ||
    !flow.reportPackageId ||
    !templateOutputReady.value ||
    expectedCaseVersion.value === null ||
    !sourceTemplateDocumentIds.length ||
    !sourceValidationRunId ||
    !isCurrentCase(token, requestedCaseId)
  ) return

  submitting.value = true
  error.value = ""
  refreshWarning.value = ""
  try {
    const requestId = submitRequestId.value ?? createValuationRequestId()
    submitRequestId.value = requestId
    const result = await valuationApi.submitForReview(requestedCaseId, {
      request_id: requestId,
      expected_case_version: authoritativeF02.versionNo,
      source_validation_run_id: sourceValidationRunId,
      source_report_document_id: sourceTemplateDocumentIds[0],
      source_template_document_ids: sourceTemplateDocumentIds,
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
      eyebrow="送審確認"
      title="送審確認"
      description="確認 Excel 成果已產生後，再送交第二系統審查。"
    />
    <ValuationIssueDrawer
      v-if="flow.case"
      :items="submitIssues"
      @select="focusSubmitTarget"
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
          <div><span>案件資料</span><strong>已載入目前案件</strong></div>
          <div><span>F02 正式版本</span><strong>{{ flow.authoritativeF02 ? `第 ${flow.authoritativeF02.versionNo} 版` : '尚未取得' }}</strong></div>
          <div><span>Excel 成果</span><strong>{{ flow.templateExports.length ? '已產生 ' + flow.templateExports.length + ' 份' : '尚未產生' }}</strong></div>
          <div><span>檢核狀態</span><strong>{{ flow.validation ? '已執行' : '尚未執行' }}</strong></div>
          <div><span>送審準備</span><strong>{{ readinessMessage }}</strong></div>
        </div>
      </section>

      <section v-if="reportPageDraftId" v-liquid-glass data-lg class="valuation-surface report-package-flow lg" data-testid="report-package-draft-flow" aria-labelledby="report-package-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">選填資料</p>
            <h2 id="report-package-title">選填：查估書三頁資料</h2>
          </div>
          <span class="value-kind">可略過</span>
        </div>
        <div v-if="flow.authoritativeF02" class="package-authoritative" data-testid="report-package-authoritative">
          <strong>已建立 Excel 範本資料包</strong>
          <span>F02 第 {{ flow.authoritativeF02.versionNo }} 版</span>
        </div>
        <template v-else>
          <p class="empty-copy">此區為選填：可檢視或修改 S01、F02-RF、F02，也可直接按下方「產生 Excel 範本」；未填欄位會保留空白。</p>
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
                  {{ reportPageLabel(pageCode) }}
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

        </template>
      </section>

      <section v-if="flow.validation" v-liquid-glass data-lg class="valuation-surface lg" data-testid="submit-validation" aria-labelledby="submit-validation-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">檢核結果</p>
            <h2 id="submit-validation-title">檢核與未解決項目</h2>
          </div>
          <span class="value-kind" :data-validation-state="flow.validation.canGenerateReport ? 'ready' : 'blocked'">
            {{ flow.validation.canGenerateReport ? '可以產出' : '仍有待修正項目' }}
          </span>
        </div>
        <div class="validation-counts">
          <span>通過 {{ flow.validation.passedCount }}</span>
          <span>警示 {{ flow.validation.warningCount }}</span>
          <span>錯誤 {{ flow.validation.failedCount }}</span>
        </div>
        <ul v-if="flow.validation.findings.length" class="finding-list">
          <li v-for="finding in flow.validation.findings" :key="finding.findingId" :data-severity="finding.severity">
            <strong>保留給第二系統確認</strong>
            <span>{{ finding.message }}</span>
            <small>實際值：{{ finding.actualValue ?? '—' }}</small>
            <small>預期值：{{ finding.expectedValue ?? '—' }}</small>
            <button class="finding-action" type="button" @click="goBackToGeneralFinding(finding.fieldPath)">返回資料確認修正</button>
          </li>
        </ul>
        <p v-else class="empty-copy">目前沒有其他需要處理的檢核項目。</p>
        <p v-if="blockers.length" class="blocker-note">仍有 {{ blockers.length }} 項待修正內容，請回到資料確認頁處理。</p>
      </section>

      <section v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="template-export-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">Excel 範本輸出</p>
            <h2 id="template-export-title">產生 Excel 範本</h2>
          </div>
          <span class="value-kind" data-validation-state="ready">可直接產生</span>
        </div>
        <p class="empty-copy">表3 會依宗地數量各產生一份；表4 與表5-1 合併所有地點，並把前段選擇的比準地放入比準地欄位。AI 已擷取或人工填寫的資料會帶入，未填欄位維持空白。產出後可直接送交第二系統審查。</p>
        <div class="formal-actions">
          <button
            class="solid-button"
            type="button"
            data-testid="generate-template-exports"
            :disabled="formalValidating || submitting"
            @click="generateTemplateExports"
          >
            {{ formalValidating ? 'Excel 範本產生中…' : '產生 Excel 範本' }}
          </button>
        </div>
      </section>
      <section v-if="flow.templateExports.length" v-liquid-glass data-lg class="valuation-surface lg" data-testid="template-excel-results" aria-labelledby="template-excel-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">範本成果</p>
            <h2 id="template-excel-title">Excel 範本成果</h2>
          </div>
          <span class="source-marker" data-source-kind="calculated">依目前已確認資料產生</span>
        </div>
        <p class="empty-copy">每個宗地各有一份表3；表4與表5-1彙整全部地點，前段選擇的比準地會置於比準地欄位。沒有資料的儲存格保留空白，另附「AI欄位對應」頁。</p>
        <div class="artifact-list">
          <div v-for="item in flow.templateExports" :key="item.documentId" class="artifact-card">
            <strong>{{ item.title }}</strong>
            <span>{{ item.filename }}｜第 {{ item.versionNo }} 版｜{{ Math.max(1, Math.round(item.fileSizeBytes / 1024)) }} KB</span>
            <button
              class="solid-button artifact-card__download"
              type="button"
              :disabled="Boolean(downloadingDocumentId)"
              @click="downloadOutput(item.documentId, item.filename)"
            >
              {{ downloadingDocumentId === item.documentId ? '下載中…' : '下載 ' + item.formCode + ' Excel' }}
            </button>
          </div>
        </div>
      </section>

      <section v-if="flow.report" v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="artifact-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">流程附件</p>
            <h2 id="artifact-title">F03 單表輸出（流程附件）</h2>
          </div>
          <span class="source-marker" data-source-kind="calculated">系統產生</span>
        </div>
        <div class="artifact-card">
          <strong>{{ flow.report.filename }}</strong>
          <span>第 {{ flow.report.versionNo }} 版｜檔案大小 {{ Math.max(1, Math.round(flow.report.fileSizeBytes / 1024)) }} KB</span>
          <small>這是前段 F03 計算產生的單表輸出，保留作流程追溯；送審以六份 Excel 成果為主。</small>
          <button
            class="solid-button artifact-card__download"
            type="button"
            data-testid="download-f03-report"
            :disabled="Boolean(downloadingDocumentId)"
            @click="downloadOutput(flow.report.documentId, flow.report.filename)"
          >
            {{ downloadingDocumentId === flow.report.documentId ? '下載中…' : '下載 F03 單表' }}
          </button>
        </div>
      </section>

      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <p v-if="refreshWarning" class="inline-notice" role="status">{{ refreshWarning }}</p>

      <section v-liquid-glass data-lg class="submit-bar lg" aria-label="送審操作">
        <div>
          <strong>{{ flow.submission ? '案件已送出審查' : readinessMessage }}</strong>
          <p v-if="flow.submission">送審時間：{{ formatDateZhTw(flow.submission.submittedAt) }}</p>
          <p v-else>六份 Excel 成果產生後即可送出審查。</p>
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
.artifact-card__download { justify-self: start; margin-top: 8px; }
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
