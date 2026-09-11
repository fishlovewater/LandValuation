<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { useAuthStore } from '../../../stores/auth.store'
import { statusLabel } from '../../../utils/enumLabels'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import {
  mapBenchmarkLandResponse,
  mapCalculationResponse,
  mapCaseResponse,
  mapDocumentResponse,
  mapF03DraftResponse,
  mapF03Update,
  mapFormResponse,
  mapReportResponse,
  mapValidationResponse,
  selectAuthoritativeF02,
  sourceForCalculatedValue,
} from '../valuation.mappers'
import {
  resetValuationFlow,
  valuationFlowState,
  type AutomatedCandidateConfirmationDto,
  type AutomatedWorkflowResponseDto,
  type BenchmarkLandCreateDto,
  type DocumentCategory,
  type DocumentArtifactModel,
  type ExtractedFieldResponseDto,
  type F03EditableValues,
  type ParcelCreateDto,
  type ParcelResponseDto,
  type ReportPageCode,
  type ReportProgressResponseDto,
  type ValidationFindingModel,
  type ValuationReviewHandoffDto,
  type ValuationFormModel,
} from '../valuation.types'
import ValuationStepNavigator from '../components/ValuationStepNavigator.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const flow = valuationFlowState
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const uploading = ref(false)
const dirty = ref(false)
const error = ref('')
const notice = ref('')
const workflowGuidance = ref<AutomatedWorkflowResponseDto | null>(null)
const reviewHandoff = ref<ValuationReviewHandoffDto | null>(null)
const reportProgress = ref<ReportProgressResponseDto | null>(null)
const revisionInitializing = ref(false)
const uploadCategory = ref<DocumentCategory>('original')
const uploadFile = ref<File | null>(null)
const parcels = ref<ParcelResponseDto[]>([])
const extractionCandidates = ref<ExtractedFieldResponseDto[]>([])
const extractionBusyDocumentId = ref<string | null>(null)
const confirmingCandidates = ref(false)
const candidateDecision = reactive<Record<string, 'CONFIRM' | 'REJECT' | ''>>({})
const candidateValue = reactive<Record<string, string>>({})
const manualFieldValue = reactive<Record<string, string>>({})
const manualFieldsSaving = ref(false)
const documentActionId = ref<string | null>(null)
const documentCategoryDraft = reactive<Record<string, DocumentCategory>>({})
const landContextSaving = ref(false)
const editingParcelId = ref<string | null>(null)
type WizardStep = 1 | 2 | 3 | 4 | 5 | 6
type DataSection = 'overview' | 'manual' | 'land' | 'f03'
const activeWizardStep = ref<WizardStep>(1)
const activeDataSection = ref<DataSection>('overview')
const previewDocumentId = ref<string | null>(null)
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const previewPage = ref<number | null>(null)
const selectedCandidateId = ref<string | null>(null)

const parcelDraft = reactive({
  districtCode: '',
  sectionName: '',
  subsectionName: '',
  landNo: '',
  areaSqm: '',
  landUseZone: '',
  designatedUse: '',
  sourceDocumentId: '',
})

const benchmarkDraft = reactive({
  parcelId: '',
  benchmarkLandNo: '',
  priceZoneNo: '',
  landConsolidationSerial: '',
  latitude: '',
  longitude: '',
})

const draft = reactive<F03EditableValues>({
  benchmarkLandId: null,
  comparisonAnalysisId: null,
  valuationBaseDate: null,
  comparisonPrice: null,
  comparisonWeight: null,
  incomePrice: null,
  incomeWeight: null,
  marketPeriodStart: null,
  marketPeriodEnd: null,
  marketCondition: null,
  selectionScopeReason: null,
  decisionReason: null,
})

const caseId = computed(() => String(route.params.caseId ?? ''))
const f03Form = computed<ValuationFormModel | null>(
  () => flow.forms
    .filter((form) => form.formCode === 'F03')
    .reduce<ValuationFormModel | null>(
      (latest, form) => (!latest || form.versionNo > latest.versionNo ? form : latest),
      null,
    ),
)
const isRevisionRequired = computed(() => reviewHandoff.value?.case_status === 'REVISION_REQUIRED')
const latestReportForms = computed(() => {
  const reportId = reportProgress.value?.report_id
  if (!reportId) return []
  return flow.forms.filter((form) =>
    form.reportId === reportId && ['S01', 'F02-RF', 'F02'].includes(form.formCode),
  )
})
const revisionDraftReady = computed(() => Boolean(
  isRevisionRequired.value
    && f03Form.value?.status === 'DRAFT'
    && reportProgress.value?.report_id
    && latestReportForms.value.length === 3
    && latestReportForms.value.every((form) => form.status === 'DRAFT'),
))
const canEditF03 = computed(() => f03Form.value?.status === 'DRAFT')
const canEditLandContext = computed(() => auth.permissions.includes('case.update'))
type CorrectionItem = NonNullable<ValuationReviewHandoffDto['correction']>['items'][number]
type HandoffMissingItem = ValuationReviewHandoffDto['missing_items'][number]
const formalSupplementMissingItems = computed(() =>
  reviewHandoff.value?.missing_items.filter((item) =>
    item.status === 'OPEN' && ['PENDING', 'SENT', 'ACKNOWLEDGED'].includes(item.notification_status ?? ''),
  ) ?? [],
)
const calculatedSource = sourceForCalculatedValue()
const canUpload = computed(() => auth.permissions.includes('document.upload'))
const canReadAutomatedWorkflow = computed(() => [
  'case.create',
  'case.read',
  'valuation.update',
  'document.upload',
  'document.download',
].every((permission) => auth.permissions.includes(permission)))
const canProceedToSubmit = computed(() => Boolean(flow.validation?.canGenerateReport && flow.report))
const f03Guidance = computed(() => workflowGuidance.value?.form_guidance.find((item) => item.form_code === 'F03') ?? null)
const workflowMissingItems = computed(() => workflowGuidance.value?.missing_items ?? [])
const allCandidates = computed(() => {
  const merged = new Map<string, ExtractedFieldResponseDto>()
  for (const candidate of workflowGuidance.value?.candidates ?? []) {
    merged.set(candidate.extracted_field_id, candidate)
  }
  for (const candidate of extractionCandidates.value) {
    merged.set(candidate.extracted_field_id, candidate)
  }
  return [...merged.values()]
})
const pendingCandidates = computed(() => allCandidates.value.filter(
  (candidate) => candidate.field_status === 'NEEDS_CONFIRMATION',
))
const processedCandidates = computed(() => allCandidates.value.filter(
  (candidate) => ['APPLIED', 'CONFIRMED', 'REJECTED'].includes(candidate.field_status),
))
const candidateDecisionTargets = computed(() => allCandidates.value.filter(
  (candidate) => candidate.field_status === 'NEEDS_CONFIRMATION' || Boolean(candidateDecision[candidate.extracted_field_id]),
))
const selectedCandidateCount = computed(() => candidateDecisionTargets.value.filter(
  (candidate) => Boolean(candidateDecision[candidate.extracted_field_id]),
).length)
const selectedCandidate = computed(() => allCandidates.value.find(
  (candidate) => candidate.extracted_field_id === selectedCandidateId.value,
) ?? null)
const previewDocument = computed(() => flow.documents.find(
  (document) => document.documentId === previewDocumentId.value,
) ?? null)
const previewSourceUrl = computed(() => {
  if (!previewUrl.value) return ''
  if (previewDocument.value?.mimeType.toLowerCase() === 'application/pdf' && previewPage.value) {
    return `${previewUrl.value}#page=${previewPage.value}`
  }
  return previewUrl.value
})
const previewIsPdf = computed(() => previewDocument.value?.mimeType.toLowerCase() === 'application/pdf')
const previewIsImage = computed(() => previewDocument.value?.mimeType.toLowerCase().startsWith('image/') ?? false)
const manualFieldEntries = computed(() => {
  const keys = new Set<string>()
  for (const guidance of workflowGuidance.value?.form_guidance ?? []) {
    for (const field of guidance.missing_required_fields) keys.add(`${guidance.form_code}.${field}`)
  }
  for (const [formCode, fields] of Object.entries(workflowGuidance.value?.manual_field_values ?? {})) {
    for (const field of Object.keys(fields)) keys.add(`${formCode}.${field}`)
  }
  return [...keys].sort().map((key) => {
    const split = key.indexOf('.')
    return { key, formCode: key.slice(0, split), fieldName: key.slice(split + 1) }
  })
})
const dataIssueCounts = computed(() => ({
  overview: (f03Guidance.value?.missing_required_fields.length ?? 0) + (!parcels.value.length ? 1 : 0) + (!flow.benchmarks.length ? 1 : 0),
  manual: manualFieldEntries.value.length,
  land: (!parcels.value.length ? 1 : 0) + (!flow.benchmarks.length ? 1 : 0),
  f03: f03Guidance.value?.missing_required_fields.length ?? 0,
}))
const wizardIssueCounts = computed<Partial<Record<WizardStep, number>>>(() => ({
  2: pendingCandidates.value.length + (!flow.documents.length ? 1 : 0),
  3: dataIssueCounts.value.overview,
  4: flow.validation?.failedCount ?? 0,
}))
const wizardAvailableSteps = computed<number[]>(() => [1, 2, 3, 4, ...(canProceedToSubmit.value ? [5] : [])])
const wizardStepTitle = computed(() => ({
  1: '案件設定',
  2: '文件上傳與 AI 辨識',
  3: '資料確認',
  4: '計算與檢核',
  5: '查估書確認',
  6: '送審',
}[activeWizardStep.value]))
const wizardStepDescription = computed(() => ({
  1: '先確認案件基本資料與目前查估表版本。',
  2: '集中管理來源文件、預覽原文並執行 AI / OCR 辨識，再逐筆確認辨識結果。',
  3: '依待處理狀態確認人工補充、宗地、比準地與 F03 正式採用值。',
  4: '執行伺服器公式計算與正式檢核；若有錯誤可直接跳回對應欄位修正。',
  5: '前往查估書三頁確認與正式 PDF。',
  6: '完成正式送審。',
}[activeWizardStep.value]))
const wizardNextLabel = computed(() => {
  if (activeWizardStep.value === 1) return '下一步：文件與 AI 辨識'
  if (activeWizardStep.value === 2) return pendingCandidates.value.length ? `先處理 ${pendingCandidates.value.length} 筆待確認` : '下一步：資料確認'
  if (activeWizardStep.value === 3) return dataIssueCounts.value.overview ? `尚有 ${dataIssueCounts.value.overview} 項資料待處理` : '下一步：計算與檢核'
  if (activeWizardStep.value === 4) return canProceedToSubmit.value ? '下一步：查估書確認' : '通過檢核後才能繼續'
  return '前往查估書確認'
})
const SOURCE_DOCUMENT_CATEGORIES: readonly DocumentCategory[] = [
  'original',
  'land-register',
  'cadastral-map',
  'photos',
  'attachments',
  'map-section-sketch',
  'map-zoning',
  'map-land-value-section',
]
let activeCaseToken = 0

const FIELD_TARGET_IDS: Readonly<Record<string, string>> = {
  benchmark_land_id: 'f03-benchmark-land',
  valuation_base_date: 'f03-valuation-base-date',
  comparison_price: 'f03-comparison-price',
  comparison_weight: 'f03-comparison-weight',
  income_price: 'f03-income-price',
  income_weight: 'f03-income-weight',
  market_period_start: 'f03-market-period-start',
  market_period_end: 'f03-market-period-end',
  market_condition: 'f03-market-condition',
  selection_scope_reason: 'f03-selection-scope-reason',
  decision_reason: 'f03-decision-reason',
  documents: 'valuation-document-workspace',
  object_key: 'valuation-document-workspace',
  prices: 'f03-comparison-price',
  'case/form/benchmark/date': 'f03-benchmark-land',
  benchmark_land_price: 'run-valuation',
}

const FIELD_LABELS: Readonly<Record<string, string>> = {
  benchmark_land_id: 'F03 → 基準地',
  valuation_base_date: 'F03 → 估價基準日',
  comparison_price: 'F03 → 比較法價格',
  comparison_weight: 'F03 → 比較法權重',
  income_price: 'F03 → 收益法價格',
  income_weight: 'F03 → 收益法權重',
  market_period_start: 'F03 → 市場期間起日',
  market_period_end: 'F03 → 市場期間迄日',
  market_condition: 'F03 → 市場條件',
  selection_scope_reason: 'F03 → 選擇範圍理由',
  decision_reason: 'F03 → 採用決策理由',
  documents: '案件與文件 → 來源文件',
  object_key: '案件與文件 → 來源文件儲存狀態',
  prices: 'F03 → 比較法／收益法價格',
  'case/form/benchmark/date': 'F03 → 基準地與估價基準日',
  benchmark_land_price: 'F03 → 伺服器計算結果',
}

function emptyDraft(): F03EditableValues {
  return {
    benchmarkLandId: null,
    comparisonAnalysisId: null,
    valuationBaseDate: null,
    comparisonPrice: null,
    comparisonWeight: null,
    incomePrice: null,
    incomeWeight: null,
    marketPeriodStart: null,
    marketPeriodEnd: null,
    marketCondition: null,
    selectionScopeReason: null,
    decisionReason: null,
  }
}

function clearReactiveRecord(record: Record<string, unknown>): void {
  for (const key of Object.keys(record)) delete record[key]
}

function resetParcelDraft(): void {
  editingParcelId.value = null
  Object.assign(parcelDraft, {
    districtCode: flow.case?.districtCode ?? '',
    sectionName: '',
    subsectionName: '',
    landNo: '',
    areaSqm: '',
    landUseZone: '',
    designatedUse: '',
    sourceDocumentId: '',
  })
}

function resetBenchmarkDraft(): void {
  Object.assign(benchmarkDraft, {
    parcelId: parcels.value[0]?.parcel_id ?? '',
    benchmarkLandNo: '',
    priceZoneNo: '',
    landConsolidationSerial: '',
    latitude: '',
    longitude: '',
  })
}

function displayCandidateValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

function fieldDisplayLabel(formCode: string, fieldName: string): string {
  if (formCode === 'F03' && FIELD_LABELS[fieldName]) return FIELD_LABELS[fieldName]
  return `${formCode} → ${fieldName.replaceAll('_', ' ')}`
}

function initializeManualFieldInputs(response: AutomatedWorkflowResponseDto): void {
  for (const [formCode, fields] of Object.entries(response.manual_field_values ?? {})) {
    for (const [fieldName, value] of Object.entries(fields)) {
      const key = `${formCode}.${fieldName}`
      if (!(key in manualFieldValue)) manualFieldValue[key] = displayCandidateValue(value)
    }
  }
}

