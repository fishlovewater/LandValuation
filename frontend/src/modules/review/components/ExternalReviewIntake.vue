<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import {
  PhCheckCircle as CheckCircle,
  PhEye as Eye,
  PhFileArrowUp as FileArrowUp,
  PhFileText as FileText,
  PhScan as Scan,
  PhXCircle as XCircle,
} from '@phosphor-icons/vue'
import type {
  DocumentCategory,
  ExtractedFieldResponseDto,
  ExtractionResponseDto,
} from '../../valuation/valuation.types'
import {
  analysisProviderLabel,
  extractedFieldStatusLabel,
  extractionStatusLabel,
  valuationFieldLabel,
} from '../../valuation/valuation.labels'
import { userStructuredValue } from '../../../utils/fieldLabels'
import EvidenceViewer from './EvidenceViewer.vue'
import { reviewApi, safeReviewErrorMessage } from '../review.api'
import type { CorrectionRequestDto, ReviewDocumentModel } from '../review.types'

type ExternalDocumentCategory = Exclude<DocumentCategory, 'complete-valuation-report'>
type CandidateFilter = 'all' | 'pending' | 'low-confidence' | 'confirmed'

const props = withDefaults(defineProps<{
  reviewId: string
  documents: ReviewDocumentModel[]
  correctionRequest?: CorrectionRequestDto | null
  canMutate?: boolean
}>(), {
  correctionRequest: null,
  canMutate: true,
})

const emit = defineEmits<{ changed: [] }>()

const categoryOptions: Array<{ value: ExternalDocumentCategory; label: string; description: string }> = [
  { value: 'original', label: '估價報告原始文件', description: '主要 OCR 與欄位確認來源' },
  { value: 'land-register', label: '土地登記謄本', description: '完整性與宗地資料查核依據' },
  { value: 'cadastral-map', label: '地籍圖', description: '位置與宗地範圍查核依據' },
  { value: 'parcel-factor-list', label: '宗地／因素資料', description: '宗地或因素明細表' },
  { value: 'photos', label: '現況照片', description: '現場照片或補充影像' },
  { value: 'attachments', label: '其他附件', description: '其他佐證或補充文件' },
  { value: 'map-section-sketch', label: '地段略圖', description: '正式附圖資料' },
  { value: 'map-zoning', label: '使用分區圖', description: '正式附圖資料' },
  { value: 'map-land-value-section', label: '地價區段圖', description: '正式附圖資料' },
]

const documentCategory = ref<ExternalDocumentCategory>('original')
const uploadFile = ref<File | null>(null)
const correctionUploadFile = ref<File | null>(null)
const selectedDocumentId = ref('')
const selectedCandidateId = ref('')
const extraction = ref<ExtractionResponseDto | null>(null)
const candidateFilter = ref<CandidateFilter>('all')
const candidateEdits = ref<Record<string, string>>({})
const uploading = ref(false)
const uploadingCorrection = ref(false)
const registeringCorrection = ref(false)
const extracting = ref(false)
const confirmingId = ref('')
const loadingExtraction = ref(false)
const error = ref('')
const notice = ref('')

const selectedDocument = computed(() =>
  props.documents.find((document) => document.documentId === selectedDocumentId.value) ?? null,
)
const selectedCandidate = computed(() =>
  extraction.value?.candidates.find((candidate) => candidate.extracted_field_id === selectedCandidateId.value) ?? null,
)
const selectedCandidateFieldPath = computed(() => selectedCandidate.value
  ? `${selectedCandidate.value.form_code}.${selectedCandidate.value.field_name}`
  : null)

const correctionAwaitingReturn = computed(() => props.correctionRequest?.status === 'SENT')
const correctionBaseDocument = computed(() => {
  const documentId = props.correctionRequest?.base_document_id
  return documentId
    ? props.documents.find((document) => document.documentId === documentId) ?? null
    : null
})
const correctionCandidateDocument = computed(() => {
  const correction = props.correctionRequest
  const base = correctionBaseDocument.value
  if (!correction || !base?.documentGroupId) return null
  return props.documents
    .filter((document) =>
      document.documentGroupId === base.documentGroupId
      && document.versionNo > correction.base_document_version,
    )
    .slice()
    .sort((left, right) => right.versionNo - left.versionNo)[0] ?? null
})

const extractionSupported = computed(() => {
  const mime = selectedDocument.value?.mimeType.toLowerCase() ?? ''
  return [
    'application/pdf',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ].includes(mime)
})

const filteredCandidates = computed(() => {
  const rows = extraction.value?.candidates ?? []
  if (candidateFilter.value === 'pending') return rows.filter((item) => item.field_status === 'NEEDS_CONFIRMATION')
  if (candidateFilter.value === 'low-confidence') return rows.filter((item) => Number(item.confidence) < 0.75)
  if (candidateFilter.value === 'confirmed') return rows.filter((item) => ['APPLIED', 'CONFIRMED'].includes(item.field_status))
  return rows
})

const pendingCount = computed(() => extraction.value?.candidates.filter((item) => item.field_status === 'NEEDS_CONFIRMATION').length ?? 0)
const confirmedCount = computed(() => extraction.value?.candidates.filter((item) => ['APPLIED', 'CONFIRMED'].includes(item.field_status)).length ?? 0)
const correctionExtractionReady = computed(() => Boolean(
  correctionAwaitingReturn.value
    && correctionCandidateDocument.value
    && extraction.value?.document_id === correctionCandidateDocument.value.documentId
    && extraction.value.extraction_status === 'COMPLETED'
    && pendingCount.value === 0,
))
const generalOriginalUploadBlocked = computed(() => correctionAwaitingReturn.value && documentCategory.value === 'original')

function categoryLabel(value: string): string {
  return categoryOptions.find((option) => option.value === value)?.label ?? '其他附件'
}

function candidateStatusLabel(value: string): string {
  if (value === 'APPLIED') return '已納入審查'
  return extractedFieldStatusLabel(value)
}

function candidateFieldLabel(candidate: ExtractedFieldResponseDto): string {
  return candidate.field_label?.trim() || valuationFieldLabel(candidate.field_name)
}

function confidenceLabel(value: string): string {
  const number = Number(value)
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : '—'
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return userStructuredValue(value)
}

function editValue(candidate: ExtractedFieldResponseDto): string {
  return candidateEdits.value[candidate.extracted_field_id]
    ?? valueText(candidate.confirmed_value ?? candidate.extracted_value)
}

function updateEdit(candidateId: string, value: string): void {
  candidateEdits.value = { ...candidateEdits.value, [candidateId]: value }
}

function viewCandidateSource(candidate: ExtractedFieldResponseDto): void {
  selectedCandidateId.value = candidate.extracted_field_id
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  uploadFile.value = input.files?.[0] ?? null
}

function onCorrectionFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  correctionUploadFile.value = input.files?.[0] ?? null
}

function externalCategory(value: string): ExternalDocumentCategory | null {
  return categoryOptions.some((option) => option.value === value)
    ? value as ExternalDocumentCategory
    : null
}

function resetMessages(): void {
  error.value = ''
  notice.value = ''
}

async function upload(): Promise<void> {
  if (!props.canMutate || !uploadFile.value || uploading.value || generalOriginalUploadBlocked.value) return
  resetMessages()
  uploading.value = true
  try {
    const uploaded = await reviewApi.uploadExternalDocument(props.reviewId, documentCategory.value, uploadFile.value)
    selectedDocumentId.value = uploaded.document_id
    uploadFile.value = null
    extraction.value = null
    candidateEdits.value = {}
    notice.value = '文件已匯入。PDF、XLS、XLSX 可繼續執行文字擷取與欄位辨識。'
    emit('changed')
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    uploading.value = false
  }
}

async function uploadCorrectionVersion(): Promise<void> {
  const correction = props.correctionRequest
  const base = correctionBaseDocument.value
  const category = base ? externalCategory(base.documentType) : null
  if (
    !props.canMutate
    || !correctionUploadFile.value
    || uploadingCorrection.value
    || correction?.status !== 'SENT'
  ) return
  resetMessages()
  if (!base?.documentGroupId || !category) {
    error.value = '找不到原始文件的版本沿革，無法安全建立修正版。請重新整理案件後再試。'
    return
  }
  uploadingCorrection.value = true
  try {
    const uploaded = await reviewApi.uploadExternalDocument(
      props.reviewId,
      category,
      correctionUploadFile.value,
      base.documentGroupId,
    )
    selectedDocumentId.value = uploaded.document_id
    correctionUploadFile.value = null
    extraction.value = null
    candidateEdits.value = {}
    notice.value = `修正版已建立為第 ${uploaded.version_no} 版。請先執行 OCR／文字擷取並完成欄位確認，再登記為廠商回件。`
    emit('changed')
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    uploadingCorrection.value = false
  }
}

async function registerCorrectionReturn(): Promise<void> {
  const correction = props.correctionRequest
  const document = correctionCandidateDocument.value
  if (!props.canMutate || !correction || !document || !correctionExtractionReady.value || registeringCorrection.value) return
  resetMessages()
  registeringCorrection.value = true
  try {
    await reviewApi.registerCorrectionResubmission(
      correction.correction_request_id,
      document.documentId,
      document.versionNo,
    )
    notice.value = `第 ${document.versionNo} 版已登記為外部廠商回件，可執行新版重新檢核。`
    emit('changed')
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    registeringCorrection.value = false
  }
}

async function loadExtraction(documentId = selectedDocumentId.value): Promise<void> {
  if (!documentId || loadingExtraction.value) return
  loadingExtraction.value = true
  error.value = ''
  try {
    extraction.value = await reviewApi.getExternalDocumentExtraction(props.reviewId, documentId)
    candidateEdits.value = {}
  } catch (caught: unknown) {
    if (isAxiosError(caught) && caught.response?.status === 404) {
      extraction.value = null
      return
    }
    error.value = safeReviewErrorMessage(caught)
  } finally {
    loadingExtraction.value = false
  }
}