function initializeDocumentCategories(): void {
  for (const document of flow.documents) {
    if (SOURCE_DOCUMENT_CATEGORIES.includes(document.documentType as DocumentCategory)) {
      documentCategoryDraft[document.documentId] = document.documentType as DocumentCategory
    }
  }
}

function candidateDocumentName(documentId: string): string {
  return flow.documents.find((document) => document.documentId === documentId)?.filename ?? '來源文件'
}

function canExtractDocument(document: { mimeType: string; isActive: boolean }): boolean {
  const mime = document.mimeType.toLowerCase()
  return document.isActive && auth.permissions.includes('valuation.update') && (
    mime === 'application/pdf'
    || mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  )
}

function canManageSourceDocument(document: { documentType: string; isActive: boolean }): boolean {
  return document.isActive
    && canUpload.value
    && SOURCE_DOCUMENT_CATEGORIES.includes(document.documentType as DocumentCategory)
}

function documentCategoryLabel(category: string): string {
  return ({
    original: '原始文件',
    'land-register': '土地登記資料',
    'cadastral-map': '地籍圖',
    photos: '照片',
    attachments: '其他附件',
    'map-section-sketch': '地段示意圖',
    'map-zoning': '使用分區圖',
    'map-land-value-section': '地價區段圖',
    'generated-report': '系統產生報告',
    'complete-valuation-report': '完整查估書',
  } as Record<string, string>)[category] ?? category
}

function candidateConfidenceLabel(candidate: ExtractedFieldResponseDto): string {
  const confidence = Number(candidate.confidence)
  if (!Number.isFinite(confidence)) return candidate.confidence || '未提供'
  const percent = confidence <= 1 ? confidence * 100 : confidence
  return `${percent.toFixed(percent >= 10 ? 0 : 1)}%`
}

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '大小未知'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function documentCandidateCount(documentId: string): number {
  return allCandidates.value.filter((candidate) => candidate.document_id === documentId).length
}

function documentPendingCount(documentId: string): number {
  return pendingCandidates.value.filter((candidate) => candidate.document_id === documentId).length
}

function documentAiStatus(documentId: string): string {
  const total = documentCandidateCount(documentId)
  const pending = documentPendingCount(documentId)
  if (extractionBusyDocumentId.value === documentId) return 'AI 辨識中'
  if (!total) return '尚未辨識'
  if (pending) return `${total} 欄位 · ${pending} 待確認`
  return `${total} 欄位 · 已完成確認`
}

function canPreviewDocument(document: DocumentArtifactModel): boolean {
  const mime = document.mimeType.toLowerCase()
  return mime === 'application/pdf' || mime.startsWith('image/')
}

function clearPreviewUrl(): void {
  if (previewUrl.value && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
}

async function openDocumentPreview(documentId: string, page: number | null = null): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const source = flow.documents.find((item) => item.documentId === documentId)
  if (!source || !isCurrentCase(token, requestedCaseId)) return

  activeWizardStep.value = 2
  previewDocumentId.value = documentId
  previewPage.value = page
  previewError.value = ''
  clearPreviewUrl()

  if (!canPreviewDocument(source)) {
    previewError.value = '此格式目前可下載，但不提供內嵌預覽。PDF 與圖片可直接在此檢視。'
    return
  }

  previewLoading.value = true
  try {
    const blob = await valuationApi.downloadDocument(requestedCaseId, documentId)
    if (!isCurrentCase(token, requestedCaseId) || previewDocumentId.value !== documentId) return
    if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
      previewError.value = '目前瀏覽器環境無法建立文件預覽，可改用下載查看。'
      return
    }
    previewUrl.value = URL.createObjectURL(blob)
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) previewError.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId) && previewDocumentId.value === documentId) previewLoading.value = false
  }
}

async function downloadSourceDocument(document: DocumentArtifactModel): Promise<void> {
  error.value = ''
  try {
    const blob = await valuationApi.downloadDocument(caseId.value, document.documentId)
    if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return
    const url = URL.createObjectURL(blob)
    const anchor = window.document.createElement('a')
    anchor.href = url
    anchor.download = document.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  }
}

function candidateEditorType(candidate: ExtractedFieldResponseDto): 'date' | 'number' | 'text' {
  const field = candidate.field_name.toLowerCase()
  if (field.includes('date')) return 'date'
  if (['price', 'weight', 'rate', 'area', 'sqm', 'latitude', 'longitude', 'amount', 'total'].some((part) => field.includes(part))) {
    return 'number'
  }
  return 'text'
}

function candidateUnit(candidate: ExtractedFieldResponseDto): string {
  const field = candidate.field_name.toLowerCase()
  if (field.includes('sqm') || field.includes('area')) return 'm²'
  if (field.includes('price') || field.includes('amount') || field.includes('total')) return '元'
  return ''
}

async function openCandidateSource(candidate: ExtractedFieldResponseDto): Promise<void> {
  selectedCandidateId.value = candidate.extracted_field_id
  await openDocumentPreview(candidate.document_id, candidate.source_page ?? null)
}

function setWizardStep(step: WizardStep): void {
  if (step >= 5) {
    if (canProceedToSubmit.value) goToSubmit()
    else {
      activeWizardStep.value = 4
      notice.value = '必須先完成資料、計算並通過檢核，才能進入查估書確認與送審。'
    }
    return
  }
  activeWizardStep.value = step
  if (step === 3 && !activeDataSection.value) activeDataSection.value = 'overview'
}

function jumpToDataSection(section: DataSection): void {
  activeWizardStep.value = 3
  activeDataSection.value = section
}

function jumpToFirstDataIssue(): void {
  if (manualFieldEntries.value.length) jumpToDataSection('manual')
  else if (!parcels.value.length || !flow.benchmarks.length) jumpToDataSection('land')
  else jumpToDataSection('f03')
}

function wizardPrevious(): void {
  if (activeWizardStep.value <= 1) return
  activeWizardStep.value = Math.max(1, activeWizardStep.value - 1) as WizardStep
}

function wizardNext(): void {
  if (activeWizardStep.value === 1) {
    activeWizardStep.value = 2
    return
  }
  if (activeWizardStep.value === 2) {
    if (pendingCandidates.value.length) {
      selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? null
      notice.value = `還有 ${pendingCandidates.value.length} 筆 AI 辨識結果待確認，先完成確認再進入正式資料。`
      void focusElementById('valuation-candidate-workspace')
      return
    }
    activeWizardStep.value = 3
    activeDataSection.value = 'overview'
    return
  }
  if (activeWizardStep.value === 3) {
    if (dataIssueCounts.value.overview) {
      notice.value = `目前仍有 ${dataIssueCounts.value.overview} 項資料待處理，已帶你前往第一個待處理區域。`
      jumpToFirstDataIssue()
      return
    }
    activeWizardStep.value = 4
    return
  }
  if (activeWizardStep.value === 4) {
    if (canProceedToSubmit.value) goToSubmit()
    else notice.value = '請先執行伺服器計算與檢核，並處理所有阻擋項目。'
  }
}

function initializeCandidateInputs(candidates: ExtractedFieldResponseDto[]): void {
  for (const candidate of candidates) {
    if (!(candidate.extracted_field_id in candidateValue)) {
      candidateValue[candidate.extracted_field_id] = displayCandidateValue(
        candidate.confirmed_value ?? candidate.extracted_value,
      )
    }
    if (!(candidate.extracted_field_id in candidateDecision)) {
      candidateDecision[candidate.extracted_field_id] = ''
    }
  }
}

function isCurrentCase(token: number, requestedCaseId: string): boolean {
  return token === activeCaseToken && requestedCaseId === caseId.value
}

function copyDraft(): void {
  if (!flow.f03) return
  Object.assign(draft, flow.f03.editable)
  dirty.value = false
}

async function loadF03(form: ValuationFormModel, token: number, requestedCaseId: string): Promise<void> {
  const dto = await valuationApi.getF03(requestedCaseId, form.formInstanceId)
  if (!isCurrentCase(token, requestedCaseId)) return
  flow.f03 = mapF03DraftResponse(dto, form.sourceDocumentId, form.formInstanceId)
  copyDraft()
}

async function loadWorkflowGuidance(token = activeCaseToken, requestedCaseId = caseId.value): Promise<void> {
  if (!canReadAutomatedWorkflow.value || !isCurrentCase(token, requestedCaseId)) {
    workflowGuidance.value = null
    return
  }
  try {
    const response = await valuationApi.getWorkflowReview(requestedCaseId)
    if (isCurrentCase(token, requestedCaseId)) {
      workflowGuidance.value = response
      initializeCandidateInputs(response.candidates)
      initializeManualFieldInputs(response)
    }
  } catch {
    // The workflow helper only exists for cases initialized through the automated
    // intake. The regular valuation flow remains usable when it is unavailable.
    if (isCurrentCase(token, requestedCaseId)) workflowGuidance.value = null
  }
}

async function loadReviewHandoff(token = activeCaseToken, requestedCaseId = caseId.value): Promise<void> {
  if (!isCurrentCase(token, requestedCaseId)) return
  try {
    const response = await valuationApi.getReviewHandoff(requestedCaseId)
    if (isCurrentCase(token, requestedCaseId)) reviewHandoff.value = response
  } catch {
    // The handoff is supplemental for ordinary draft cases. Do not block the
    // valuation editor if an older backend does not expose it yet.
    if (isCurrentCase(token, requestedCaseId)) reviewHandoff.value = null
  }
}

function editableReportPagePayload(
  pageCode: ReportPageCode,
  data: Record<string, unknown>,
): Record<string, unknown> {
  const allowed: Record<ReportPageCode, readonly string[]> = {
    S01: [
      'district_name', 'district_boundary', 'survey_date', 'urban_plan_status',
      'land_use_zone', 'building_coverage_rate', 'floor_area_ratio',
      'prohibited_building', 'restricted_building', 'main_road_name',
      'main_road_width_m', 'average_road_width_m', 'observations', 'notes',
      'site_opinion', 'handler_name', 'section_head_name', 'director_name',
      'appraiser_name',
    ],
    'F02-RF': [
      'benchmark_land_id', 'comparison_analysis_id', 'rule_version_id',
      'factor_rows', 'other_influences', 'notes', 'appraiser_name',
    ],
    F02: [
      'benchmark_land_id', 'comparison_analysis_id', 'comparison_targets',
      'benchmark_notes', 'notes', 'handler_name', 'section_head_name',
      'director_name', 'appraiser_name',
    ],
  }
  return Object.fromEntries(
    allowed[pageCode]
      .filter((key) => Object.prototype.hasOwnProperty.call(data, key))
      .map((key) => [key, data[key]]),
  )
}

async function ensureRevisionDrafts(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (!isRevisionRequired.value || revisionInitializing.value || !isCurrentCase(token, requestedCaseId)) return

  revisionInitializing.value = true
  error.value = ''
  notice.value = ''
  try {
    const currentF03 = f03Form.value
    const f03SourceValues = flow.f03 ? { ...flow.f03.editable } : null
    const currentReportId = reportProgress.value?.report_id ?? null
    const reportSourcePages = currentReportId
      ? await Promise.all(
          (['S01', 'F02-RF', 'F02'] as ReportPageCode[]).map((pageCode) =>
            valuationApi.getReportPage(requestedCaseId, currentReportId, pageCode),
          ),
        )
      : []

    if (!currentF03 || currentF03.status !== 'DRAFT') {
      if (!f03SourceValues?.benchmarkLandId || !f03SourceValues.valuationBaseDate) {
        throw new Error('F03_SOURCE_VALUES_REQUIRED')
      }
      const createdF03 = await valuationApi.createForm(requestedCaseId, {
        form_code: 'F03',
        prepared_date: currentF03?.preparedDate ?? flow.case?.valuationBaseDate ?? null,
        source_document_id: currentF03?.sourceDocumentId ?? null,
      })
      await valuationApi.updateF03(
        requestedCaseId,
        createdF03.form_instance_id,
        mapF03Update(f03SourceValues),
      )
    }

    const reportIsEditable = Boolean(
      currentReportId
        && latestReportForms.value.length === 3
        && latestReportForms.value.every((form) => form.status === 'DRAFT'),
    )
    if (!reportIsEditable) {
      const createdPackage = await valuationApi.createReportPackage(requestedCaseId, {
        report_type: 'REPORT_COMPARISON_COMMERCIAL',
        prepared_date: latestReportForms.value[0]?.preparedDate ?? flow.case?.valuationBaseDate ?? null,
      })
      for (const sourcePage of reportSourcePages) {
        const payload = editableReportPagePayload(sourcePage.page_code, sourcePage.data)
        if (Object.keys(payload).length) {
          await valuationApi.updateReportPage(
            requestedCaseId,
            createdPackage.report_id,
            sourcePage.page_code,
            payload,
          )
        }
      }
    }

    await loadData()
    if (isCurrentCase(activeCaseToken, requestedCaseId)) {
      notice.value = '補正版已建立：F03 與 S01／F02-RF／F02 已建立較新的 DRAFT 版本，可依修正通知逐項修改。'
      activeWizardStep.value = 3
      activeDataSection.value = 'f03'
      void focusElementById('f03-data-section')
    }
  } catch (caught: unknown) {
    if (caught instanceof Error && caught.message === 'F03_SOURCE_VALUES_REQUIRED') {
      error.value = '舊版 F03 缺少基準地或估價基準日，無法安全複製；請先確認來源資料。'
    } else {
      error.value = safeValuationErrorMessage(caught)
    }
  } finally {
    revisionInitializing.value = false
  }
}

function findingFieldCodes(finding: ValidationFindingModel): string[] {
  if (finding.fieldPath === 'prices') return ['comparison_price', 'income_price']
  if (finding.fieldPath === 'case/form/benchmark/date') return ['valuation_base_date', 'benchmark_land_id']
  if (finding.fieldPath) return finding.fieldPath.split(',').map((item) => item.trim()).filter(Boolean)
  if (finding.ruleCode === 'F03_REQUIRED_FIELDS') return ['benchmark_land_id', 'valuation_base_date']
  if (finding.ruleCode === 'F03_REQUIRED_DOCUMENTS' || finding.ruleCode === 'F03_MINIO_OBJECTS') return ['documents']
  if (finding.ruleCode === 'F03_CALCULATION_MATCH') return ['benchmark_land_price']
  return []
}

function findingLocationLabel(finding: ValidationFindingModel): string {
  const codes = findingFieldCodes(finding)
  if (!codes.length) return 'F03 檢核資料'
  return codes.map((code) => FIELD_LABELS[code] ?? `F03 → ${code}`).join('、')
}