async function startExtraction(): Promise<void> {
  const document = selectedDocument.value
  if (!props.canMutate || !document || !extractionSupported.value || extracting.value) return
  resetMessages()
  extracting.value = true
  try {
    extraction.value = await reviewApi.startExternalDocumentExtraction(props.reviewId, document.documentId)
    candidateEdits.value = {}
    notice.value = extraction.value.extraction_status === 'COMPLETED'
      ? `文字擷取完成，共取得 ${extraction.value.candidates.length} 個候選欄位。`
      : '文件擷取未完成，請確認文件內容後再試。'
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    extracting.value = false
  }
}

async function decideCandidate(candidate: ExtractedFieldResponseDto, decision: 'CONFIRM' | 'REJECT'): Promise<void> {
  if (!props.canMutate || !selectedDocumentId.value || confirmingId.value) return
  resetMessages()
  confirmingId.value = candidate.extracted_field_id
  try {
    const currentValue = editValue(candidate)
    const originalValue = valueText(candidate.extracted_value)
    extraction.value = await reviewApi.confirmExternalDocumentExtraction(
      props.reviewId,
      selectedDocumentId.value,
      [{
        extracted_field_id: candidate.extracted_field_id,
        decision,
        ...(decision === 'CONFIRM' && currentValue !== originalValue ? { corrected_value: currentValue } : {}),
      }],
    )
    candidateEdits.value = {}
    notice.value = decision === 'CONFIRM' ? '欄位已確認並納入審查資料。' : '候選欄位已排除。'
    emit('changed')
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    confirmingId.value = ''
  }
}

watch(selectedDocumentId, (documentId) => {
  extraction.value = null
  selectedCandidateId.value = ''
  candidateEdits.value = {}
  resetMessages()
  if (documentId && extractionSupported.value) void loadExtraction(documentId)
})

watch(
  () => props.documents.map((document) => `${document.documentId}:${document.versionNo}`).join('|'),
  () => {
    if (selectedDocumentId.value && props.documents.some((item) => item.documentId === selectedDocumentId.value)) return
    const original = [...props.documents]
      .filter((item) => item.documentType === 'original')
      .sort((left, right) => right.versionNo - left.versionNo)[0]
    selectedDocumentId.value = original?.documentId ?? props.documents[0]?.documentId ?? ''
  },
  { immediate: true },
)
</script>

<template>
  <section class="external-intake" data-testid="external-review-intake" aria-labelledby="external-intake-title">
    <header class="external-intake__heading">
      <div>
        <span>外部案件資料準備</span>
        <h2 id="external-intake-title">文件匯入與欄位確認</h2>
        <p>先匯入外部廠商提供的文件。擷取出的候選欄位必須由審查人員核對來源後確認，才會成為正式審查依據。</p>
      </div>
      <div class="external-intake__summary">
        <span><b>{{ documents.length }}</b> 份文件</span>
        <span v-if="extraction"><b>{{ pendingCount }}</b> 欄待確認</span>
        <span v-if="extraction"><b>{{ confirmedCount }}</b> 欄已確認</span>
      </div>
    </header>
    <p v-if="!canMutate" class="external-intake__readonly" data-testid="external-intake-readonly">
      目前審查狀態已鎖定來源資料；文件與擷取結果仍可查閱，但不可新增、重新辨識或變更確認欄位。
    </p>

    <section
      v-if="correctionRequest && ['SENT', 'RESUBMITTED', 'RECHECKING', 'RECHECKED'].includes(correctionRequest.status)"
      class="external-intake__correction-return"
      data-testid="external-correction-return"
      aria-labelledby="external-correction-return-title"
    >
      <div class="external-intake__correction-heading">
        <div>
          <span>外部修正版回件</span>
          <strong id="external-correction-return-title">第 {{ correctionRequest.request_no }} 次修正通知</strong>
          <p v-if="correctionRequest.status === 'SENT'">請把廠商回傳的修正版建立成原文件的下一個版本。完成 OCR 與欄位確認後，才登記為正式回件。</p>
          <p v-else-if="correctionRequest.status === 'RESUBMITTED'">新版已登記為正式回件，接下來可執行新版完整性與規則重檢。</p>
          <p v-else-if="correctionRequest.status === 'RECHECKING'">系統正在重新檢核修正版。</p>
          <p v-else>本次修正版已完成重新檢核。</p>
        </div>
        <b :data-status="correctionRequest.status">
          {{ correctionRequest.status === 'SENT' ? '等待回件' : correctionRequest.status === 'RESUBMITTED' ? '已登記回件' : correctionRequest.status === 'RECHECKING' ? '重新檢核中' : '已重新檢核' }}
        </b>
      </div>

      <template v-if="correctionRequest.status === 'SENT'">
        <div class="external-intake__version-lineage">
          <div>
            <span>原審查版本</span>
            <strong>{{ correctionBaseDocument?.filename ?? '找不到原始文件' }}</strong>
            <small>第 {{ correctionRequest.base_document_version }} 版</small>
          </div>
          <span aria-hidden="true">→</span>
          <div>
            <span>待登記修正版</span>
            <strong>{{ correctionCandidateDocument?.filename ?? '尚未上傳' }}</strong>
            <small>{{ correctionCandidateDocument ? `第 ${correctionCandidateDocument.versionNo} 版` : '需沿用同一文件版本群組' }}</small>
          </div>
        </div>

        <div v-if="!correctionCandidateDocument" class="external-intake__correction-upload">
          <label>
            <span>廠商回傳修正版</span>
            <input type="file" data-testid="external-correction-file" accept=".pdf,.xls,.xlsx" :disabled="!canMutate" @change="onCorrectionFileChange">
            <small>系統會建立同一份原始文件的下一版本，不會另開一份無關文件。</small>
          </label>
          <button
            type="button"
            data-testid="upload-external-correction-version"
            :disabled="!canMutate || !correctionUploadFile || uploadingCorrection || !correctionBaseDocument?.documentGroupId"
            @click="uploadCorrectionVersion"
          >
            <FileArrowUp :size="17" weight="bold" aria-hidden="true" />
            {{ uploadingCorrection ? '建立版本中…' : '匯入為下一版本' }}
          </button>
        </div>

        <div v-else class="external-intake__correction-next">
          <p v-if="extraction?.document_id !== correctionCandidateDocument.documentId">
            修正版已建立。請在下方選取第 {{ correctionCandidateDocument.versionNo }} 版並執行 OCR／文字擷取。
          </p>
          <p v-else-if="extraction.extraction_status !== 'COMPLETED'">
            修正版文字擷取尚未完成，請先完成 OCR／文字擷取。
          </p>
          <p v-else-if="pendingCount > 0">
            修正版還有 {{ pendingCount }} 個候選欄位待人工確認，全部處理後才能正式登記回件。
          </p>
          <p v-else>
            修正版欄位已完成確認，可將第 {{ correctionCandidateDocument.versionNo }} 版正式登記為本次廠商回件。
          </p>
          <button
            type="button"
            data-testid="register-external-resubmission"
            :disabled="!canMutate || !correctionExtractionReady || registeringCorrection"
            @click="registerCorrectionReturn"
          >
            <CheckCircle :size="17" weight="bold" aria-hidden="true" />
            {{ registeringCorrection ? '登記中…' : '確認此版為廠商回件' }}
          </button>
        </div>
      </template>

      <div v-else class="external-intake__correction-registered">
        <CheckCircle :size="20" weight="fill" aria-hidden="true" />
        <span>
          <strong>第 {{ correctionRequest.response_document_version ?? '—' }} 版已登記</strong>
          <small>回件版本已固定，重新檢核會使用目前已確認的新版欄位資料。</small>
        </span>
      </div>
    </section>

    <div class="external-intake__upload" data-testid="external-document-upload">
      <label>
        <span>文件類型</span>
        <select v-model="documentCategory" data-testid="external-document-category" :disabled="!canMutate">
          <option v-for="option in categoryOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <label>
        <span>選擇來源文件</span>
        <input type="file" data-testid="external-document-file" accept=".pdf,.xls,.xlsx,.png,.jpg,.jpeg" :disabled="!canMutate" @change="onFileChange">
        <small>{{ categoryOptions.find((option) => option.value === documentCategory)?.description }}</small>
      </label>
      <button type="button" data-testid="upload-external-document" :disabled="!canMutate || !uploadFile || uploading || generalOriginalUploadBlocked" @click="upload">
        <FileArrowUp :size="17" weight="bold" aria-hidden="true" />
        {{ uploading ? '匯入中…' : '匯入文件' }}
      </button>
    </div>
    <p v-if="generalOriginalUploadBlocked" class="external-intake__hint">
      目前正在等待外部修正版；「估價報告原始文件」請使用上方的修正版回件區建立下一版本。其他附件仍可正常新增。
    </p>

    <p v-if="error" class="external-intake__error" role="alert">{{ error }}</p>
    <p v-if="notice" class="external-intake__notice" role="status">{{ notice }}</p>

    <div class="external-intake__body">
      <aside class="external-intake__documents" aria-label="已匯入文件">
        <div class="external-intake__subheading"><strong>已匯入文件</strong><small>{{ documents.length }} 份</small></div>
        <div v-if="documents.length" class="external-intake__document-list">
          <button
            v-for="document in documents"
            :key="document.documentId"
            type="button"
            :class="{ 'is-selected': document.documentId === selectedDocumentId }"
            :data-testid="`external-document-${document.documentId}`"
            @click="selectedDocumentId = document.documentId"
          >
            <FileText :size="18" aria-hidden="true" />
            <span><strong>{{ document.filename }}</strong><small>{{ categoryLabel(document.documentType) }} · 第 {{ document.versionNo }} 版 · {{ document.isActive ? '目前版本' : '歷史版本' }}</small></span>
          </button>
        </div>
        <div v-else class="external-intake__empty">
          <FileArrowUp :size="24" aria-hidden="true" />
          <strong>尚未匯入來源文件</strong>
          <p>至少先匯入「估價報告原始文件」，再進行 OCR／欄位確認。</p>
        </div>
      </aside>

      <main class="external-intake__workspace">
        <div v-if="selectedDocument" class="external-intake__selected-document">
          <div>
            <span>{{ categoryLabel(selectedDocument.documentType) }}</span>
            <strong>{{ selectedDocument.filename }}</strong>
            <small>{{ selectedDocument.mimeTypeLabel }} · 第 {{ selectedDocument.versionNo }} 版</small>
          </div>
          <button v-if="extractionSupported" type="button" data-testid="start-external-extraction" :disabled="!canMutate || extracting || loadingExtraction" @click="startExtraction">
            <Scan :size="17" weight="bold" aria-hidden="true" />
            {{ extracting ? '辨識中…' : extraction ? '重新執行文字擷取' : '執行 OCR／文字擷取' }}
          </button>
          <span v-else class="external-intake__unsupported">此格式保留作為附件，不執行欄位擷取</span>
        </div>

        <div v-if="loadingExtraction" class="external-intake__loading">正在讀取既有擷取結果…</div>
        <template v-else-if="extraction">
          <div class="external-intake__extraction-summary">
            <div><span>擷取方式</span><strong>{{ analysisProviderLabel(extraction.provider) }}</strong></div>
            <div><span>處理狀態</span><strong>{{ extractionStatusLabel(extraction.extraction_status) }}</strong></div>
            <div><span>頁數</span><strong>{{ extraction.page_count ?? '—' }}</strong></div>
          </div>
          <div v-if="extraction.error_message" class="external-intake__extraction-error">文件辨識未完成，請確認檔案內容後重試。</div>

          <template v-if="extraction.extraction_status === 'COMPLETED'">
            <div class="external-intake__candidate-toolbar">
              <div><strong>欄位候選值</strong><small>請核對來源頁面與原文後再確認。</small></div>
              <div class="external-intake__filters" aria-label="欄位候選篩選">
                <button type="button" :class="{ 'is-active': candidateFilter === 'all' }" @click="candidateFilter = 'all'">全部</button>
                <button type="button" :class="{ 'is-active': candidateFilter === 'pending' }" @click="candidateFilter = 'pending'">待確認 {{ pendingCount }}</button>
                <button type="button" :class="{ 'is-active': candidateFilter === 'low-confidence' }" @click="candidateFilter = 'low-confidence'">低信心</button>
                <button type="button" :class="{ 'is-active': candidateFilter === 'confirmed' }" @click="candidateFilter = 'confirmed'">已確認 {{ confirmedCount }}</button>
              </div>
            </div>

            <div v-if="filteredCandidates.length" class="external-intake__candidate-review">
              <section
                class="external-intake__source-pane"
                data-testid="external-candidate-source-preview"
                aria-label="候選欄位來源文件"
              >
                <div v-if="selectedCandidate" class="external-intake__source-location">
                  <span>來源定位</span>
                  <strong>{{ selectedCandidate.source_page ? `第 ${selectedCandidate.source_page} 頁` : '頁碼未辨識' }}</strong>
                  <small>{{ candidateFieldLabel(selectedCandidate) }}</small>
                </div>
                <EvidenceViewer
                  v-if="selectedCandidate && selectedDocument"
                  :review-id="reviewId"
                  :document="selectedDocument"
                  :page-number="selectedCandidate.source_page"
                  :field-path="selectedCandidateFieldPath"
                />
                <div v-else class="external-intake__source-empty">
                  <Eye :size="26" aria-hidden="true" />
                  <strong>選取欄位查看來源</strong>
                  <p>按「查看來源」後，系統會開啟該欄位實際引用的文件與頁碼，避免只看擷取文字就直接確認。</p>
                </div>
              </section>
              <div class="external-intake__table-wrap">
                <table class="external-intake__table">
                  <thead><tr><th>欄位</th><th>擷取結果</th><th>來源</th><th>狀態</th><th>操作</th></tr></thead>
                  <tbody>
                    <tr
                      v-for="candidate in filteredCandidates"
                      :key="candidate.extracted_field_id"
                      :class="{ 'is-source-selected': candidate.extracted_field_id === selectedCandidateId }"
                    >
                      <td><strong>{{ candidateFieldLabel(candidate) }}</strong><small>{{ candidate.form_code }} · 信心 {{ confidenceLabel(candidate.confidence) }}</small></td>
                      <td>
                        <input
                          :value="editValue(candidate)"
                          :disabled="!canMutate || candidate.field_status === 'REJECTED' || confirmingId === candidate.extracted_field_id"
                          :aria-label="`${candidateFieldLabel(candidate)}確認值`"
                          @input="updateEdit(candidate.extracted_field_id, ($event.target as HTMLInputElement).value)"
                        >
                      </td>
                      <td><span>{{ candidate.source_page ? `第 ${candidate.source_page} 頁` : '頁碼未辨識' }}</span><small :title="candidate.source_text || ''">{{ candidate.source_text || '沒有擷取到來源片段' }}</small></td>
                      <td><span class="external-intake__status" :data-status="candidate.field_status">{{ candidateStatusLabel(candidate.field_status) }}</span></td>
                      <td>
                        <div class="external-intake__row-actions">
                          <button type="button" class="is-source" :data-testid="`view-external-field-source-${candidate.extracted_field_id}`" @click="viewCandidateSource(candidate)"><Eye :size="16" aria-hidden="true" />查看來源</button>
                          <button type="button" :data-testid="`confirm-external-field-${candidate.extracted_field_id}`" :disabled="!canMutate || confirmingId === candidate.extracted_field_id" @click="decideCandidate(candidate, 'CONFIRM')"><CheckCircle :size="16" weight="bold" aria-hidden="true" />確認</button>
                          <button type="button" class="is-reject" :data-testid="`reject-external-field-${candidate.extracted_field_id}`" :disabled="!canMutate || confirmingId === candidate.extracted_field_id" @click="decideCandidate(candidate, 'REJECT')"><XCircle :size="16" aria-hidden="true" />排除</button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div v-else class="external-intake__empty external-intake__empty--compact">
              <strong>{{ extraction.candidates.length ? '目前篩選條件沒有欄位' : '沒有找到可自動辨識的欄位' }}</strong>
              <p>文件仍會保留作為證據；開始審查時，完整性檢核會列出仍缺少的必要資料。</p>
            </div>
          </template>
        </template>

        <div v-else-if="selectedDocument && extractionSupported" class="external-intake__empty external-intake__empty--workspace">
          <Scan :size="28" aria-hidden="true" /><strong>尚未執行文字擷取</strong><p>執行後會列出候選欄位、辨識信心、來源頁面與原文。</p>
        </div>
        <div v-else-if="!selectedDocument" class="external-intake__empty external-intake__empty--workspace"><strong>請先匯入或選擇文件</strong></div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.external-intake{display:grid;gap:16px;margin-top:16px;padding:18px;border:1px solid var(--app-line);border-radius:12px;background:#fff}
.external-intake__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.external-intake__heading>div:first-child{display:grid;max-width:760px;gap:4px}.external-intake__heading span{color:var(--app-muted);font-size:10px;font-weight:850}.external-intake__heading h2{margin:0;color:var(--app-ink);font-size:18px}.external-intake__heading p{margin:2px 0 0;color:var(--app-muted);font-size:11px;line-height:1.65}.external-intake__summary{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.external-intake__summary span{padding:6px 9px;border-radius:999px;color:var(--app-ink-soft);background:#f4f6f8}.external-intake__summary b{color:var(--app-ink)}
.external-intake__readonly{margin:0;padding:9px 11px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-muted);background:#f5f7f9;font-size:10px;line-height:1.55}
.external-intake__correction-return{display:grid;gap:12px;padding:14px;border:1px solid rgba(204,145,44,.3);border-radius:10px;background:#fffaf0}.external-intake__correction-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.external-intake__correction-heading>div{display:grid;gap:3px}.external-intake__correction-heading span{color:#8a6417;font-size:9px;font-weight:900;letter-spacing:.1em}.external-intake__correction-heading strong{color:var(--app-ink);font-size:13px}.external-intake__correction-heading p{max-width:720px;margin:2px 0 0;color:var(--app-ink-soft);font-size:10px;line-height:1.6}.external-intake__correction-heading>b{flex:0 0 auto;padding:5px 8px;border-radius:999px;color:#7a5a15;background:#fff0c7;font-size:9px;white-space:nowrap}.external-intake__correction-heading>b[data-status="RESUBMITTED"],.external-intake__correction-heading>b[data-status="RECHECKED"]{color:#356148;background:#eaf6ee}.external-intake__correction-heading>b[data-status="RECHECKING"]{color:#2e5984;background:#edf4fb}.external-intake__version-lineage{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:10px}.external-intake__version-lineage>div{display:grid;gap:3px;padding:10px 12px;border:1px solid rgba(204,145,44,.18);border-radius:8px;background:rgba(255,255,255,.82)}.external-intake__version-lineage>div>span{color:var(--app-muted);font-size:8.5px;font-weight:800}.external-intake__version-lineage>div>strong{overflow:hidden;color:var(--app-ink);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.external-intake__version-lineage>div>small{color:var(--app-muted);font-size:8.5px}.external-intake__version-lineage>span{color:#9a6c19;font-size:18px;font-weight:900}.external-intake__correction-upload{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px}.external-intake__correction-upload label{display:grid;gap:5px}.external-intake__correction-upload label>span{color:var(--app-ink-soft);font-size:10px;font-weight:850}.external-intake__correction-upload input{min-height:40px;width:100%;padding:7px 9px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-ink);background:#fff;font:inherit;font-size:11px}.external-intake__correction-upload small{color:var(--app-muted);font-size:9px}.external-intake__correction-upload button,.external-intake__correction-next button{display:inline-flex;min-height:40px;align-items:center;justify-content:center;gap:6px;padding:8px 12px;border:1px solid var(--app-accent);border-radius:8px;color:#fff;background:var(--app-accent);cursor:pointer;font-size:10px;font-weight:850;white-space:nowrap}.external-intake__correction-upload button:disabled,.external-intake__correction-next button:disabled{cursor:not-allowed;opacity:.5}.external-intake__correction-next{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid rgba(204,145,44,.18);border-radius:8px;background:rgba(255,255,255,.72)}.external-intake__correction-next p{margin:0;color:var(--app-ink-soft);font-size:10px;line-height:1.55}.external-intake__correction-registered{display:flex;align-items:center;gap:9px;padding:10px 12px;border-radius:8px;color:#356148;background:#eef8f1}.external-intake__correction-registered>span{display:grid;gap:2px}.external-intake__correction-registered strong{font-size:10px}.external-intake__correction-registered small{color:#547463;font-size:9px}.external-intake__hint{margin:-8px 0 0;color:#87651f;font-size:9px;line-height:1.5}
.external-intake__upload{display:grid;grid-template-columns:minmax(180px,.7fr) minmax(260px,1.4fr) auto;align-items:end;gap:10px;padding:12px;border:1px solid var(--app-line);border-radius:10px;background:#f8fafc}.external-intake__upload label{display:grid;min-width:0;gap:5px}.external-intake__upload label>span{color:var(--app-muted);font-size:10px;font-weight:800}.external-intake__upload select,.external-intake__upload input{min-height:40px;width:100%;padding:7px 9px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-ink);background:#fff;font:inherit;font-size:11px}.external-intake__upload small{color:var(--app-muted);font-size:9px}.external-intake__upload>button,.external-intake__selected-document>button{display:inline-flex;min-height:40px;align-items:center;justify-content:center;gap:6px;padding:8px 12px;border:1px solid var(--app-accent);border-radius:8px;color:#fff;background:var(--app-accent);cursor:pointer;font-size:11px;font-weight:850;white-space:nowrap}.external-intake__upload>button:disabled,.external-intake__selected-document>button:disabled{cursor:not-allowed;opacity:.55}
.external-intake__error,.external-intake__notice{margin:-4px 0 0;padding:9px 11px;border-radius:8px;font-size:11px}.external-intake__error{color:#a53934;background:#fff0ef}.external-intake__notice{color:#356148;background:#eef8f1}.external-intake__body{display:grid;grid-template-columns:minmax(230px,290px) minmax(0,1fr);gap:14px;min-height:330px}.external-intake__documents{min-width:0;padding-right:14px;border-right:1px solid var(--app-line)}.external-intake__subheading{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.external-intake__subheading strong{color:var(--app-ink);font-size:12px}.external-intake__subheading small{color:var(--app-muted);font-size:9px}.external-intake__document-list{display:grid;gap:5px}.external-intake__document-list button{display:grid;grid-template-columns:20px minmax(0,1fr);align-items:start;gap:8px;width:100%;padding:9px;border:1px solid transparent;border-radius:8px;color:var(--app-muted);background:transparent;cursor:pointer;text-align:left}.external-intake__document-list button:hover{background:#f7f9fb}.external-intake__document-list button.is-selected{border-color:color-mix(in srgb,var(--app-accent) 24%,var(--app-line));color:var(--app-accent-deep);background:var(--app-accent-soft)}.external-intake__document-list button span{display:grid;min-width:0;gap:3px}.external-intake__document-list strong{overflow:hidden;color:var(--app-ink-soft);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.external-intake__document-list small{color:var(--app-muted);font-size:8.5px}
.external-intake__workspace{min-width:0}.external-intake__selected-document{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-bottom:12px;border-bottom:1px solid var(--app-line)}.external-intake__selected-document>div{display:grid;min-width:0;gap:3px}.external-intake__selected-document>div span{color:var(--app-accent-deep);font-size:9px;font-weight:850}.external-intake__selected-document>div strong{overflow:hidden;color:var(--app-ink);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.external-intake__selected-document>div small,.external-intake__unsupported{color:var(--app-muted);font-size:9px}.external-intake__loading{padding:30px 8px;color:var(--app-muted);font-size:11px;text-align:center}.external-intake__extraction-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:12px 0}.external-intake__extraction-summary>div{display:grid;gap:3px;padding:9px 10px;border-radius:8px;background:#f7f9fb}.external-intake__extraction-summary span{color:var(--app-muted);font-size:8.5px}.external-intake__extraction-summary strong{color:var(--app-ink-soft);font-size:11px}.external-intake__extraction-error{margin-bottom:10px;padding:10px;border-radius:8px;color:#a53934;background:#fff0ef;font-size:10px}
.external-intake__candidate-toolbar{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;padding:5px 0 9px}.external-intake__candidate-toolbar>div:first-child{display:grid;gap:2px}.external-intake__candidate-toolbar strong{color:var(--app-ink);font-size:12px}.external-intake__candidate-toolbar small{color:var(--app-muted);font-size:9px}.external-intake__filters{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:4px}.external-intake__filters button{min-height:29px;padding:5px 8px;border:1px solid transparent;border-radius:999px;color:var(--app-muted);background:#f3f5f7;cursor:pointer;font-size:9px;font-weight:800}.external-intake__filters button.is-active{border-color:color-mix(in srgb,var(--app-accent) 25%,transparent);color:var(--app-accent-deep);background:var(--app-accent-soft)}.external-intake__table-wrap{overflow-x:auto;border:1px solid var(--app-line);border-radius:9px}.external-intake__table{width:100%;border-collapse:collapse;min-width:760px}.external-intake__table th{padding:8px 9px;border-bottom:1px solid var(--app-line);color:var(--app-muted);background:#f8fafc;font-size:8.5px;font-weight:850;text-align:left}.external-intake__table td{padding:9px;border-bottom:1px solid #edf0f3;vertical-align:top}.external-intake__table tbody tr:last-child td{border-bottom:0}.external-intake__table td:first-child{display:grid;gap:3px;min-width:150px}.external-intake__table td:first-child strong{color:var(--app-ink);font-size:10px}.external-intake__table td:first-child small{color:var(--app-muted);font-size:8px}.external-intake__table td:nth-child(2) input{min-height:34px;width:100%;min-width:150px;padding:6px 8px;border:1px solid var(--app-line);border-radius:6px;color:var(--app-ink);background:#fff;font:inherit;font-size:10px}.external-intake__table td:nth-child(3){max-width:260px}.external-intake__table td:nth-child(3)>span{display:block;color:var(--app-ink-soft);font-size:9px;font-weight:800}.external-intake__table td:nth-child(3)>small{display:-webkit-box;overflow:hidden;margin-top:3px;color:var(--app-muted);font-size:8px;line-height:1.45;-webkit-box-orient:vertical;-webkit-line-clamp:2}.external-intake__status{display:inline-flex;padding:4px 6px;border-radius:999px;color:#7e601d;background:#fff3d8;font-size:8px;font-weight:850;white-space:nowrap}.external-intake__status[data-status="APPLIED"],.external-intake__status[data-status="CONFIRMED"]{color:#356148;background:#eaf6ee}.external-intake__status[data-status="REJECTED"]{color:#6d7075;background:#eff1f3}.external-intake__row-actions{display:flex;flex-wrap:wrap;gap:4px;min-width:130px}.external-intake__row-actions button{display:inline-flex;min-height:31px;align-items:center;gap:4px;padding:5px 7px;border:1px solid #b9d7c4;border-radius:6px;color:#356148;background:#f2faf5;cursor:pointer;font-size:8.5px;font-weight:850}.external-intake__row-actions button.is-reject{border-color:var(--app-line);color:var(--app-muted);background:#fff}.external-intake__row-actions button:disabled{cursor:not-allowed;opacity:.5}.external-intake__empty{display:grid;justify-items:center;gap:5px;padding:28px 12px;color:var(--app-muted);text-align:center}.external-intake__empty strong{color:var(--app-ink-soft);font-size:11px}.external-intake__empty p{max-width:340px;margin:0;font-size:9px;line-height:1.55}.external-intake__empty--workspace{min-height:220px;align-content:center}.external-intake__empty--compact{padding:24px 12px;border:1px dashed var(--app-line);border-radius:8px}
.external-intake__candidate-review{display:grid;grid-template-columns:minmax(300px,.9fr) minmax(0,1.35fr);align-items:start;gap:12px}.external-intake__source-pane{position:sticky;top:76px;min-width:0}.external-intake__source-pane :deep(.evidence-viewer){padding:14px;box-shadow:none}.external-intake__source-pane :deep(.evidence-viewer h2){font-size:17px}.external-intake__source-pane :deep(.evidence-viewer__surface){min-height:430px}.external-intake__source-pane :deep(.evidence-viewer__pdf){min-height:380px}.external-intake__source-empty{display:grid;min-height:430px;align-content:center;justify-items:center;gap:7px;padding:24px;border:1px dashed var(--app-line);border-radius:10px;color:var(--app-muted);background:#fafbfc;text-align:center}.external-intake__source-empty strong{color:var(--app-ink-soft);font-size:11px}.external-intake__source-empty p{max-width:300px;margin:0;font-size:9px;line-height:1.6}.external-intake__table tr.is-source-selected td{background:#f6f9fc}.external-intake__row-actions button.is-source{border-color:#c6d7e8;color:var(--app-accent-deep);background:#f4f8fc}
.external-intake__source-location{display:flex;align-items:center;gap:7px;margin-bottom:7px;padding:8px 10px;border:1px solid #d7e2ed;border-radius:8px;background:#f6f9fc}.external-intake__source-location span,.external-intake__source-location small{color:var(--app-muted);font-size:9px}.external-intake__source-location strong{color:var(--app-accent-deep);font-size:10px}.external-intake__source-location small{margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:1180px){.external-intake__candidate-review{grid-template-columns:1fr}.external-intake__source-pane{position:static}.external-intake__source-pane :deep(.evidence-viewer__surface),.external-intake__source-empty{min-height:360px}.external-intake__source-pane :deep(.evidence-viewer__pdf){min-height:310px}}
@media(max-width:920px){.external-intake__upload{grid-template-columns:1fr 1fr}.external-intake__upload>button{grid-column:1/-1}.external-intake__body{grid-template-columns:1fr}.external-intake__documents{padding-right:0;padding-bottom:12px;border-right:0;border-bottom:1px solid var(--app-line)}.external-intake__document-list{grid-template-columns:repeat(2,minmax(0,1fr))}.external-intake__correction-upload{grid-template-columns:1fr}.external-intake__correction-upload button{width:100%}}
@media(max-width:620px){.external-intake{padding:14px}.external-intake__heading,.external-intake__selected-document,.external-intake__candidate-toolbar,.external-intake__correction-heading,.external-intake__correction-next{align-items:stretch;flex-direction:column}.external-intake__summary,.external-intake__filters{justify-content:flex-start}.external-intake__upload,.external-intake__extraction-summary,.external-intake__document-list,.external-intake__version-lineage{grid-template-columns:1fr}.external-intake__version-lineage>span{justify-self:center;transform:rotate(90deg)}.external-intake__correction-next button{width:100%}}
</style>