function findingCorrectionHint(finding: ValidationFindingModel): string {
  if (finding.ruleCode === 'F03_CALCULATION_MATCH') {
    return '此欄位由伺服器計算。請先修正上游資料，再重新執行「伺服器計算與檢核」。'
  }
  if (finding.ruleCode === 'F03_REQUIRED_DOCUMENTS' || finding.ruleCode === 'F03_MINIO_OBJECTS') {
    return '請到來源文件區補上或重新上傳缺少的文件，完成後再執行檢核。'
  }
  if (finding.ruleCode === 'F03_WEIGHT_SUM') {
    return '請調整比較法與收益法權重，使各自介於 0～1 且合計為 1。'
  }
  if (finding.ruleCode === 'F03_METHOD_INPUTS') {
    return '權重大於 0 的估價方法必須有對應價格；補值後重新計算。'
  }
  if (finding.ruleCode === 'F03_PRICE_RANGE') return '價格不可小於 0，請修正價格欄位。'
  if (finding.ruleCode === 'F03_REQUIRED_FIELDS') return '請補齊基準地與估價基準日。'
  return finding.message
}

async function focusElementById(targetId: string, message?: string): Promise<void> {
  await nextTick()
  const target = document.getElementById(targetId)
  if (!target) return
  target.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  const focusable = target.matches('input, select, textarea, button')
    ? target as HTMLElement
    : target.querySelector<HTMLElement>('input, select, textarea, button')
  focusable?.focus()
  if (message) notice.value = message
}

function goToFinding(finding: ValidationFindingModel): void {
  const fieldCode = findingFieldCodes(finding)[0]
  const targetId = fieldCode ? FIELD_TARGET_IDS[fieldCode] : undefined
  if (!targetId) {
    notice.value = `請依檢核訊息處理：${finding.message}`
    return
  }
  if (fieldCode === 'documents' || fieldCode === 'object_key') {
    activeWizardStep.value = 2
  } else {
    activeWizardStep.value = 3
    activeDataSection.value = 'f03'
  }
  void focusElementById(targetId, `${findingLocationLabel(finding)}：${findingCorrectionHint(finding)}`)
}

function goToWorkflowNextAction(): void {
  if (isRevisionRequired.value) {
    if (!revisionDraftReady.value) {
      void ensureRevisionDrafts()
      return
    }
    activeWizardStep.value = 3
    activeDataSection.value = 'f03'
    void focusElementById('f03-data-section', '補正版已建立，請依修正通知逐項調整資料。')
    return
  }
  if (workflowGuidance.value?.pending_candidate_count) {
    activeWizardStep.value = 2
    selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? null
    void focusElementById('valuation-candidate-workspace', '目前仍有待確認候選資料；請逐筆確認、修改後採用，或拒絕。')
    return
  }
  if (workflowMissingItems.value.some((item) => item.toLowerCase().includes('document'))) {
    activeWizardStep.value = 2
    void focusElementById('valuation-document-workspace')
    return
  }
  if (flow.validation && !flow.validation.canGenerateReport) {
    activeWizardStep.value = 4
    void focusElementById('validation-title')
    return
  }
  if (canProceedToSubmit.value) {
    goToSubmit()
    return
  }
  if (!parcels.value.length || !flow.benchmarks.length) {
    activeWizardStep.value = 3
    activeDataSection.value = 'land'
    void focusElementById('valuation-land-context', '請先補齊宗地與比準地資料。')
    return
  }
  if (flow.f03) {
    activeWizardStep.value = 3
    activeDataSection.value = 'f03'
    void focusElementById('f03-data-section')
  } else {
    activeWizardStep.value = 2
    void focusElementById('valuation-document-workspace')
  }
}

async function goToCorrectionItem(item: CorrectionItem): Promise<void> {
  if (isRevisionRequired.value && !revisionDraftReady.value) {
    await ensureRevisionDrafts()
    if (!revisionDraftReady.value) return
  }
  if (item.document_id) {
    activeWizardStep.value = 2
    await focusElementById('valuation-document-workspace', `修正要求：${item.requested_correction}`)
    return
  }
  activeWizardStep.value = 3
  activeDataSection.value = 'f03'
  await focusElementById('f03-data-section', `修正要求：${item.requested_correction}`)
}

function goToMissingItem(item: HandoffMissingItem): void {
  if (item.document_type) {
    activeWizardStep.value = 2
    void focusElementById(
      'valuation-document-workspace',
      `審查要求補件：${item.item_name}${item.reason ? `｜${item.reason}` : ''}`,
    )
    return
  }
  activeWizardStep.value = 3
  activeDataSection.value = 'land'
  void focusElementById(
    'valuation-land-context',
    `審查要求補資料：${item.item_name}${item.reason ? `｜${item.reason}` : ''}`,
  )
}

function focusRequestedRouteTarget(): void {
  const requestedStep = typeof route.query.step === 'string' ? Number(route.query.step) : NaN
  const focus = typeof route.query.focus === 'string' ? route.query.focus : ''
  const field = typeof route.query.field === 'string' ? route.query.field : ''
  if (Number.isInteger(requestedStep) && requestedStep >= 1 && requestedStep <= 4) {
    activeWizardStep.value = requestedStep as WizardStep
  }
  if (focus === 'documents') {
    activeWizardStep.value = 2
    void focusElementById('valuation-document-workspace')
    return
  }
  if (!field) return
  const normalized = field.split(',')[0]?.trim()
  const targetId = normalized ? FIELD_TARGET_IDS[normalized] : undefined
  if (targetId) {
    if (normalized === 'documents' || normalized === 'object_key') activeWizardStep.value = 2
    else {
      activeWizardStep.value = 3
      activeDataSection.value = 'f03'
    }
    void focusElementById(targetId, `請修正 ${FIELD_LABELS[normalized] ?? normalized} 後重新執行檢核。`)
  }
}

async function loadData(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = ++activeCaseToken
  resetValuationFlow()
  Object.assign(draft, emptyDraft())
  dirty.value = false
  saving.value = false
  running.value = false
  error.value = ''
  notice.value = ''
  workflowGuidance.value = null
  reviewHandoff.value = null
  reportProgress.value = null
  parcels.value = []
  extractionCandidates.value = []
  extractionBusyDocumentId.value = null
  confirmingCandidates.value = false
  clearPreviewUrl()
  previewDocumentId.value = null
  previewPage.value = null
  previewError.value = ''
  selectedCandidateId.value = null
  clearReactiveRecord(candidateDecision)
  clearReactiveRecord(candidateValue)
  clearReactiveRecord(manualFieldValue)
  clearReactiveRecord(documentCategoryDraft)
  resetParcelDraft()
  resetBenchmarkDraft()

  if (!requestedCaseId) {
    error.value = '找不到案件識別資訊，請從估價案件清單重新進入。'
    loading.value = false
    return
  }

  loading.value = true
  try {
    const [caseDto, parcelDtos, formDtos, benchmarkDtos, documentDtos, reportProgressDto] = await Promise.all([
      valuationApi.getCase(requestedCaseId),
      valuationApi.listParcels(requestedCaseId),
      valuationApi.listForms(requestedCaseId),
      valuationApi.listBenchmarkLands(requestedCaseId),
      valuationApi.listDocuments(requestedCaseId),
      valuationApi.getReportProgress(requestedCaseId),
    ])
    if (!isCurrentCase(token, requestedCaseId)) return

    const forms = formDtos.map(mapFormResponse)
    const form = forms
      .filter((item) => item.formCode === 'F03')
      .reduce<ValuationFormModel | null>(
        (latest, item) => (!latest || item.versionNo > latest.versionNo ? item : latest),
        null,
      )
    const documents = documentDtos.map(mapDocumentResponse)
    const authoritative = selectAuthoritativeF02(forms, documents, reportProgressDto)

    flow.case = mapCaseResponse(caseDto)
    parcels.value = parcelDtos
    resetParcelDraft()
    resetBenchmarkDraft()
    flow.forms = forms
    flow.benchmarks = benchmarkDtos.map(mapBenchmarkLandResponse)
    flow.documents = documents
    previewDocumentId.value = documents.find((document) => document.isActive)?.documentId ?? null
    initializeDocumentCategories()
    flow.authoritativeF02 = authoritative.form
    flow.completeReport = authoritative.completeReport
    flow.reportPackageId = authoritative.reportPackageId
    reportProgress.value = reportProgressDto
    if (form) {
      try {
        await loadF03(form, token, requestedCaseId)
      } catch {
        if (isCurrentCase(token, requestedCaseId)) {
          notice.value = 'F03 表單已建立，但正式估價草稿尚未初始化；可先上傳來源文件並補齊宗地／比準地資料。'
        }
      }
    } else {
      notice.value = '目前案件尚未建立 F03 估價表；可先補齊來源文件，再建立需要的估價表。'
    }
    await Promise.all([
      loadWorkflowGuidance(token, requestedCaseId),
      loadReviewHandoff(token, requestedCaseId),
    ])
    if (isCurrentCase(token, requestedCaseId)) focusRequestedRouteTarget()
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) loading.value = false
  }
}

function chooseUpload(event: Event): void {
  const input = event.target as HTMLInputElement
  uploadFile.value = input.files?.[0] ?? null
}

async function uploadSourceDocument(): Promise<void> {
  if (!flow.case || !uploadFile.value || !canUpload.value || uploading.value) return
  uploading.value = true
  error.value = ''
  notice.value = ''
  try {
    const uploaded = await valuationApi.uploadDocument(flow.case.caseId, uploadCategory.value, uploadFile.value)
    flow.documents = [mapDocumentResponse(uploaded), ...flow.documents.filter((item) => item.documentId !== uploaded.document_id)]
    previewDocumentId.value = uploaded.document_id
    initializeDocumentCategories()
    notice.value = `${uploaded.original_filename} 已上傳完成，檔案版本與儲存狀態已由伺服器確認。`
    uploadFile.value = null
    const input = document.querySelector<HTMLInputElement>('#valuation-source-file')
    if (input) input.value = ''
    await loadWorkflowGuidance()
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    uploading.value = false
  }
}

async function extractDocument(documentId: string): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (
    extractionBusyDocumentId.value
    || !auth.permissions.includes('valuation.update')
    || !isCurrentCase(token, requestedCaseId)
  ) return

  extractionBusyDocumentId.value = documentId
  error.value = ''
  notice.value = ''
  try {
    const result = await valuationApi.startDocumentExtraction(requestedCaseId, documentId)
    if (!isCurrentCase(token, requestedCaseId)) return
    extractionCandidates.value = [
      ...extractionCandidates.value.filter((candidate) => candidate.document_id !== documentId),
      ...result.candidates,
    ]
    initializeCandidateInputs(result.candidates)
    await loadWorkflowGuidance(token, requestedCaseId)
    const pending = result.candidates.filter((candidate) => candidate.field_status === 'NEEDS_CONFIRMATION').length
    previewDocumentId.value = documentId
    selectedCandidateId.value = result.candidates.find((candidate) => candidate.field_status === 'NEEDS_CONFIRMATION')?.extracted_field_id
      ?? result.candidates[0]?.extracted_field_id
      ?? null
    notice.value = pending
      ? `AI 辨識完成，找到 ${pending} 筆需要人工確認的欄位。`
      : 'AI 辨識完成，目前沒有需要人工確認的欄位。'
    if (pending) void focusElementById('valuation-candidate-workspace')
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) extractionBusyDocumentId.value = null
  }
}

function chooseCandidateDecision(candidateId: string, decision: 'CONFIRM' | 'REJECT'): void {
  candidateDecision[candidateId] = decision
}

function reopenCandidate(candidate: ExtractedFieldResponseDto): void {
  candidateDecision[candidate.extracted_field_id] = 'CONFIRM'
  candidateValue[candidate.extracted_field_id] = displayCandidateValue(
    candidate.confirmed_value ?? candidate.extracted_value,
  )
  void nextTick(() => {
    document.querySelector<HTMLInputElement>(`[data-testid="candidate-value-${candidate.extracted_field_id}"]`)?.focus()
  })
}

async function submitCandidateDecisions(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (confirmingCandidates.value || !selectedCandidateCount.value || !isCurrentCase(token, requestedCaseId)) return

  const confirmations = candidateDecisionTargets.value.flatMap<AutomatedCandidateConfirmationDto>((candidate) => {
    const decision = candidateDecision[candidate.extracted_field_id]
    if (!decision) return []
    const inputValue = candidateValue[candidate.extracted_field_id] ?? ''
    const originalValue = displayCandidateValue(candidate.extracted_value)
    return [{
      document_id: candidate.document_id,
      extracted_field_id: candidate.extracted_field_id,
      decision,
      ...(decision === 'CONFIRM' && inputValue !== originalValue ? { corrected_value: inputValue } : {}),
    }]
  })
  if (!confirmations.length) return

  confirmingCandidates.value = true
  error.value = ''
  notice.value = ''
  try {
    const response = await valuationApi.confirmWorkflowCandidates(requestedCaseId, {
      confirmations,
      confirm_apply: true,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    workflowGuidance.value = response
    extractionCandidates.value = response.candidates
    for (const confirmation of confirmations) {
      delete candidateDecision[confirmation.extracted_field_id]
      delete candidateValue[confirmation.extracted_field_id]
    }
    initializeCandidateInputs(response.candidates)
    initializeManualFieldInputs(response)
    const form = f03Form.value
    if (form) {
      try {
        await loadF03(form, token, requestedCaseId)
      } catch {
        // Some confirmations are for non-F03 forms or F03 may still lack its
        // two initialization fields. The workflow response remains authoritative.
      }
    }
    notice.value = response.pending_candidate_count
      ? `已保存本次判定；尚有 ${response.pending_candidate_count} 筆候選需要人工確認。`
      : '候選資料已全部完成人工判定；可繼續確認正式採用值。'
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) confirmingCandidates.value = false
  }
}

async function saveManualFields(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (manualFieldsSaving.value || !isCurrentCase(token, requestedCaseId)) return

  const values: Record<string, Record<string, unknown>> = {}
  for (const entry of manualFieldEntries.value) {
    const value = (manualFieldValue[entry.key] ?? '').trim()
    if (!value) continue
    ;(values[entry.formCode] ??= {})[entry.fieldName] = value
  }
  if (!Object.keys(values).length) {
    notice.value = '請至少填寫一個人工補充欄位；空白欄位不會送到伺服器。'
    return
  }

  manualFieldsSaving.value = true
  error.value = ''
  notice.value = ''
  try {
    const response = await valuationApi.saveWorkflowManualFields(requestedCaseId, { values })
    if (!isCurrentCase(token, requestedCaseId)) return
    workflowGuidance.value = response
    extractionCandidates.value = response.candidates
    initializeCandidateInputs(response.candidates)
    initializeManualFieldInputs(response)
    const form = f03Form.value
    if (form) {
      try {
        await loadF03(form, token, requestedCaseId)
      } catch {
        // Manual values may belong only to another form. Keep the workflow
        // response visible even if F03 is not initialized yet.
      }
    }
    const failures = Object.entries(response.manual_field_errors ?? {})
    notice.value = failures.length
      ? `已保存可套用欄位；另有 ${failures.length} 項無法寫入正式表單，請依下方錯誤修正。`
      : `已保存 ${response.manual_fields_saved?.length ?? 0} 個人工補充欄位，並重新產生確認資料。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) manualFieldsSaving.value = false
  }
}

async function refreshDocumentsAndWorkflow(token: number, requestedCaseId: string): Promise<void> {
  const documentDtos = await valuationApi.listDocuments(requestedCaseId)
  if (!isCurrentCase(token, requestedCaseId)) return
  flow.documents = documentDtos.map(mapDocumentResponse)
  clearReactiveRecord(documentCategoryDraft)
  initializeDocumentCategories()
  await loadWorkflowGuidance(token, requestedCaseId)
}

async function reclassifyDocument(documentId: string): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const category = documentCategoryDraft[documentId]
  if (!category || documentActionId.value || !isCurrentCase(token, requestedCaseId)) return
  documentActionId.value = documentId
  error.value = ''
  notice.value = ''
  try {
    await valuationApi.reclassifyDocument(requestedCaseId, documentId, category)
    if (!isCurrentCase(token, requestedCaseId)) return
    await refreshDocumentsAndWorkflow(token, requestedCaseId)
    notice.value = `文件分類已更新為「${documentCategoryLabel(category)}」。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) documentActionId.value = null
  }
}

async function removeDocument(documentId: string, filename: string): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (documentActionId.value || !isCurrentCase(token, requestedCaseId)) return
  if (typeof window !== 'undefined' && !window.confirm(`確定要移除「${filename}」嗎？舊版本仍保留在稽核歷程。`)) return
  documentActionId.value = documentId
  error.value = ''
  notice.value = ''
  try {
    await valuationApi.deleteDocument(requestedCaseId, documentId)
    if (!isCurrentCase(token, requestedCaseId)) return
    if (previewDocumentId.value === documentId) {
      clearPreviewUrl()
      previewDocumentId.value = null
      previewPage.value = null
      selectedCandidateId.value = null
    }
    await refreshDocumentsAndWorkflow(token, requestedCaseId)
    if (!previewDocumentId.value) {
      previewDocumentId.value = flow.documents.find((document) => document.isActive)?.documentId ?? null
    }
    notice.value = `${filename} 已從目前作用中的來源文件移除。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) documentActionId.value = null
  }
}

async function downloadConfirmationExport(): Promise<void> {
  const exported = workflowGuidance.value?.confirmation_export
  const requestedCaseId = caseId.value
  if (!exported || !requestedCaseId) return
  error.value = ''
  try {
    const blob = await valuationApi.downloadDocument(requestedCaseId, exported.document_id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = exported.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  }
}

function startParcelEdit(parcel: ParcelResponseDto): void {
  activeWizardStep.value = 3
  activeDataSection.value = 'land'
  editingParcelId.value = parcel.parcel_id
  Object.assign(parcelDraft, {
    districtCode: parcel.district_code,
    sectionName: parcel.section_name,
    subsectionName: parcel.subsection_name,
    landNo: parcel.land_no,
    areaSqm: parcel.area_sqm,
    landUseZone: parcel.land_use_zone ?? '',
    designatedUse: parcel.designated_use ?? '',
    sourceDocumentId: parcel.source_document_id ?? '',
  })
  void focusElementById('parcel-editor')
}

function parcelPayload(): ParcelCreateDto {
  return {
    district_code: parcelDraft.districtCode.trim(),
    section_name: parcelDraft.sectionName.trim(),
    subsection_name: parcelDraft.subsectionName.trim(),
    land_no: parcelDraft.landNo.trim(),
    area_sqm: parcelDraft.areaSqm.trim(),
    land_use_zone: parcelDraft.landUseZone.trim() || null,
    designated_use: parcelDraft.designatedUse.trim() || null,
    source_document_id: parcelDraft.sourceDocumentId || null,
  }
}

async function saveParcel(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const payload = parcelPayload()
  if (
    landContextSaving.value
    || !canEditLandContext.value
    || !payload.district_code
    || !payload.section_name
    || !payload.land_no
    || !payload.area_sqm
    || !isCurrentCase(token, requestedCaseId)
  ) return

  landContextSaving.value = true
  error.value = ''
  notice.value = ''
  try {
    if (editingParcelId.value) {
      await valuationApi.updateParcel(requestedCaseId, editingParcelId.value, payload)
      notice.value = '宗地資料已更新。'
    } else {
      await valuationApi.createParcel(requestedCaseId, payload)
      notice.value = '宗地資料已建立。'
    }
    if (!isCurrentCase(token, requestedCaseId)) return
    parcels.value = await valuationApi.listParcels(requestedCaseId)
    if (!isCurrentCase(token, requestedCaseId)) return
    resetParcelDraft()
    resetBenchmarkDraft()
    await loadWorkflowGuidance(token, requestedCaseId)
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) landContextSaving.value = false
  }
}

function benchmarkPayload(): BenchmarkLandCreateDto {
  return {
    parcel_id: benchmarkDraft.parcelId,
    benchmark_land_no: benchmarkDraft.benchmarkLandNo.trim(),
    price_zone_no: benchmarkDraft.priceZoneNo.trim(),
    land_consolidation_serial: benchmarkDraft.landConsolidationSerial.trim() || null,
    latitude: benchmarkDraft.latitude.trim() || null,
    longitude: benchmarkDraft.longitude.trim() || null,
  }
}

async function saveBenchmarkLand(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const payload = benchmarkPayload()
  if (
    landContextSaving.value
    || !canEditLandContext.value
    || !payload.parcel_id
    || !payload.benchmark_land_no
    || !payload.price_zone_no
    || !isCurrentCase(token, requestedCaseId)
  ) return

  landContextSaving.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await valuationApi.createBenchmarkLand(requestedCaseId, payload)
    if (!isCurrentCase(token, requestedCaseId)) return
    const benchmarkDtos = await valuationApi.listBenchmarkLands(requestedCaseId)
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.benchmarks = benchmarkDtos.map(mapBenchmarkLandResponse)
    resetBenchmarkDraft()

    const form = f03Form.value
    if (form?.status === 'DRAFT' && !flow.f03) {
      await valuationApi.updateF03(requestedCaseId, form.formInstanceId, {
        benchmark_land_id: created.benchmark_land_id,
        valuation_base_date: flow.case?.valuationBaseDate ?? null,
      })
      await loadF03(form, token, requestedCaseId)
      notice.value = '比準地已建立，並以案件基準日初始化 F03 草稿。'
    } else {
      notice.value = flow.f03
        ? '比準地已建立。既有 F03 草稿仍保留原比準地，以避免未確認地改寫正式估價來源。'
        : '比準地已建立。'
    }
    await loadWorkflowGuidance(token, requestedCaseId)
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) landContextSaving.value = false
  }
}

async function saveConfirmedFields(
  token = activeCaseToken,
  requestedCaseId = caseId.value,
): Promise<boolean> {
  const form = f03Form.value
  if (!form || !isCurrentCase(token, requestedCaseId)) return false

  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const updated = await valuationApi.updateF03(requestedCaseId, form.formInstanceId, mapF03Update(draft))
    if (!isCurrentCase(token, requestedCaseId)) return false
    flow.f03 = mapF03DraftResponse(updated, form.sourceDocumentId, form.formInstanceId)
    copyDraft()
    await loadWorkflowGuidance(token, requestedCaseId)
    notice.value = '人工確認欄位已由伺服器儲存並重新載入。'
    return true
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return false
    error.value = safeValuationErrorMessage(caught)
    return false
  } finally {
    if (isCurrentCase(token, requestedCaseId)) saving.value = false
  }
}

function handleSave(): void {
  void saveConfirmedFields()
}

async function runValuation(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const form = f03Form.value
  if (!form || !flow.f03 || !isCurrentCase(token, requestedCaseId)) return

  activeWizardStep.value = 4
  running.value = true
  error.value = ''
  notice.value = ''
  if (form.status === 'DRAFT') flow.calculation = null
  flow.validation = null
  flow.report = null
  try {
    if (dirty.value && !(await saveConfirmedFields(token, requestedCaseId))) return
    if (!isCurrentCase(token, requestedCaseId)) return

    let currentForm = f03Form.value
    if (!currentForm || !flow.f03) return

    if (currentForm.status !== 'DRAFT') {
      notice.value = '目前 F03 已不是草稿狀態，請重新載入案件後再執行。'
      return
    }

    const calculation = await valuationApi.calculate(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.calculation = mapCalculationResponse(calculation)
    flow.f03 = {
      ...flow.f03,
      benchmarkLandPrice: flow.calculation.result,
      source: sourceForCalculatedValue(),
    }

    const validation = await valuationApi.validate(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.validation = mapValidationResponse(validation)

    if (!flow.validation.canGenerateReport) {
      await loadWorkflowGuidance(token, requestedCaseId)
      notice.value = '伺服器檢核回傳阻擋項目，請依結果補正後再執行。'
      return
    }

    const submitted = await valuationApi.submitForm(requestedCaseId, currentForm.formInstanceId)
    if (!isCurrentCase(token, requestedCaseId)) return
    const submittedForm = mapFormResponse(submitted)
    flow.forms = flow.forms.map((item) =>
      item.formInstanceId === submittedForm.formInstanceId ? submittedForm : item,
    )
    if (submittedForm.status !== 'READY') {
      notice.value = '伺服器未將 F03 轉為 READY，暫停正式輸出。'
      return
    }
    currentForm = f03Form.value
    if (!currentForm || !isCurrentCase(token, requestedCaseId)) return

    const report = await valuationApi.generateReport(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.report = mapReportResponse(report)
    await loadWorkflowGuidance(token, requestedCaseId)
    notice.value = '伺服器已完成計算、檢核、F03 提交與正式輸出。'
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) running.value = false
  }
}

function goToSubmit(): void {
  if (!canProceedToSubmit.value) {
    notice.value = '目前仍有阻擋項目，必須先完成修正並通過伺服器檢核，才能進入輸出與送審。'
    return
  }
  void router.push({ name: 'valuation-submit', params: { caseId: caseId.value } })
}

function openRevisionFields(): void {
  activeWizardStep.value = 3
  activeDataSection.value = 'f03'
  void focusElementById('f03-data-section', '補正版已建立，請依上方修正通知逐項修改。')
}

watch(caseId, () => {
  void loadData()
}, { immediate: true })

onBeforeUnmount(clearPreviewUrl)
</script>

<template>
  <div class="valuation-view">
    <ValuationStepNavigator
      :current-step="activeWizardStep"
      :available-steps="wizardAvailableSteps"
      :issue-counts="wizardIssueCounts"
      @navigate="setWizardStep"
    />
    <PageHeader
      eyebrow="GUIDED VALUATION"
      :title="wizardStepTitle"
      :description="wizardStepDescription"
    />

    <LoadingSkeleton v-if="loading" :rows="7" label="案件估價資料載入中" />
    <ErrorState v-else-if="error && !flow.case" :message="error" @retry="loadData" />

    <template v-else-if="flow.case">
      <section class="case-context-strip" data-testid="case-context" aria-label="目前案件">
        <div>
          <span>目前案件</span>
          <strong>{{ flow.case.caseNo }}</strong>
          <small>{{ flow.case.name }}</small>
        </div>
        <div class="case-context-strip__meta">
          <span>{{ flow.case.districtCode }}</span>
          <span>估價基準日 {{ flow.case.valuationBaseDate }}</span>
          <span>{{ statusLabel(f03Form?.status ?? 'DRAFT') }}</span>
        </div>
      </section>

      <section
        v-if="isRevisionRequired && reviewHandoff?.correction"
        v-liquid-glass
        data-lg
        class="valuation-surface revision-panel lg"
        data-testid="valuation-correction-request"
        aria-labelledby="revision-panel-title"
      >
        <div class="revision-panel__heading">
          <div>
            <p class="valuation-eyebrow">REVISION REQUIRED</p>
            <h2 id="revision-panel-title">第 {{ reviewHandoff.correction.request_no }} 次補正要求</h2>
          </div>
          <span>{{ new Date(reviewHandoff.correction.due_at).toLocaleString('zh-TW') }} 前</span>
        </div>
        <p class="revision-panel__message">{{ reviewHandoff.correction.message }}</p>
        <ul class="revision-panel__items">
          <li v-for="item in reviewHandoff.correction.items" :key="`${item.finding_code}-${item.document_id ?? 'case'}`">
            <div>
              <strong>{{ item.issue_summary }}</strong>
              <span>要求修正：{{ item.requested_correction }}</span>
              <small v-if="item.page_number">文件頁次：第 {{ item.page_number }} 頁</small>
            </div>
            <button class="finding-action" type="button" @click="goToCorrectionItem(item)">
              {{ item.document_id ? '前往文件處理' : '前往資料修正' }}
            </button>
          </li>
        </ul>
        <div v-if="formalSupplementMissingItems.length" class="revision-panel__missing">
          <strong>審查缺件</strong>
          <span v-for="item in formalSupplementMissingItems" :key="item.item_code">
            {{ item.item_name }}{{ item.reason ? `：${item.reason}` : '' }}
          </span>
        </div>
        <div class="revision-panel__actions">
          <button
            v-if="!revisionDraftReady"
            class="solid-button solid-button--primary"
            type="button"
            data-testid="prepare-revision-draft"
            :disabled="revisionInitializing"
            @click="ensureRevisionDrafts"
          >
            {{ revisionInitializing ? '建立補正版中…' : '建立補正版並帶入前一版資料' }}
          </button>
          <button
            v-else
            class="solid-button solid-button--primary"
            type="button"
            data-testid="open-revision-fields"
            @click="openRevisionFields"
          >
            補正版已建立，開始修正
          </button>
          <small>舊送審版本保持不可變；補正會建立較新的 F03 與正式報告版本。</small>
        </div>
      </section>

      <section
        v-if="formalSupplementMissingItems.length && !reviewHandoff?.correction"
        v-liquid-glass
        data-lg
        class="valuation-surface supplement-panel lg"
        data-testid="valuation-supplement-request"
        aria-labelledby="supplement-panel-title"
      >
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">SUPPLEMENT REQUIRED</p>
            <h2 id="supplement-panel-title">審查補件要求</h2>
          </div>
          <span class="value-kind">{{ formalSupplementMissingItems.length }} 項待補</span>
        </div>
        <p class="supplement-panel__intro">審查端已完成完整性檢查並提出補件要求。請逐項補齊後，再依正常送審流程建立新版正式輸出。</p>
        <ul class="supplement-panel__list">
          <li v-for="item in formalSupplementMissingItems" :key="item.item_code">
            <div>
              <strong>{{ item.item_name }}</strong>
              <span v-if="item.reason">{{ item.reason }}</span>
              <small v-if="item.due_at">期限：{{ new Date(item.due_at).toLocaleString('zh-TW') }}</small>
            </div>
            <button class="finding-action" type="button" @click="goToMissingItem(item)">
              {{ item.document_type ? '前往文件補件' : '前往資料補正' }}
            </button>
          </li>
        </ul>
      </section>

      <section class="wizard-status" data-testid="valuation-workflow-guide" aria-labelledby="workflow-guide-title">
        <div class="workflow-guide__copy">
          <div>
            <p class="valuation-eyebrow">目前進度</p>
            <h2 id="workflow-guide-title">{{ wizardStepTitle }}</h2>
          </div>
          <span class="workflow-guide__step">第 {{ activeWizardStep }} 步 / 6</span>
        </div>
        <div class="workflow-guide__stats">
          <span>來源文件 {{ flow.documents.length }} 份</span>
          <span v-if="workflowGuidance">AI 待確認 {{ workflowGuidance.pending_candidate_count }} 筆</span>
          <span v-if="f03Guidance">F03 缺欄位 {{ f03Guidance.missing_required_fields.length }} 項</span>
          <span v-if="flow.validation">檢核錯誤 {{ flow.validation.failedCount }} 項</span>
        </div>
        <button
          v-if="wizardIssueCounts[activeWizardStep]"
          class="finding-action"
          type="button"
          data-testid="workflow-next-action"
          @click="goToWorkflowNextAction"
        >
          查看第一個待處理項目
        </button>
      </section>

      <section v-if="activeWizardStep === 1 || activeWizardStep === 2" v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="case-summary-title">
        <div v-if="activeWizardStep === 1" class="surface-heading">
          <div>
            <p class="valuation-eyebrow">CASE SETUP</p>
            <h2 id="case-summary-title">{{ flow.case.caseNo }}｜{{ flow.case.name }}</h2>
          </div>
          <span class="source-marker" data-source-kind="automatic">{{ flow.case.source.label }}</span>
        </div>
        <div v-if="activeWizardStep === 1" class="summary-grid">
          <div><span>案件類型</span><strong>{{ flow.case.caseType }}</strong></div>
          <div><span>申請機關</span><strong>{{ flow.case.requestingAgency || '未提供' }}</strong></div>
          <div><span>估價基準日</span><strong>{{ flow.case.valuationBaseDate }}</strong></div>
          <div><span>行政區</span><strong>{{ flow.case.districtCode }}</strong></div>
        </div>
        <div v-if="activeWizardStep === 1" class="form-list" aria-label="已發現估價表">
          <div v-for="form in flow.forms" :key="form.formInstanceId" class="form-list__item">
            <strong>{{ form.formCode }}</strong>
            <span>第 {{ form.versionNo }} 版｜{{ statusLabel(form.status) }}</span>
            <small>{{ form.source.label }}</small>
          </div>
        </div>
        <div v-if="activeWizardStep === 2" id="valuation-document-workspace" class="document-workspace" tabindex="-1">
          <div class="document-workspace__heading">
            <div>
              <strong>來源文件與 AI 辨識</strong>
              <span>先選文件預覽，再執行 AI / OCR 辨識。辨識結果不會直接改寫正式資料，仍需人工確認。</span>
            </div>
            <span>{{ flow.documents.length }} 份</span>
          </div>
          <div class="document-ai-grid">
            <div class="document-ai-grid__list">
              <ul v-if="flow.documents.length" class="document-list">
                <li
                  v-for="document in flow.documents"
                  :key="document.documentId"
                  :class="{ 'is-selected': previewDocumentId === document.documentId }"
                >
                  <div class="document-list__identity">
                    <strong>{{ document.filename }}</strong>
                    <span>{{ documentCategoryLabel(document.documentType) }} · 第 {{ document.versionNo }} 版 · {{ formatFileSize(document.fileSizeBytes) }}</span>
                    <small :data-ai-state="documentPendingCount(document.documentId) ? 'pending' : 'ready'">{{ documentAiStatus(document.documentId) }}</small>
                  </div>
                  <div class="document-list__actions">
                    <button class="finding-action" type="button" @click="openDocumentPreview(document.documentId)">預覽</button>
                    <button
                      v-if="canExtractDocument(document)"
                      class="finding-action finding-action--primary"
                      type="button"
                      :data-testid="`extract-document-${document.documentId}`"
                      :disabled="Boolean(extractionBusyDocumentId)"
                      @click="extractDocument(document.documentId)"
                    >
                      {{ extractionBusyDocumentId === document.documentId ? 'AI 辨識中…' : documentCandidateCount(document.documentId) ? '重新 AI 辨識' : '開始 AI 辨識' }}
                    </button>
                    <div v-if="canManageSourceDocument(document)" class="document-list__manage">
                      <label :for="`document-category-${document.documentId}`">分類</label>
                      <select
                        :id="`document-category-${document.documentId}`"
                        v-model="documentCategoryDraft[document.documentId]"
                        :data-testid="`document-category-${document.documentId}`"
                        :disabled="documentActionId === document.documentId"
                      >
                        <option v-for="category in SOURCE_DOCUMENT_CATEGORIES" :key="category" :value="category">{{ documentCategoryLabel(category) }}</option>
                      </select>
                      <button class="finding-action" type="button" :data-testid="`reclassify-document-${document.documentId}`" :disabled="documentActionId === document.documentId || documentCategoryDraft[document.documentId] === document.documentType" @click="reclassifyDocument(document.documentId)">套用</button>
                      <button class="finding-action finding-action--danger" type="button" :data-testid="`remove-document-${document.documentId}`" :disabled="documentActionId === document.documentId" @click="removeDocument(document.documentId, document.filename)">移除</button>
                    </div>
                  </div>
                </li>
              </ul>
              <p v-else class="empty-copy">尚未上傳案件來源文件。請先選擇文件類型並上傳。</p>
            </div>

            <section class="document-preview" aria-labelledby="document-preview-title">
              <div class="document-preview__heading">
                <div>
                  <strong id="document-preview-title">文件預覽</strong>
                  <span v-if="previewDocument">{{ previewDocument.filename }}{{ previewPage ? ` · 第 ${previewPage} 頁` : '' }}</span>
                  <span v-else>從左側選擇一份文件查看內容</span>
                </div>
                <button v-if="previewDocument" class="finding-action" type="button" @click="downloadSourceDocument(previewDocument)">下載原檔</button>
              </div>
              <div class="document-preview__body">
                <p v-if="previewLoading" class="empty-copy">正在載入文件預覽…</p>
                <p v-else-if="previewError" class="document-preview__message">{{ previewError }}</p>
                <iframe v-else-if="previewIsPdf && previewSourceUrl" :src="previewSourceUrl" title="PDF 文件預覽" />
                <img v-else-if="previewIsImage && previewSourceUrl" :src="previewSourceUrl" :alt="previewDocument?.filename || '來源文件預覽'">
                <div v-else class="document-preview__empty">
                  <strong>{{ previewDocument ? '按「預覽」載入文件' : '尚未選擇文件' }}</strong>
                  <span>PDF 與圖片可直接顯示；其他格式仍可下載原檔查看。</span>
                </div>
              </div>
              <div v-if="selectedCandidate?.source_text && selectedCandidate.document_id === previewDocumentId" class="document-preview__evidence" data-testid="candidate-source-evidence">
                <strong>AI 對應原文{{ selectedCandidate.source_page ? ` · 第 ${selectedCandidate.source_page} 頁` : '' }}</strong>
                <blockquote>{{ selectedCandidate.source_text }}</blockquote>
              </div>
            </section>
          </div>
          <form v-if="canUpload" class="upload-form" @submit.prevent="uploadSourceDocument">
            <label><span>文件類型</span>
              <select v-model="uploadCategory">
                <option value="original">原始文件</option>
                <option value="cadastral-map">地籍圖</option>
                <option value="land-register">土地登記資料</option>
                <option value="photos">照片</option>
                <option value="attachments">其他附件</option>
                <option value="map-section-sketch">地段示意圖</option>
                <option value="map-zoning">使用分區圖</option>
                <option value="map-land-value-section">地價區段圖</option>
              </select>
            </label>
            <label class="upload-form__file"><span>選擇檔案</span><input id="valuation-source-file" type="file" required @change="chooseUpload" /></label>
            <button class="solid-button" type="submit" :disabled="uploading || !uploadFile">
              {{ uploading ? '上傳中…' : '上傳文件' }}
            </button>
          </form>
        </div>
      </section>

      <section
        v-if="activeWizardStep === 2"
        id="valuation-candidate-workspace"
        v-liquid-glass
        data-lg
        class="valuation-surface candidate-workspace lg"
        data-testid="valuation-candidate-workspace"
        tabindex="-1"
        aria-labelledby="candidate-workspace-title"
      >
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">AI REVIEW</p>
            <h2 id="candidate-workspace-title">AI 辨識結果</h2>
          </div>
          <div class="candidate-workspace__summary">
            <span class="value-kind">待確認 {{ pendingCandidates.length }} 筆</span>
            <button
              v-if="workflowGuidance?.confirmation_export"
              class="finding-action"
              type="button"
              data-testid="download-confirmation-export"
              @click="downloadConfirmationExport"
            >下載確認 Excel</button>
          </div>
        </div>
        <p v-if="!candidateDecisionTargets.length" class="empty-copy">
          目前沒有需要人工確認的 AI 辨識結果。請在上方來源文件按「開始 AI 辨識」。
        </p>
        <div v-else class="candidate-list">
          <article
            v-for="candidate in candidateDecisionTargets"
            :key="candidate.extracted_field_id"
            :class="['candidate-card', { 'is-active': selectedCandidateId === candidate.extracted_field_id }]"
            :data-testid="`candidate-${candidate.extracted_field_id}`"
            @click="selectedCandidateId = candidate.extracted_field_id"
          >
            <div class="candidate-card__heading">
              <div>
                <strong>{{ fieldDisplayLabel(candidate.form_code, candidate.field_name) }}</strong>
                <span>{{ candidateDocumentName(candidate.document_id) }}{{ candidate.source_page ? ` · 第 ${candidate.source_page} 頁` : '' }}</span>
              </div>
              <small>{{ candidate.field_status === 'NEEDS_CONFIRMATION' ? '待確認' : '重新確認中' }} · 信心度 {{ candidateConfidenceLabel(candidate) }} · {{ candidate.analysis_provider }}</small>
            </div>
            <div v-if="candidate.source_text" class="candidate-card__source-summary">
              <span>來源原文</span>
              <blockquote class="candidate-card__source">{{ candidate.source_text }}</blockquote>
              <button class="candidate-card__source-link" type="button" @click.stop="openCandidateSource(candidate)">在原文件中查看</button>
            </div>
            <label class="candidate-card__value">
              <span>AI 辨識值／人工修正值 <small v-if="candidateUnit(candidate)">({{ candidateUnit(candidate) }})</small></span>
              <input v-model="candidateValue[candidate.extracted_field_id]" :data-testid="`candidate-value-${candidate.extracted_field_id}`" :type="candidateEditorType(candidate)" :step="candidateEditorType(candidate) === 'number' ? 'any' : undefined" :disabled="candidateDecision[candidate.extracted_field_id] === 'REJECT'">
            </label>
            <div class="candidate-card__actions" role="group" :aria-label="`${candidate.field_name} 人工判定`">
              <button
                type="button"
                :class="{ 'is-selected': candidateDecision[candidate.extracted_field_id] === 'CONFIRM' }"
                :data-testid="`candidate-confirm-${candidate.extracted_field_id}`"
                @click="chooseCandidateDecision(candidate.extracted_field_id, 'CONFIRM')"
              >
                確認採用
              </button>
              <button
                type="button"
                :class="{ 'is-selected is-reject': candidateDecision[candidate.extracted_field_id] === 'REJECT' }"
                :data-testid="`candidate-reject-${candidate.extracted_field_id}`"
                @click="chooseCandidateDecision(candidate.extracted_field_id, 'REJECT')"
              >
                不採用
              </button>
            </div>
          </article>
          <div class="candidate-submit">
            <span>已選擇 {{ selectedCandidateCount }} / {{ candidateDecisionTargets.length }} 筆判定</span>
            <button
              class="solid-button solid-button--primary"
              type="button"
              data-testid="submit-candidate-decisions"
              :disabled="!selectedCandidateCount || confirmingCandidates"
              @click="submitCandidateDecisions"
            >
              {{ confirmingCandidates ? '保存判定中…' : '保存已選判定並套用' }}
            </button>
          </div>
        </div>

        <div v-if="processedCandidates.length" class="candidate-history" data-testid="processed-candidates">
          <div class="candidate-history__heading">
            <strong>已處理 AI 辨識結果</strong>
            <span>已採用資料若需要補正，可以重新開啟、修改後再次套用。</span>
          </div>
          <ul>
            <li v-for="candidate in processedCandidates" :key="`processed-${candidate.extracted_field_id}`">
              <div>
                <strong>{{ candidate.form_code }} · {{ candidate.field_name }}</strong>
                <span>{{ candidate.field_status }} · {{ displayCandidateValue(candidate.confirmed_value ?? candidate.extracted_value) || '未採用值' }}</span>
              </div>
              <button
                v-if="candidate.field_status !== 'REJECTED' && !candidateDecision[candidate.extracted_field_id]"
                class="finding-action"
                type="button"
                :data-testid="`reopen-candidate-${candidate.extracted_field_id}`"
                @click="reopenCandidate(candidate)"
              >重新修改</button>
            </li>
          </ul>
        </div>
      </section>

      <section v-if="activeWizardStep === 3" class="data-confirmation-nav" aria-labelledby="data-confirmation-title">
        <div class="data-confirmation-nav__heading">
          <div>
            <p class="valuation-eyebrow">DATA CONFIRMATION</p>
            <h2 id="data-confirmation-title">資料確認</h2>
            <span>只顯示目前要處理的資料類別；有缺漏時可從上方狀態或下方總覽直接跳轉。</span>
          </div>
          <span class="value-kind">待處理 {{ dataIssueCounts.overview }} 項</span>
        </div>
        <nav class="data-subnav" aria-label="資料確認子選單">
          <button type="button" :class="{ 'is-active': activeDataSection === 'overview' }" data-testid="data-section-overview" @click="activeDataSection = 'overview'">
            <strong>總覽</strong><small>{{ dataIssueCounts.overview ? `${dataIssueCounts.overview} 待處理` : '已完成' }}</small>
          </button>
          <button type="button" :class="{ 'is-active': activeDataSection === 'manual' }" data-testid="data-section-manual" @click="activeDataSection = 'manual'">
            <strong>人工補充</strong><small>{{ dataIssueCounts.manual ? `${dataIssueCounts.manual} 可補充` : '無缺漏' }}</small>
          </button>
          <button type="button" :class="{ 'is-active': activeDataSection === 'land' }" data-testid="data-section-land" @click="activeDataSection = 'land'">
            <strong>宗地與比準地</strong><small>{{ dataIssueCounts.land ? `${dataIssueCounts.land} 待處理` : '已建立' }}</small>
          </button>
          <button type="button" :class="{ 'is-active': activeDataSection === 'f03' }" data-testid="data-section-f03" @click="activeDataSection = 'f03'">
            <strong>F03 正式資料</strong><small>{{ dataIssueCounts.f03 ? `${dataIssueCounts.f03} 缺欄位` : flow.f03 ? '可編輯' : '尚未建立' }}</small>
          </button>
        </nav>

        <div v-if="activeDataSection === 'overview'" class="data-overview">
          <article :data-state="dataIssueCounts.manual ? 'attention' : 'ready'">
            <div><strong>人工補充</strong><span>AI / OCR 沒有取得的欄位，可在這裡人工補齊。</span></div>
            <div><small>{{ dataIssueCounts.manual ? `${dataIssueCounts.manual} 項可補充` : '目前沒有缺漏欄位' }}</small><button type="button" @click="jumpToDataSection('manual')">前往</button></div>
          </article>
          <article :data-state="dataIssueCounts.land ? 'attention' : 'ready'">
            <div><strong>宗地與比準地</strong><span>確認宗地基本資料與後續計算使用的比準地。</span></div>
            <div><small>{{ parcels.length }} 宗地 · {{ flow.benchmarks.length }} 比準地</small><button type="button" @click="jumpToDataSection('land')">前往</button></div>
          </article>
          <article :data-state="dataIssueCounts.f03 ? 'attention' : flow.f03 ? 'ready' : 'attention'">
            <div><strong>F03 正式資料</strong><span>確認最後會進入公式計算與正式檢核的採用值。</span></div>
            <div><small>{{ flow.f03 ? dataIssueCounts.f03 ? `${dataIssueCounts.f03} 欄未完成` : '正式資料可編輯' : '尚未建立 F03' }}</small><button type="button" @click="jumpToDataSection('f03')">前往</button></div>
          </article>
        </div>
      </section>

      <section
        v-if="activeWizardStep === 3 && activeDataSection === 'manual' && workflowGuidance && manualFieldEntries.length"
        v-liquid-glass
        data-lg
        class="valuation-surface manual-fields lg"
        data-testid="manual-field-workspace"
        aria-labelledby="manual-fields-title"
      >
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">MANUAL FALLBACK</p>
            <h2 id="manual-fields-title">AI / OCR 未取得欄位的人工補充</h2>
          </div>
          <span class="value-kind">{{ manualFieldEntries.length }} 項</span>
        </div>
        <p class="manual-fields__intro">只會送出非空欄位。後端會依正式表單契約寫入可直接套用的值；其餘值保留為人工覆寫稽核資料，不會偷偷填入不相容欄位。</p>
        <div class="manual-fields__grid">
          <label v-for="entry in manualFieldEntries" :key="entry.key">
            <span>{{ fieldDisplayLabel(entry.formCode, entry.fieldName) }}</span>
            <input
              v-model="manualFieldValue[entry.key]"
              :data-testid="`manual-field-${entry.formCode}-${entry.fieldName}`"
              type="text"
              autocomplete="off"
            >
            <small v-if="workflowGuidance.manual_field_errors?.[entry.key]" class="manual-fields__error">
              {{ workflowGuidance.manual_field_errors?.[entry.key] }}
            </small>
          </label>
        </div>
        <div class="candidate-submit">
          <span>人工輸入會覆蓋先前同欄位的人工值，並使相關正式輸出需要重新計算／檢核。</span>
          <button
            class="solid-button solid-button--primary"
            type="button"
            data-testid="save-manual-fields"
            :disabled="manualFieldsSaving"
            @click="saveManualFields"
          >{{ manualFieldsSaving ? '儲存中…' : '儲存人工補充資料' }}</button>
        </div>
      </section>

      <section v-if="activeWizardStep === 3 && activeDataSection === 'manual' && !manualFieldEntries.length" class="valuation-surface data-complete-state">
        <strong>目前沒有需要人工補充的欄位</strong>
        <span>AI 辨識與既有資料已提供目前可確認的欄位；你可以直接前往宗地與比準地或 F03。</span>
      </section>

      <section
        v-if="activeWizardStep === 3 && activeDataSection === 'land'"
        id="valuation-land-context"
        v-liquid-glass
        data-lg
        class="valuation-surface land-context lg"
        data-testid="valuation-land-context"
        tabindex="-1"
        aria-labelledby="land-context-title"
      >
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">LAND CONTEXT</p>
            <h2 id="land-context-title">宗地與比準地</h2>
          </div>
          <span class="value-kind">宗地 {{ parcels.length }} · 比準地 {{ flow.benchmarks.length }}</span>
        </div>
        <div class="land-context__grid">
          <section class="land-context__panel">
            <div class="land-context__panel-heading"><strong>宗地資料</strong><span>後端支援新增與修改</span></div>
            <ul v-if="parcels.length" class="land-context__records">
              <li v-for="parcel in parcels" :key="parcel.parcel_id">
                <div>
                  <strong>{{ parcel.section_name }} {{ parcel.land_no }}</strong>
                  <span>{{ parcel.area_sqm }} m² · {{ parcel.district_code }}</span>
                </div>
                <button v-if="canEditLandContext" type="button" :data-testid="`edit-parcel-${parcel.parcel_id}`" @click="startParcelEdit(parcel)">修改</button>
              </li>
            </ul>
            <p v-else class="empty-copy">尚未建立宗地；請直接使用下方表單建立。</p>
            <form id="parcel-editor" class="land-context__form" tabindex="-1" @submit.prevent="saveParcel">
              <h3>{{ editingParcelId ? '修改宗地' : '新增宗地' }}</h3>
              <div class="land-context__fields">
                <label><span>行政區代碼 *</span><input v-model="parcelDraft.districtCode" data-testid="parcel-district-code" required></label>
                <label><span>段名 *</span><input v-model="parcelDraft.sectionName" data-testid="parcel-section-name" required></label>
                <label><span>小段</span><input v-model="parcelDraft.subsectionName"></label>
                <label><span>地號 *</span><input v-model="parcelDraft.landNo" data-testid="parcel-land-no" required></label>
                <label><span>面積 m² *</span><input v-model="parcelDraft.areaSqm" data-testid="parcel-area-sqm" inputmode="decimal" required></label>
                <label><span>使用分區</span><input v-model="parcelDraft.landUseZone"></label>
                <label><span>指定用途</span><input v-model="parcelDraft.designatedUse"></label>
                <label><span>來源文件</span>
                  <select v-model="parcelDraft.sourceDocumentId">
                    <option value="">不指定</option>
                    <option v-for="document in flow.documents" :key="document.documentId" :value="document.documentId">{{ document.filename }}</option>
                  </select>
                </label>
              </div>
              <div class="land-context__form-actions">
                <button v-if="editingParcelId" type="button" class="solid-button" @click="resetParcelDraft">取消修改</button>
                <button class="solid-button solid-button--primary" type="submit" data-testid="save-parcel" :disabled="!canEditLandContext || landContextSaving">
                  {{ landContextSaving ? '儲存中…' : editingParcelId ? '儲存宗地修改' : '建立宗地' }}
                </button>
              </div>
            </form>
          </section>

          <section class="land-context__panel">
            <div class="land-context__panel-heading"><strong>比準地資料</strong><span>後端目前支援新增；既有比準地不提供直接修改</span></div>
            <ul v-if="flow.benchmarks.length" class="land-context__records">
              <li v-for="benchmark in flow.benchmarks" :key="benchmark.benchmarkLandId">
                <div>
                  <strong>{{ benchmark.benchmarkLandNo }}</strong>
                  <span>地價區段 {{ benchmark.priceZoneNo }}</span>
                </div>
              </li>
            </ul>
            <p v-else class="empty-copy">尚未建立比準地；建立後才能初始化／選擇 F03 基準地。</p>
            <form class="land-context__form" @submit.prevent="saveBenchmarkLand">
              <h3>新增比準地</h3>
              <div class="land-context__fields">
                <label><span>來源宗地 *</span>
                  <select v-model="benchmarkDraft.parcelId" data-testid="benchmark-parcel" required>
                    <option value="">請選擇宗地</option>
                    <option v-for="parcel in parcels" :key="parcel.parcel_id" :value="parcel.parcel_id">{{ parcel.section_name }} {{ parcel.land_no }}</option>
                  </select>
                </label>
                <label><span>比準地編號 *</span><input v-model="benchmarkDraft.benchmarkLandNo" data-testid="benchmark-no" required></label>
                <label><span>地價區段 *</span><input v-model="benchmarkDraft.priceZoneNo" data-testid="benchmark-zone" required></label>
                <label><span>重劃序號</span><input v-model="benchmarkDraft.landConsolidationSerial"></label>
                <label><span>緯度</span><input v-model="benchmarkDraft.latitude" inputmode="decimal"></label>
                <label><span>經度</span><input v-model="benchmarkDraft.longitude" inputmode="decimal"></label>
              </div>
              <div class="land-context__form-actions">
                <button class="solid-button solid-button--primary" type="submit" data-testid="save-benchmark" :disabled="!canEditLandContext || !parcels.length || landContextSaving">
                  {{ landContextSaving ? '儲存中…' : '建立比準地' }}
                </button>
              </div>
            </form>
          </section>
        </div>
      </section>

      <section v-if="activeWizardStep === 3 && activeDataSection === 'f03' && !flow.f03" v-liquid-glass data-lg class="valuation-surface setup-required lg" aria-labelledby="setup-required-title">
        <div>
          <p class="valuation-eyebrow">REQUIRED DATA</p>
          <h2 id="setup-required-title">估價資料尚未可計算</h2>
        </div>
        <p>系統不會以空值直接送出。請先完成必要來源文件、宗地與比準地資料；待後端建立 F03 正式草稿後，計算與檢核按鈕才會開放。</p>
      </section>

      <section id="f03-data-section" v-if="activeWizardStep === 3 && activeDataSection === 'f03' && flow.f03" v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="f03-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">F03 正式資料</p>
            <h2 id="f03-title">資料確認與正式採用值</h2>
          </div>
          <span class="source-marker" data-source-kind="human-confirmed">{{ flow.f03.source.label }}</span>
        </div>

        <div class="official-value" data-testid="official-value">
          <div>
            <span>基準地正式採用價格</span>
            <strong>{{ flow.f03.benchmarkLandPrice || '尚未由伺服器提供' }}</strong>
          </div>
          <span class="value-kind" data-value-kind="calculated" data-source-kind="calculated">{{ calculatedSource.label }}</span>
        </div>

        <form class="confirmed-form" @submit.prevent="handleSave">
          <div class="form-heading">
            <h3>人工確認欄位</h3>
            <span class="value-kind" data-value-kind="human-confirmed">可編輯欄位依 F03 PATCH 契約</span>
          </div>
          <fieldset class="field-grid" :disabled="!canEditF03">
            <label>
              <span>基準地</span>
              <select
                id="f03-benchmark-land"
                v-model="draft.benchmarkLandId"
                data-value-kind="human-confirmed"
                @input="dirty = true"
              >
                <option :value="null">請選擇基準地</option>
                <option v-for="land in flow.benchmarks" :key="land.benchmarkLandId" :value="land.benchmarkLandId">
                  {{ land.benchmarkLandNo }}｜{{ land.priceZoneNo }}
                </option>
              </select>
            </label>
            <label>
              <span>估價基準日</span>
              <input id="f03-valuation-base-date" v-model="draft.valuationBaseDate" type="date" @input="dirty = true" />
            </label>
            <label>
              <span>比較法價格（正式值）</span>
              <input
                v-model="draft.comparisonPrice"
                id="f03-comparison-price"
                data-testid="f03-comparison-price"
                inputmode="decimal"
                @input="dirty = true"
              />
            </label>
            <label>
              <span>比較法權重</span>
              <input id="f03-comparison-weight" v-model="draft.comparisonWeight" inputmode="decimal" @input="dirty = true" />
            </label>
            <label>
              <span>收益法價格（正式值）</span>
              <input id="f03-income-price" v-model="draft.incomePrice" inputmode="decimal" @input="dirty = true" />
            </label>
            <label>
              <span>收益法權重</span>
              <input id="f03-income-weight" v-model="draft.incomeWeight" inputmode="decimal" @input="dirty = true" />
            </label>
            <label>
              <span>市場期間起日</span>
              <input id="f03-market-period-start" v-model="draft.marketPeriodStart" type="date" @input="dirty = true" />
            </label>
            <label>
              <span>市場期間迄日</span>
              <input id="f03-market-period-end" v-model="draft.marketPeriodEnd" type="date" @input="dirty = true" />
            </label>
            <label class="field-grid__wide">
              <span>市場條件</span>
              <input id="f03-market-condition" v-model="draft.marketCondition" @input="dirty = true" />
            </label>
            <label class="field-grid__wide">
              <span>選擇範圍理由</span>
              <textarea id="f03-selection-scope-reason" v-model="draft.selectionScopeReason" rows="2" @input="dirty = true" />
            </label>
            <label class="field-grid__wide">
              <span>採用決策理由</span>
              <textarea id="f03-decision-reason" v-model="draft.decisionReason" rows="2" @input="dirty = true" />
            </label>
          </fieldset>
          <div class="action-row">
            <button class="solid-button" data-testid="save-confirmed-fields" type="submit" :disabled="saving || !canEditF03">
              {{ saving ? '儲存中…' : '儲存確認欄位' }}
            </button>
          </div>
        </form>
      </section>

      <section v-if="activeWizardStep === 4" class="valuation-surface calculation-launch" data-testid="calculation-launch" aria-labelledby="calculation-launch-title">
        <div class="calculation-launch__copy">
          <div>
            <p class="valuation-eyebrow">CALCULATE & VALIDATE</p>
            <h2 id="calculation-launch-title">計算與檢核</h2>
            <p>系統會使用已確認的 F03 正式資料執行公式計算，再以伺服器規則檢查缺漏與一致性。若有阻擋，結果會直接提供修正位置。</p>
          </div>
          <div class="calculation-launch__readiness">
            <span :data-state="flow.f03 ? 'ready' : 'blocked'">{{ flow.f03 ? 'F03 已建立' : '缺少 F03' }}</span>
            <span :data-state="dirty ? 'attention' : 'ready'">{{ dirty ? '有尚未儲存的修改' : '資料已同步' }}</span>
          </div>
        </div>
        <button
          class="solid-button solid-button--primary calculation-launch__button"
          type="button"
          data-testid="run-valuation"
          :disabled="running || saving || !canEditF03"
          :title="dirty ? '會先儲存尚未保存的 F03 修改，再執行計算與檢核' : '執行正式計算與檢核'"
          @click="runValuation"
        >
          {{ running ? '伺服器計算與檢核中…' : dirty ? '儲存修改並執行計算與檢核' : '執行計算與檢核' }}
        </button>
      </section>

      <p v-if="notice" class="inline-notice" role="status">{{ notice }}</p>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>

      <section v-if="activeWizardStep === 4 && flow.validation" v-liquid-glass data-lg class="valuation-surface lg validation-results" data-testid="validation-results" aria-labelledby="validation-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">SERVER VALIDATION</p>
            <h2 id="validation-title">伺服器檢核結果</h2>
          </div>
          <span class="value-kind" :data-validation-state="flow.validation.canGenerateReport ? 'ready' : 'blocked'">
            {{ flow.validation.canGenerateReport ? '可產生正式輸出' : '有伺服器阻擋項目' }}
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
            <small><b>問題位置：</b>{{ findingLocationLabel(finding) }}</small>
            <small>實際值：{{ finding.actualValue ?? '—' }}</small>
            <small>預期值（expected）：{{ finding.expectedValue ?? '—' }}</small>
            <small><b>建議修正：</b>{{ findingCorrectionHint(finding) }}</small>
            <button class="finding-action" type="button" :data-testid="`fix-finding-${finding.findingId}`" @click="goToFinding(finding)">
              前往修正
            </button>
          </li>
        </ul>
        <p v-else class="empty-copy">伺服器沒有回傳其他檢核訊息。</p>
        <div v-if="flow.validation.correctionHints.length" class="correction-hints">
          <strong>伺服器修正提示</strong>
          <ul>
            <li v-for="hint in flow.validation.correctionHints" :key="hint">{{ hint }}</li>
          </ul>
        </div>

        <div v-if="flow.calculation" class="calculation-result" data-testid="calculation-result" data-source-kind="calculated">
          <span>伺服器計算正式結果</span>
          <strong>{{ flow.calculation.result }} {{ flow.calculation.currencyCode }}</strong>
          <small>公式版本：{{ flow.calculation.formulaVersion }}</small>
        </div>
        <div v-if="flow.report" class="report-result" data-testid="report-result">
          <span>正式輸出</span>
          <strong>{{ flow.report.filename }}</strong>
          <small>第 {{ flow.report.versionNo }} 版｜{{ flow.report.fileSizeBytes }} bytes</small>
        </div>
        <button
          class="solid-button solid-button--primary"
          type="button"
          data-testid="go-to-submit"
          :disabled="!canProceedToSubmit"
          :title="canProceedToSubmit ? '前往輸出預覽與送審' : '必須先修正 ERROR 並通過檢核'"
          @click="goToSubmit"
        >
          {{ canProceedToSubmit ? '前往輸出預覽與送審' : '請先完成阻擋項目' }}
        </button>
      </section>

      <footer v-if="activeWizardStep <= 4" class="wizard-footer" aria-label="估價流程導覽">
        <button class="wizard-footer__secondary" type="button" :disabled="activeWizardStep === 1" @click="wizardPrevious">← 上一步</button>
        <div class="wizard-footer__status">
          <strong>第 {{ activeWizardStep }} 步 / 6</strong>
          <span>{{ wizardNextLabel }}</span>
        </div>
        <button
          class="wizard-footer__primary"
          type="button"
          data-testid="wizard-next"
          :disabled="activeWizardStep === 4 && !canProceedToSubmit"
          @click="wizardNext"
        >
          {{ wizardNextLabel }} →
        </button>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.valuation-view {
  display: grid;
  gap: 18px;
  padding: 24px 28px 34px;
}

.valuation-surface {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-paper-strong);
  box-shadow: var(--app-shadow-soft);
}

.case-context-strip { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:11px 14px; border:1px solid #d9e3ee; border-radius:11px; background:#f8fbfe; }
.case-context-strip > div:first-child { display:flex; align-items:baseline; flex-wrap:wrap; gap:7px; min-width:0; }
.case-context-strip > div:first-child > span { color:var(--app-muted); font-size:10px; font-weight:800; }
.case-context-strip > div:first-child > strong { color:var(--app-ink); font-size:13px; }
.case-context-strip > div:first-child > small { overflow:hidden; color:var(--app-ink-soft); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.case-context-strip__meta { display:flex; align-items:center; flex-wrap:wrap; justify-content:flex-end; gap:6px; }
.case-context-strip__meta span { padding:5px 8px; border-radius:999px; color:#52657a; background:#edf2f7; font-size:9px; font-weight:800; }

.surface-heading,
.form-heading,
.action-row,
.official-value,
.calculation-result,
.report-result {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.surface-heading { margin-bottom: 18px; }
.surface-heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; font-weight: 600; letter-spacing: -0.04em; }
.valuation-eyebrow { margin: 0 0 6px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: 0.12em; }
.source-marker, .value-kind { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 10px; border: 1px solid var(--app-line); border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f8fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.source-marker[data-source-kind="automatic"] { border-color: rgba(59, 129, 102, 0.24); color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.source-marker[data-source-kind="human-confirmed"] { border-color: rgba(200, 91, 67, 0.24); color: var(--app-accent-deep); background: rgba(200, 91, 67, 0.08); }
.value-kind[data-source-kind="calculated"] { border-color: rgba(46, 89, 132, 0.22); color: #2e5984; background: #edf4fb; }
.value-kind[data-value-kind="calculated"] { border-color: rgba(46, 89, 132, 0.22); color: #2e5984; background: #edf4fb; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.summary-grid div { display: grid; gap: 5px; padding: 13px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.revision-panel { display: grid; gap: 14px; border-color: rgba(200, 91, 67, .26); background: rgba(255, 246, 242, .86); }
.revision-panel__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.revision-panel__heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; }
.revision-panel__heading > span { padding: 7px 10px; border-radius: var(--app-radius-pill); color: #a44334; background: #fff0ed; font-size: 11px; font-weight: 900; white-space: nowrap; }
.revision-panel__message { margin: 0; color: var(--app-ink); font-size: 13px; font-weight: 700; line-height: 1.7; white-space: pre-line; }
.revision-panel__items { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.revision-panel__items li { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 13px; border-left: 4px solid #c85b43; border-radius: 8px; background: rgba(255,255,255,.8); }
.revision-panel__items li > div { display: grid; gap: 4px; min-width: 0; }
.revision-panel__items strong { color: var(--app-ink); font-size: 12px; }
.revision-panel__items span { color: var(--app-ink-soft); font-size: 12px; line-height: 1.6; }
.revision-panel__items small { color: var(--app-muted); font-size: 10px; }
.revision-panel__missing { display: grid; gap: 5px; padding: 11px 12px; border: 1px solid rgba(214,166,62,.28); border-radius: 9px; background: #fffaf0; }
.revision-panel__missing strong { color: var(--app-ink); font-size: 11px; }
.revision-panel__missing span { color: var(--app-ink-soft); font-size: 11px; }
.revision-panel__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.revision-panel__actions small { color: var(--app-muted); font-size: 11px; line-height: 1.5; }
.workflow-guide { display: grid; gap: 14px; border-color: rgba(46, 89, 132, .18); background: rgba(246, 250, 255, .82); }
.workflow-guide__copy { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.workflow-guide__copy h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; }
.workflow-guide__step { padding: 7px 11px; border-radius: var(--app-radius-pill); color: #2e5984; background: #edf4fb; font-size: 11px; font-weight: 900; white-space: nowrap; }
.workflow-guide__next { margin: 0; color: var(--app-ink); font-size: 14px; font-weight: 800; line-height: 1.6; }
.workflow-guide__stats { display: flex; flex-wrap: wrap; gap: 8px; }
.workflow-guide__stats span { padding: 7px 10px; border-radius: 8px; color: var(--app-ink-soft); background: rgba(255,255,255,.82); font-size: 11px; font-weight: 800; }
.workflow-guide__issues { display: grid; gap: 8px; }
.workflow-guide__issues div { display: grid; gap: 4px; padding: 10px 12px; border-left: 3px solid #d6a63e; background: #fffaf0; }
.workflow-guide__issues strong { color: var(--app-ink); font-size: 11px; }
.workflow-guide__issues span { color: var(--app-ink-soft); font-size: 12px; line-height: 1.55; overflow-wrap: anywhere; }
.workflow-guide > .solid-button { justify-self: start; }
.form-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.form-list__item { display: grid; gap: 3px; padding: 10px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; font-size: 11px; }
.form-list__item strong { color: var(--app-ink); font-size: 12px; }
.form-list__item small { color: var(--app-muted); }
.document-workspace { display: grid; gap: 12px; margin-top: 16px; padding: 14px; border: 1px solid var(--app-line); border-radius: 14px; background: rgba(255,255,255,.55); }
.document-workspace__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.document-workspace__heading div { display: grid; gap: 3px; }
.document-workspace__heading strong { color: var(--app-ink); }
.document-workspace__heading span { color: var(--app-muted); font-size: 11px; }
.document-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.document-list li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 11px; border-radius: 10px; background: rgba(247,249,252,.84); }
.document-list li div { display: grid; gap: 2px; min-width: 0; }
.document-list li strong { overflow: hidden; color: var(--app-ink); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.document-list li span { color: var(--app-muted); font-size: 10px; }
.document-list__actions { display: flex !important; align-items: flex-end; gap: 6px !important; }
.document-list__actions .finding-action { margin-top: 0; white-space: nowrap; }
.document-list__manage { display: grid !important; grid-template-columns: auto minmax(130px, 190px) auto auto; align-items: center; gap: 6px !important; }
.document-list__manage label { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.document-list__manage select { min-height: 36px; padding: 6px 8px; border: 1px solid var(--app-line); border-radius: 7px; color: var(--app-ink); background: #fff; font-size: 11px; }
.finding-action--danger { border-color: rgba(164,67,52,.28); color: #a44334; }
.upload-form { display: grid; grid-template-columns: 180px minmax(0,1fr) auto; align-items: end; gap: 10px; }
.upload-form label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.upload-form select,
.upload-form input { min-height: 44px; padding: 8px 10px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink); background: rgba(255,255,255,.82); }
.supplement-panel { border-color: rgba(214,166,62,.32); background: rgba(255,250,240,.88); }
.supplement-panel__intro { margin: -4px 0 14px; color: var(--app-ink-soft); font-size: 12px; line-height: 1.65; }
.supplement-panel__list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.supplement-panel__list li { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 11px 12px; border: 1px solid rgba(214,166,62,.2); border-radius: 9px; background: rgba(255,255,255,.76); }
.supplement-panel__list li > div { display: grid; gap: 4px; min-width: 0; }
.supplement-panel__list strong { color: var(--app-ink); font-size: 12px; }
.supplement-panel__list span { color: var(--app-ink-soft); font-size: 12px; line-height: 1.55; }
.supplement-panel__list small { color: var(--app-muted); font-size: 10px; }
.candidate-workspace { border-color: rgba(46,89,132,.18); }
.candidate-workspace__summary { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.candidate-list { display: grid; gap: 10px; }
.candidate-card { display: grid; gap: 12px; padding: 15px; border: 1px solid var(--app-line); border-radius: 11px; background: #fbfcfe; }
.candidate-card__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.candidate-card__heading > div { display: grid; gap: 4px; min-width: 0; }
.candidate-card__heading strong { color: var(--app-ink); font-size: 13px; }
.candidate-card__heading span, .candidate-card__heading small { color: var(--app-muted); font-size: 10px; }
.candidate-card__source { margin: 0; padding: 10px 12px; border-left: 3px solid rgba(46,89,132,.35); color: var(--app-ink-soft); background: #f3f7fb; font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
.candidate-card__source-summary { display:grid; gap:6px; }
.candidate-card__source-summary > span { color:var(--app-muted); font-size:10px; font-weight:850; }
.candidate-card__value { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.candidate-card__value input { width: 100%; min-height: 44px; padding: 9px 11px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; }
.candidate-card__actions { display: flex; flex-wrap: wrap; gap: 8px; }
.candidate-card__actions button { min-height: 38px; padding: 7px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 11px; font-weight: 900; }
.candidate-card__actions button.is-selected { border-color: rgba(59,129,102,.4); color: var(--app-green); background: rgba(59,129,102,.08); }
.candidate-card__actions button.is-reject { border-color: rgba(200,91,67,.35); color: var(--app-accent-deep); background: rgba(200,91,67,.07); }
.candidate-submit { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 4px; }
.candidate-submit > span { color: var(--app-muted); font-size: 11px; }
.candidate-history { display: grid; gap: 9px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--app-line); }
.candidate-history__heading { display: grid; gap: 3px; }
.candidate-history__heading strong { color: var(--app-ink); font-size: 12px; }
.candidate-history__heading span { color: var(--app-muted); font-size: 11px; }
.candidate-history ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.candidate-history li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 11px; border-radius: 9px; background: rgba(247,249,252,.84); }
.candidate-history li > div { display: grid; gap: 3px; min-width: 0; }
.candidate-history li strong { color: var(--app-ink); font-size: 11px; }
.candidate-history li span { overflow-wrap: anywhere; color: var(--app-muted); font-size: 10px; }
.manual-fields { border-color: rgba(59,129,102,.2); }
.manual-fields__intro { margin: -4px 0 14px; color: var(--app-ink-soft); font-size: 12px; line-height: 1.65; }
.manual-fields__grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 10px; }
.manual-fields__grid label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.manual-fields__grid input { min-height: 42px; padding: 8px 10px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; }
.manual-fields__error { color: #a44334; font-size: 10px; line-height: 1.5; }
.land-context__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.land-context__panel { display: grid; align-content: start; gap: 12px; padding: 15px; border: 1px solid var(--app-line); border-radius: 11px; background: #fbfcfe; }
.land-context__panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.land-context__panel-heading strong { color: var(--app-ink); font-size: 13px; }
.land-context__panel-heading span { color: var(--app-muted); font-size: 10px; text-align: right; }
.land-context__records { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.land-context__records li { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px; border-radius: 8px; background: #fff; }
.land-context__records li > div { display: grid; gap: 3px; min-width: 0; }
.land-context__records strong { color: var(--app-ink); font-size: 12px; }
.land-context__records span { color: var(--app-muted); font-size: 10px; }
.land-context__records button { min-height: 34px; padding: 5px 9px; border: 1px solid var(--app-line); border-radius: 7px; color: var(--app-accent-deep); background: #fff; cursor: pointer; font-size: 10px; font-weight: 900; }
.land-context__form { display: grid; gap: 10px; padding-top: 11px; border-top: 1px solid var(--app-line); }
.land-context__form h3 { margin: 0; color: var(--app-ink); font-size: 13px; }
.land-context__fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
.land-context__fields label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 10px; font-weight: 800; }
.land-context__fields input, .land-context__fields select { width: 100%; min-height: 42px; padding: 8px 9px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; }
.land-context__form-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.setup-required { display: grid; gap: 10px; border-color: rgba(214,166,62,.28); background: rgba(255,250,240,.78); }
.setup-required h2 { margin: 0; color: var(--app-ink); }
.setup-required p:last-child { margin: 0; color: var(--app-ink-soft); line-height: 1.7; }
.summary-grid span, .official-value span, .calculation-result span, .report-result span { color: var(--app-muted); font-size: 11px; font-weight: 800; }
.summary-grid strong { color: var(--app-ink); font-size: 14px; }
.source-note { margin: 14px 0 0; color: var(--app-muted); font-size: 12px; }
.official-value { align-items: center; margin-bottom: 20px; padding: 16px; border: 1px solid rgba(46, 89, 132, 0.18); border-radius: var(--app-radius-sm); background: #f5f8fc; }
.official-value div { display: grid; gap: 6px; }
.official-value strong { color: #244d73; font-family: var(--app-font-display); font-size: 24px; font-weight: 600; }
.form-heading { align-items: center; margin-bottom: 12px; }
.form-heading h3 { margin: 0; color: var(--app-ink); font-size: 16px; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; min-width: 0; margin: 0; padding: 0; border: 0; }
.field-grid:disabled { opacity: .68; }
.field-grid label { display: grid; gap: 6px; color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.field-grid__wide { grid-column: 1 / -1; }
.field-grid input, .field-grid select, .field-grid textarea { width: 100%; min-height: 44px; padding: 9px 11px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; font: inherit; font-weight: 500; }
.field-grid textarea { min-height: 72px; resize: vertical; }
.field-grid input:focus, .field-grid select:focus, .field-grid textarea:focus { outline: 3px solid rgba(200, 91, 67, 0.18); border-color: var(--app-accent); }
.action-row { justify-content: flex-end; margin-top: 18px; }
.solid-button { min-height: 44px; padding: 10px 16px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 13px; font-weight: 800; }
.solid-button--primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.solid-button:disabled { cursor: not-allowed; opacity: 0.55; }
.inline-notice, .inline-error { margin: 0; padding: 12px 14px; border-radius: var(--app-radius-sm); font-size: 13px; }
.inline-notice { color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.inline-error { color: #a44334; background: #fff0ed; }
.validation-counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.validation-counts span { padding: 8px 11px; border-radius: 8px; color: var(--app-ink-soft); background: #f5f7fb; font-size: 12px; font-weight: 800; }
.finding-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.finding-list li { display: grid; gap: 4px; padding: 12px 14px; border-left: 4px solid #d6a63e; background: #fffaf0; color: var(--app-ink-soft); font-size: 13px; }
.finding-list li[data-severity="ERROR"] { border-left-color: #c85b43; background: #fff3f0; }
.finding-list strong { color: var(--app-ink); font-size: 12px; }
.finding-list b { color: var(--app-ink); }
.finding-action { justify-self: start; min-height: 36px; margin-top: 5px; padding: 6px 11px; border: 1px solid rgba(200,91,67,.26); border-radius: 8px; color: var(--app-accent-deep); background: #fff; cursor: pointer; font-size: 11px; font-weight: 900; }
.correction-hints { display: grid; gap: 7px; margin-top: 14px; padding: 12px 14px; border: 1px solid rgba(214,166,62,.26); border-radius: var(--app-radius-sm); background: #fffaf0; }
.correction-hints > strong { color: var(--app-ink); font-size: 12px; }
.correction-hints ul { display: grid; gap: 4px; margin: 0; padding-left: 20px; color: var(--app-ink-soft); font-size: 12px; }
.empty-copy { margin: 0; color: var(--app-muted); font-size: 13px; }
.calculation-result, .report-result { align-items: center; margin-top: 14px; padding: 14px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.calculation-result strong, .report-result strong { margin-left: auto; color: var(--app-ink); font-size: 14px; }
.calculation-result small, .report-result small { color: var(--app-muted); font-size: 11px; }
.validation-results > .solid-button { margin-top: 18px; }

.wizard-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid #d9e4ef;
  border-radius: 12px;
  background: #f7fbff;
}
.wizard-status .workflow-guide__copy { min-width: 190px; }
.wizard-status .workflow-guide__copy h2 { font-size: 17px; }
.wizard-status .workflow-guide__stats { flex: 1 1 auto; }
.wizard-status > .finding-action { flex: 0 0 auto; margin: 0; }

.document-ai-grid {
  display: grid;
  grid-template-columns: minmax(330px, .9fr) minmax(420px, 1.1fr);
  gap: 14px;
  min-height: 460px;
}
.document-ai-grid__list { min-width: 0; }
.document-list li { border: 1px solid transparent; }
.document-list li.is-selected { border-color: rgba(46,89,132,.36); background: #eef5fc; }
.document-list__identity small { width: fit-content; margin-top: 3px; padding: 3px 7px; border-radius: 999px; color: #52657a; background: #eef1f5; font-size: 9px; font-weight: 800; }
.document-list__identity small[data-ai-state="pending"] { color: #925421; background: #fff0df; }
.finding-action--primary { border-color: rgba(46,89,132,.34); color: #244d73; background: #edf4fb; }
.document-preview { display: grid; grid-template-rows: auto minmax(340px, 1fr) auto; min-width: 0; overflow: hidden; border: 1px solid #d8e1eb; border-radius: 12px; background: #fff; }
.document-preview__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 13px; border-bottom: 1px solid #e1e7ee; background: #f8fafc; }
.document-preview__heading > div { display: grid; gap: 2px; min-width: 0; }
.document-preview__heading strong { color: var(--app-ink); font-size: 12px; }
.document-preview__heading span { overflow: hidden; color: var(--app-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.document-preview__body { display: grid; min-height: 340px; place-items: center; overflow: hidden; background: #eef1f4; }
.document-preview__body iframe { width: 100%; height: 100%; min-height: 460px; border: 0; background: #fff; }
.document-preview__body img { display: block; max-width: 100%; max-height: 520px; object-fit: contain; }
.document-preview__empty { display: grid; gap: 5px; max-width: 300px; padding: 26px; color: #6b798a; text-align: center; }
.document-preview__empty strong { color: #34495f; font-size: 13px; }
.document-preview__empty span, .document-preview__message { color: #6b798a; font-size: 11px; line-height: 1.6; }
.document-preview__message { margin: 0; padding: 24px; text-align: center; }
.document-preview__evidence { display: grid; gap: 6px; padding: 11px 13px; border-top: 1px solid #e1e7ee; background: #fff8ee; }
.document-preview__evidence strong { color: #8a531e; font-size: 10px; }
.document-preview__evidence blockquote { margin: 0; color: #3d4a58; font-size: 11px; line-height: 1.6; white-space: pre-wrap; }

.candidate-card { cursor: default; transition: border-color 120ms ease, box-shadow 120ms ease; }
.candidate-card.is-active { border-color: rgba(46,89,132,.4); box-shadow: 0 0 0 3px rgba(46,89,132,.08); }
.candidate-card__source-link { justify-self: start; padding: 0; border: 0; color: #2e5984; background: transparent; cursor: pointer; font-size: 11px; font-weight: 850; text-decoration: underline; text-underline-offset: 3px; }

.data-confirmation-nav { display: grid; gap: 14px; padding: 18px; border: 1px solid #dce5ef; border-radius: var(--app-radius-md); background: #f8fbfe; }
.data-confirmation-nav__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.data-confirmation-nav__heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; }
.data-confirmation-nav__heading > div > span { display: block; margin-top: 4px; color: var(--app-muted); font-size: 11px; line-height: 1.55; }
.data-subnav { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.data-subnav button { display: grid; min-height: 62px; gap: 4px; padding: 10px 12px; border: 1px solid #d9e2ec; border-radius: 10px; color: #4b5d70; background: #fff; cursor: pointer; text-align: left; }
.data-subnav button.is-active { border-color: #2e5984; color: #244d73; background: #edf4fb; box-shadow: inset 0 0 0 1px rgba(46,89,132,.12); }
.data-subnav strong { font-size: 11px; }
.data-subnav small { color: #718094; font-size: 9px; }
.data-overview { display: grid; gap: 8px; }
.data-overview article { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 13px 14px; border: 1px solid #dfe6ee; border-left-width: 4px; border-radius: 9px; background: #fff; }
.data-overview article[data-state="ready"] { border-left-color: #4c9275; }
.data-overview article[data-state="attention"] { border-left-color: #e09837; }
.data-overview article > div { display: grid; gap: 3px; }
.data-overview article > div:last-child { flex: 0 0 auto; grid-template-columns: auto auto; align-items: center; gap: 10px; }
.data-overview strong { color: var(--app-ink); font-size: 12px; }
.data-overview span, .data-overview small { color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.data-overview button { min-height: 34px; padding: 6px 10px; border: 1px solid #cbd8e5; border-radius: 8px; color: #244d73; background: #f5f9fd; cursor: pointer; font-size: 10px; font-weight: 900; }
.data-complete-state { display: grid; gap: 5px; color: var(--app-muted); font-size: 12px; }
.data-complete-state strong { color: var(--app-green); font-size: 14px; }

.calculation-launch { display: grid; gap: 14px; border-color: rgba(46,89,132,.24); background: #f8fbff; }
.calculation-launch__copy { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.calculation-launch__copy h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; }
.calculation-launch__copy p:last-child { max-width: 720px; margin: 7px 0 0; color: var(--app-ink-soft); font-size: 12px; line-height: 1.7; }
.calculation-launch__readiness { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.calculation-launch__readiness span { padding: 6px 9px; border-radius: 999px; font-size: 10px; font-weight: 850; }
.calculation-launch__readiness [data-state="ready"] { color: #2f745b; background: #edf8f3; }
.calculation-launch__readiness [data-state="attention"] { color: #925421; background: #fff0df; }
.calculation-launch__readiness [data-state="blocked"] { color: #9a4435; background: #fff0ed; }
.calculation-launch__button { justify-self: start; min-width: 200px; }

.wizard-footer { position: sticky; z-index: 8; bottom: 14px; display: grid; grid-template-columns: auto minmax(180px, 1fr) auto; align-items: center; gap: 14px; padding: 12px 14px; border: 1px solid rgba(190,204,220,.9); border-radius: 14px; background: rgba(255,255,255,.96); box-shadow: 0 14px 36px rgba(30,52,78,.16); backdrop-filter: blur(14px); }
.wizard-footer button { min-height: 42px; padding: 8px 14px; border-radius: 9px; cursor: pointer; font-size: 11px; font-weight: 900; }
.wizard-footer button:disabled { cursor: not-allowed; opacity: .48; }
.wizard-footer__secondary { border: 1px solid #ccd7e3; color: #465a70; background: #fff; }
.wizard-footer__primary { border: 1px solid #2e5984; color: #fff; background: #2e5984; }
.wizard-footer__status { display: grid; gap: 2px; text-align: center; }
.wizard-footer__status strong { color: var(--app-ink); font-size: 11px; }
.wizard-footer__status span { color: var(--app-muted); font-size: 9px; }

@media (max-width: 1100px) {
  .document-ai-grid { grid-template-columns: 1fr; }
  .document-preview__body iframe { min-height: 520px; }
}

@media (max-width: 760px) {
  .valuation-view { padding: 18px 16px 28px; }
  .valuation-surface { padding: 16px; }
  .case-context-strip { align-items:flex-start; flex-direction:column; }
  .case-context-strip__meta { justify-content:flex-start; }
  .surface-heading, .official-value, .calculation-result, .report-result { align-items: flex-start; flex-direction: column; }
  .revision-panel__heading, .revision-panel__items li, .revision-panel__actions { align-items: stretch; flex-direction: column; }
  .workflow-guide__copy { flex-direction: column; }
  .workflow-guide > .solid-button { width: 100%; justify-self: stretch; }
  .summary-grid, .field-grid { grid-template-columns: 1fr; }
  .upload-form { grid-template-columns: 1fr; }
  .document-list li, .supplement-panel__list li, .candidate-card__heading, .candidate-submit, .candidate-history li { align-items: stretch; flex-direction: column; }
  .document-list__actions { align-items: stretch; }
  .document-list__manage { grid-template-columns: 1fr; align-items: stretch; }
  .document-preview__heading, .data-confirmation-nav__heading, .calculation-launch__copy { align-items: stretch; flex-direction: column; }
  .data-subnav { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .data-overview article { align-items: stretch; flex-direction: column; }
  .data-overview article > div:last-child { grid-template-columns: 1fr auto; }
  .wizard-status { align-items: stretch; flex-direction: column; }
  .wizard-footer { bottom: 8px; grid-template-columns: 1fr 1fr; }
  .wizard-footer__status { grid-column: 1 / -1; grid-row: 1; }
  .candidate-workspace__summary { justify-content: flex-start; }
  .manual-fields__grid { grid-template-columns: 1fr; }
  .land-context__grid, .land-context__fields { grid-template-columns: 1fr; }
  .field-grid__wide { grid-column: auto; }
  .form-heading, .action-row { align-items: stretch; flex-direction: column; }
  .solid-button { width: 100%; }
  .calculation-result strong, .report-result strong { margin-left: 0; }
}
</style>
