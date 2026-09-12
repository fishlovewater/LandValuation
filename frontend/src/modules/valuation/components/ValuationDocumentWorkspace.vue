<script setup lang="ts">
import { computed, nextTick } from 'vue'
import {
  PhArrowClockwise as ArrowClockwise,
  PhCheckCircle as CheckCircle,
  PhDownloadSimple as DownloadSimple,
  PhEye as Eye,
  PhFile as FileIcon,
  PhFileSearch as FileSearch,
  PhMagicWand as MagicWand,
  PhTag as Tag,
  PhTrash as Trash,
  PhUploadSimple as UploadSimple,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import DocumentTextPreview from '../../../components/common/DocumentTextPreview.vue'
import SpreadsheetPreview from '../../../components/common/SpreadsheetPreview.vue'
import type { DocumentTextPreviewDto } from '../../../types/documentPreview'
import type { SpreadsheetPreviewDto } from '../../../types/spreadsheet'
import type {
  DocumentArtifactModel,
  DocumentCategory,
  ExtractedFieldResponseDto,
} from '../valuation.types'

type FieldAnalysisFormCode = 'S01' | 'F01' | 'F02' | 'F02-RF' | 'F03' | 'F04'

const startupDocuments: ReadonlyArray<{
  category: DocumentCategory
  label: string
  detail: string
  requirement: 'recommended' | 'required'
}> = [
  {
    category: 'parcel-factor-list',
    label: '宗地個別因素清冊',
    detail: '案件啟動建議資料；可上傳既有 XLS／XLSX，協助辨識宗地與個別因素欄位。',
    requirement: 'recommended',
  },
  {
    category: 'cadastral-map',
    label: '預定徵收範圍地籍圖',
    detail: '核對宗地位置與徵收範圍；目前比準地地價估計表的必要來源之一。',
    requirement: 'required',
  },
  {
    category: 'land-register',
    label: '土地登記資料',
    detail: '核對地號、面積等土地基本資料；目前比準地地價估計表的必要來源之一。',
    requirement: 'required',
  },
]

const props = defineProps<{
  documents: DocumentArtifactModel[]
  previewDocumentId: string | null
  previewDocument: DocumentArtifactModel | null
  previewPage: number | null
  previewLoading: boolean
  previewError: string
  previewSourceUrl: string
  previewIsPdf: boolean
  previewIsImage: boolean
  previewIsSpreadsheet: boolean
  previewIsDocx: boolean
  spreadsheetPreview: SpreadsheetPreviewDto | null
  textPreview: DocumentTextPreviewDto | null
  selectedCandidate: ExtractedFieldResponseDto | null
  canUpload: boolean
  uploading: boolean
  uploadFile: File | null
  uploadCategory: DocumentCategory
  extractionBusyDocumentId: string | null
  documentActionId: string | null
  documentCategoryDraft: Record<string, DocumentCategory>
  documentAnalysisForm: Record<string, FieldAnalysisFormCode>
  analysisFormCodes: readonly FieldAnalysisFormCode[]
  sourceCategories: readonly DocumentCategory[]
  formDisplayName: (code: string) => string
  documentCategoryLabel: (category: string) => string
  formatFileSize: (bytes: number) => string
  documentPendingCount: (documentId: string) => number
  documentCandidateCount: (documentId: string) => number
  documentAiStatus: (documentId: string) => string
  canExtractDocument: (document: DocumentArtifactModel) => boolean
  canManageSourceDocument: (document: DocumentArtifactModel) => boolean
}>()

const emit = defineEmits<{
  preview: [documentId: string]
  prepareParcelImport: [documentId: string]
  extract: [documentId: string]
  reviewCandidates: []
  continueData: []
  reclassify: [documentId: string]
  remove: [documentId: string, filename: string]
  download: [document: DocumentArtifactModel]
  updateAnalysisForm: [documentId: string, formCode: FieldAnalysisFormCode]
  updateCategory: [documentId: string, category: DocumentCategory]
  updateUploadCategory: [category: DocumentCategory]
  chooseUpload: [event: Event | File]
  upload: []
}>()

function categoryValue(documentId: string): DocumentCategory {
  return props.documentCategoryDraft[documentId] ?? 'original'
}

function hasActiveCategory(category: DocumentCategory): boolean {
  return props.documents.some((document) => document.isActive && document.documentType === category)
}

const requiredDocumentCount = computed(() => startupDocuments.filter((item) => item.requirement === 'required').length)
const uploadedRequiredDocumentCount = computed(() => startupDocuments.filter(
  (item) => item.requirement === 'required' && hasActiveCategory(item.category),
).length)
const missingRequiredDocuments = computed(() => startupDocuments.filter(
  (item) => item.requirement === 'required' && !hasActiveCategory(item.category),
))
const pendingRecognitionCount = computed(() => props.documents.reduce(
  (total, document) => total + props.documentPendingCount(document.documentId),
  0,
))
const documentsWaitingForRecognition = computed(() => props.documents.filter(
  (document) => document.isActive
    && props.canExtractDocument(document)
    && props.documentAiStatus(document.documentId) === '尚未辨識',
))
const sourceReady = computed(() => (
  missingRequiredDocuments.value.length === 0
  && documentsWaitingForRecognition.value.length === 0
  && pendingRecognitionCount.value === 0
))

const activeDocumentCount = computed(() => props.documents.filter((document) => document.isActive).length)
const currentTaskTitle = computed(() => {
  const missing = missingRequiredDocuments.value[0]
  if (missing) return `還缺少「${missing.label}」`
  if (documentsWaitingForRecognition.value.length) return `還有 ${documentsWaitingForRecognition.value.length} 份文件尚未辨識`
  if (pendingRecognitionCount.value) return `還有 ${pendingRecognitionCount.value} 項辨識結果需要確認`
  return '來源資料已整理完成'
})
const currentTaskDetail = computed(() => {
  if (missingRequiredDocuments.value.length) return '先補齊必要來源，再進行後續辨識與估價。'
  if (documentsWaitingForRecognition.value.length) return '可直接執行下一份文件辨識。'
  if (pendingRecognitionCount.value) return '核對 AI 擷取值後再套用到正式資料。'
  return '必要來源、文件辨識與人工確認都已完成。'
})

async function focusUpload(category?: DocumentCategory): Promise<void> {
  if (category) emit('updateUploadCategory', category)
  await nextTick()
  const panel = document.getElementById('valuation-upload-panel')
  panel?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  panel?.querySelector<HTMLElement>('select, input, button')?.focus()
}

async function runNextSourceAction(): Promise<void> {
  const missing = missingRequiredDocuments.value[0]
  if (missing) {
    await focusUpload(missing.category)
    return
  }
  const pendingDocument = documentsWaitingForRecognition.value[0]
  if (pendingDocument) {
    emit('extract', pendingDocument.documentId)
    return
  }
  if (pendingRecognitionCount.value) {
    emit('reviewCandidates')
    return
  }
  emit('continueData')
}

function sourceNextActionLabel(): string {
  const missing = missingRequiredDocuments.value[0]
  if (missing) return `上傳${missing.label}`
  if (documentsWaitingForRecognition.value.length) return `辨識下一份文件（${documentsWaitingForRecognition.value.length}）`
  if (pendingRecognitionCount.value) return `確認辨識結果（${pendingRecognitionCount.value}）`
  return '下一步：估價資料'
}

function handleDrop(event: DragEvent): void {
  const file = event.dataTransfer?.files?.[0]
  if (file) emit('chooseUpload', file)
}

function canPrepareParcelImport(document: DocumentArtifactModel): boolean {
  return document.documentType === 'parcel-factor-list'
    && [
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ].includes(document.mimeType.toLowerCase())
}
</script>

<template>
  <div id="valuation-document-workspace" class="document-workspace" tabindex="-1">
    <section class="source-summary" data-testid="source-data-flow" aria-labelledby="source-data-flow-title">
      <div class="source-summary__main">
        <div class="source-summary__title">
          <span>來源資料</span>
          <strong id="source-data-flow-title">{{ currentTaskTitle }}</strong>
        </div>
        <div class="source-summary__metrics" aria-label="來源資料狀態">
          <span :data-state="missingRequiredDocuments.length ? 'attention' : 'ready'">必要 <b>{{ uploadedRequiredDocumentCount }} / {{ requiredDocumentCount }}</b></span>
          <span>文件 <b>{{ activeDocumentCount }}</b></span>
          <span :data-state="documentsWaitingForRecognition.length ? 'attention' : 'ready'">待辨識 <b>{{ documentsWaitingForRecognition.length }}</b></span>
          <span :data-state="pendingRecognitionCount ? 'attention' : 'ready'">待確認 <b>{{ pendingRecognitionCount }}</b></span>
        </div>
      </div>
      <div class="source-summary__task" :data-state="sourceReady ? 'ready' : 'attention'">
        <CheckCircle v-if="sourceReady" :size="17" weight="fill" aria-hidden="true" />
        <WarningCircle v-else :size="17" weight="fill" aria-hidden="true" />
        <span>{{ currentTaskDetail }}</span>
        <button
          class="source-summary__action"
          type="button"
          data-testid="source-next-action"
          :disabled="Boolean(extractionBusyDocumentId)"
          @click="runNextSourceAction"
        >
          {{ sourceNextActionLabel() }}
        </button>
      </div>
    </section>

    <form
      v-if="canUpload"
      id="valuation-upload-panel"
      class="upload-bar"
      data-testid="valuation-upload-panel"
      @submit.prevent="emit('upload')"
    >
        <label class="upload-bar__category">
          <span class="sr-only">文件類型</span>
          <select :value="uploadCategory" @change="emit('updateUploadCategory', ($event.target as HTMLSelectElement).value as DocumentCategory)">
            <option value="parcel-factor-list">宗地個別因素清冊</option>
            <option value="cadastral-map">預定徵收範圍地籍圖</option>
            <option value="land-register">土地登記資料</option>
            <option value="original">其他原始查估文件</option>
            <option value="photos">照片</option>
            <option value="attachments">其他附件</option>
            <option value="map-section-sketch">地段示意圖</option>
            <option value="map-zoning">使用分區圖</option>
            <option value="map-land-value-section">地價區段圖</option>
          </select>
        </label>
        <div class="upload-bar__picker" @dragover.prevent @drop.prevent="handleDrop">
          <label for="valuation-source-file">
            <UploadSimple :size="18" weight="bold" aria-hidden="true" />
            <span v-if="uploadFile" class="upload-bar__selected">
              <strong>{{ uploadFile.name }}</strong>
              <small>{{ formatFileSize(uploadFile.size) }}</small>
            </span>
            <span v-else class="upload-bar__selected">
              <strong>選擇或拖曳來源文件</strong>
              <small>PDF、Excel、圖片、DOCX</small>
            </span>
          </label>
          <input id="valuation-source-file" type="file" accept=".pdf,.xls,.xlsx,.png,.jpg,.jpeg,.docx" required @change="emit('chooseUpload', $event)" />
        </div>
        <button class="upload-bar__submit" type="submit" :disabled="uploading || !uploadFile">
          <UploadSimple :size="16" weight="bold" aria-hidden="true" />
          {{ uploading ? '上傳中…' : '上傳文件' }}
        </button>
    </form>

    <div class="document-ai-grid">
      <section class="document-ai-grid__list" aria-labelledby="uploaded-document-list-title">
        <div class="document-list__heading">
          <div>
            <strong id="uploaded-document-list-title">已上傳文件</strong>
            <span>選擇文件後可在右側預覽，再執行辨識。</span>
          </div>
          <small>{{ documents.length }} 份</small>
        </div>
        <ul v-if="documents.length" class="document-list">
          <li
            v-for="document in documents"
            :key="document.documentId"
            :class="{ 'is-selected': previewDocumentId === document.documentId }"
          >
            <div class="document-list__identity">
              <span class="document-list__file-icon" aria-hidden="true"><FileIcon :size="18" weight="regular" /></span>
              <div>
                <strong>{{ document.filename }}</strong>
                <span>{{ documentCategoryLabel(document.documentType) }} · 第 {{ document.versionNo }} 版 · {{ formatFileSize(document.fileSizeBytes) }}</span>
              </div>
              <small :data-ai-state="documentPendingCount(document.documentId) ? 'pending' : 'ready'">
                <WarningCircle v-if="documentPendingCount(document.documentId)" :size="13" weight="fill" aria-hidden="true" />
                <CheckCircle v-else :size="13" weight="fill" aria-hidden="true" />
                {{ documentAiStatus(document.documentId) }}
              </small>
            </div>
            <div class="document-list__actions">
              <button class="document-action" type="button" @click="emit('preview', document.documentId)">
                <Eye :size="14" weight="bold" aria-hidden="true" />
                <span>預覽</span>
              </button>
              <button
                v-if="canPrepareParcelImport(document)"
                class="document-action document-action--primary"
                type="button"
                :data-testid="`parcel-import-preview-${document.documentId}`"
                :disabled="Boolean(documentActionId)"
                @click="emit('prepareParcelImport', document.documentId)"
              >
                <MagicWand :size="14" weight="bold" aria-hidden="true" />
                <span>解析宗地清冊</span>
              </button>
              <button
                v-if="canExtractDocument(document)"
                class="document-action document-action--primary"
                type="button"
                :data-testid="`extract-document-${document.documentId}`"
                :disabled="Boolean(extractionBusyDocumentId)"
                @click="emit('extract', document.documentId)"
              >
                <MagicWand v-if="!documentCandidateCount(document.documentId)" :size="14" weight="bold" aria-hidden="true" />
                <ArrowClockwise v-else :size="14" weight="bold" aria-hidden="true" />
                <span>{{ extractionBusyDocumentId === document.documentId ? '辨識中…' : documentCandidateCount(document.documentId) ? '重新辨識' : '自動辨識' }}</span>
              </button>
              <details v-if="canManageSourceDocument(document)" class="document-list__manage-details">
                <summary>管理文件</summary>
                <div class="document-list__manage">
                  <label :for="`document-category-${document.documentId}`"><Tag :size="13" weight="bold" aria-hidden="true" />文件分類</label>
                  <select
                    :id="`document-category-${document.documentId}`"
                    :value="categoryValue(document.documentId)"
                    :data-testid="`document-category-${document.documentId}`"
                    :disabled="documentActionId === document.documentId"
                    @change="emit('updateCategory', document.documentId, ($event.target as HTMLSelectElement).value as DocumentCategory)"
                  >
                    <option v-for="category in sourceCategories" :key="category" :value="category">{{ documentCategoryLabel(category) }}</option>
                  </select>
                  <button
                    class="document-action"
                    type="button"
                    :data-testid="`reclassify-document-${document.documentId}`"
                    :disabled="documentActionId === document.documentId || categoryValue(document.documentId) === document.documentType"
                    @click="emit('reclassify', document.documentId)"
                  >
                    <Tag :size="14" weight="bold" aria-hidden="true" />
                    <span>套用分類</span>
                  </button>
                  <button
                    class="document-action document-action--danger"
                    type="button"
                    :data-testid="`remove-document-${document.documentId}`"
                    :disabled="documentActionId === document.documentId"
                    @click="emit('remove', document.documentId, document.filename)"
                  >
                    <Trash :size="14" weight="bold" aria-hidden="true" />
                    <span>移除</span>
                  </button>
                </div>
              </details>
            </div>
          </li>
        </ul>
        <div v-else class="document-list__empty">
          <FileSearch :size="28" weight="regular" aria-hidden="true" />
          <strong>尚未上傳來源文件</strong>
          <span>先從上方選擇文件類型並上傳；建議優先準備地籍圖與土地登記資料。</span>
        </div>
      </section>

      <section class="document-preview" aria-labelledby="document-preview-title">
        <div class="document-preview__heading">
          <div>
            <strong id="document-preview-title">文件預覽</strong>
            <span v-if="previewDocument">{{ previewDocument.filename }}{{ previewPage ? ` · 第 ${previewPage} 頁` : '' }}</span>
            <span v-else>從左側選擇一份文件查看內容</span>
          </div>
          <button v-if="previewDocument" class="document-action" type="button" @click="emit('download', previewDocument)">
            <DownloadSimple :size="14" weight="bold" aria-hidden="true" />
            <span>下載原檔</span>
          </button>
        </div>
        <div class="document-preview__body">
          <p v-if="previewLoading" class="empty-copy">正在載入文件預覽…</p>
          <p v-else-if="previewError" class="document-preview__message">{{ previewError }}</p>
          <iframe v-else-if="previewIsPdf && previewSourceUrl" :src="previewSourceUrl" title="PDF 文件預覽" />
          <img v-else-if="previewIsImage && previewSourceUrl" :src="previewSourceUrl" :alt="previewDocument?.filename || '來源文件預覽'">
          <SpreadsheetPreview v-else-if="previewIsSpreadsheet && spreadsheetPreview" :preview="spreadsheetPreview" />
          <DocumentTextPreview v-else-if="previewIsDocx && textPreview" :preview="textPreview" />
          <div v-else class="document-preview__empty">
            <FileSearch :size="34" weight="regular" aria-hidden="true" />
            <strong>{{ previewDocument ? '按「預覽」載入文件' : '尚未選擇文件' }}</strong>
            <span>PDF、圖片、Excel 與 DOCX 可直接預覽；其他格式仍可下載原檔查看。</span>
          </div>
        </div>
        <div v-if="selectedCandidate?.source_text && selectedCandidate.document_id === previewDocumentId" class="document-preview__evidence" data-testid="candidate-source-evidence">
          <strong>辨識來源原文{{ selectedCandidate.source_page ? ` · 第 ${selectedCandidate.source_page} 頁` : '' }}</strong>
          <blockquote>{{ selectedCandidate.source_text }}</blockquote>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.document-workspace { display:grid; gap:10px; min-width:0; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }

.source-summary { display:grid; gap:7px; padding:10px 12px; border:1px solid #d8e3ec; border-radius:10px; background:#fbfcfe; }
.source-summary__main { display:flex; align-items:center; justify-content:space-between; gap:12px; min-width:0; }
.source-summary__title { display:flex; min-width:0; align-items:baseline; gap:9px; }
.source-summary__title > span { flex:0 0 auto; color:#647b90; font-size:9px; font-weight:900; letter-spacing:.08em; }
.source-summary__title > strong { overflow:hidden; color:var(--app-ink); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.source-summary__metrics { display:flex; flex:0 0 auto; flex-wrap:wrap; justify-content:flex-end; gap:5px; }
.source-summary__metrics span { padding:4px 7px; border-radius:999px; color:#657789; background:#eef3f7; font-size:8px; font-weight:800; white-space:nowrap; }
.source-summary__metrics b { color:#2e5984; font-size:9px; }
.source-summary__metrics span[data-state="attention"] { color:#925421; background:#fff0df; }
.source-summary__metrics span[data-state="ready"] { color:#2f745b; background:#edf8f3; }
.source-summary__task { display:flex; min-height:32px; align-items:center; gap:7px; padding:6px 8px; border-radius:8px; color:#8a5a23; background:#fff7e9; font-size:9px; }
.source-summary__task[data-state="ready"] { color:#2f745b; background:#edf8f3; }
.source-summary__task > span { min-width:0; flex:1; }
.source-summary__action { min-height:28px; flex:0 0 auto; padding:4px 9px; border:1px solid #2e5984; border-radius:7px; color:#fff; background:#2e5984; cursor:pointer; font-size:9px; font-weight:900; white-space:nowrap; }
.source-summary__action:disabled { cursor:not-allowed; opacity:.5; }

.upload-bar { display:grid; grid-template-columns:210px minmax(260px,1fr) auto; align-items:stretch; gap:8px; min-width:0; padding:8px; border:1px solid #dbe4ec; border-radius:10px; background:#fff; }
.upload-bar__category select { width:100%; height:42px; padding:0 10px; border:1px solid #cbd7e2; border-radius:8px; color:var(--app-ink); background:#fff; font:inherit; font-size:10px; }
.upload-bar__picker { position:relative; min-width:0; border:1px dashed #aebfce; border-radius:8px; background:#f9fbfd; }
.upload-bar__picker:focus-within { border-color:#2e5984; box-shadow:0 0 0 3px rgba(46,89,132,.08); }
.upload-bar__picker label { display:flex; height:40px; align-items:center; gap:8px; padding:0 10px; color:#526b82; cursor:pointer; }
.upload-bar__picker input { position:absolute; width:1px; height:1px; overflow:hidden; opacity:0; pointer-events:none; }
.upload-bar__selected { display:flex; min-width:0; align-items:center; gap:7px; }
.upload-bar__selected strong { overflow:hidden; color:#34495f; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.upload-bar__selected small { flex:0 0 auto; color:#7a8999; font-size:8px; }
.upload-bar__submit { display:inline-flex; min-width:104px; height:42px; align-items:center; justify-content:center; gap:5px; padding:0 11px; border:1px solid #2e5984; border-radius:8px; color:#fff; background:#2e5984; cursor:pointer; font-size:9px; font-weight:900; }
.upload-bar__submit:disabled { cursor:not-allowed; opacity:.46; }

.document-ai-grid { display:grid; grid-template-columns:minmax(300px,.48fr) minmax(0,1fr); gap:10px; height:clamp(500px,calc(100vh - 450px),700px); min-height:500px; }
.document-ai-grid__list { display:grid; grid-template-rows:auto minmax(0,1fr); min-width:0; overflow:hidden; border:1px solid #dbe3eb; border-radius:10px; background:#fff; }
.document-list__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:12px 13px; border-bottom:1px solid #e4e9ef; background:#fafbfd; }
.document-list__heading > div { display:grid; gap:2px; min-width:0; }
.document-list__heading strong { color:var(--app-ink); font-size:11px; }
.document-list__heading span { color:var(--app-muted); font-size:9px; }
.document-list__heading > small { color:#63768a; font-size:9px; font-weight:850; }
.document-list { display:grid; align-content:start; gap:0; min-height:0; margin:0; padding:0; overflow:auto; list-style:none; }
.document-list li { display:grid; gap:9px; min-width:0; padding:11px 12px; border:0; border-bottom:1px solid #edf1f5; background:#fff; }
.document-list li:last-child { border-bottom:0; }
.document-list li.is-selected { background:#f4f8fc; box-shadow:inset 3px 0 0 #2e5984; }
.document-list__identity { display:grid !important; grid-template-columns:auto minmax(0,1fr) auto; align-items:start; gap:8px !important; min-width:0; }
.document-list__identity > div { display:grid; gap:2px; min-width:0; }
.document-list__file-icon { display:grid; width:28px; height:28px; place-items:center; border-radius:7px; color:#536b83; background:#eef3f7; }
.document-list__identity strong { overflow:hidden; color:var(--app-ink); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.document-list__identity span { color:var(--app-muted); font-size:9px; }
.document-list__identity small { display:inline-flex; width:fit-content; align-items:center; gap:4px; padding:4px 6px; border-radius:999px; color:#2f745b; background:#edf8f3; font-size:8px; font-weight:850; white-space:nowrap; }
.document-list__identity small[data-ai-state="pending"] { color:#925421; background:#fff0df; }
.document-list__actions { display:flex !important; width:100%; min-width:0; align-items:center; flex-wrap:wrap; gap:6px !important; }
.document-list__analysis-form { display:flex; min-width:190px; flex:1 1 210px; align-items:center; gap:6px; color:var(--app-muted); font-size:9px; font-weight:800; }
.document-list__analysis-form > span { flex:0 0 auto; }
.document-list__analysis-form select,
.document-list__manage select { width:100%; min-width:0; min-height:34px; padding:5px 7px; border:1px solid #ced8e2; border-radius:7px; color:var(--app-ink); background:#fff; font-size:9px; }
.document-list__manage-details { flex:1 1 100%; width:100%; padding-top:2px; }
.document-list__manage-details > summary { width:fit-content; color:#63768a; cursor:pointer; font-size:9px; font-weight:850; }
.document-list__manage-details[open] > summary { margin-bottom:4px; color:#2e5984; }
.document-list__manage { display:grid !important; grid-template-columns:auto minmax(0,1fr) auto auto; flex:1 1 100%; width:100%; min-width:0; align-items:center; gap:6px !important; padding-top:7px; border-top:1px dashed #e2e7ec; }
.document-list__manage label { display:inline-flex; align-items:center; gap:4px; color:var(--app-muted); font-size:9px; font-weight:800; }
.document-action { display:inline-flex; min-height:34px; align-items:center; justify-content:center; gap:5px; padding:5px 9px; border:1px solid #cfd9e3; border-radius:7px; color:#52677d; background:#fff; cursor:pointer; font-size:9px; font-weight:900; white-space:nowrap; }
.document-action:hover { border-color:#aebfce; background:#f8fafc; }
.document-action--primary { border-color:#c8d8e8; color:#244d73; background:#edf4fb; }
.document-action--danger { border-color:#ead2cd; color:#9d4738; background:#fffafa; }
.document-action:disabled { cursor:not-allowed; opacity:.5; }
.document-list__empty { display:grid; min-height:0; place-items:center; align-content:center; gap:6px; padding:24px; color:#8090a0; text-align:center; }
.document-list__empty strong { color:#4c6075; font-size:11px; }
.document-list__empty span { max-width:300px; font-size:9px; line-height:1.6; }

.document-preview { display:grid; grid-template-rows:auto minmax(0,1fr) auto; min-width:0; min-height:0; overflow:hidden; border:1px solid #d8e1eb; border-radius:10px; background:#fff; }
.document-preview__heading { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:11px 13px; border-bottom:1px solid #e1e7ee; background:#fafbfd; }
.document-preview__heading > div { display:grid; gap:2px; min-width:0; }
.document-preview__heading strong { color:var(--app-ink); font-size:11px; }
.document-preview__heading span { overflow:hidden; color:var(--app-muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.document-preview__heading .document-action { flex:0 0 auto; }
.document-preview__body { display:grid; min-height:0; place-items:center; overflow:auto; background:#eef1f4; }
.document-preview__body iframe { width:100%; height:100%; min-height:0; border:0; background:#fff; }
.document-preview__body img { display:block; max-width:100%; max-height:100%; object-fit:contain; }
.document-preview__empty { display:grid; gap:6px; max-width:310px; justify-items:center; padding:28px; color:#75879a; text-align:center; }
.document-preview__empty strong { color:#34495f; font-size:12px; }
.document-preview__empty span,.document-preview__message { color:#6b798a; font-size:10px; line-height:1.6; }
.document-preview__message { margin:0; padding:24px; text-align:center; }
.document-preview__evidence { display:grid; gap:6px; padding:11px 13px; border-top:1px solid #e1e7ee; background:#fff8ee; }
.document-preview__evidence strong { color:#8a531e; font-size:9px; }
.document-preview__evidence blockquote { margin:0; color:#3d4a58; font-size:10px; line-height:1.6; white-space:pre-wrap; }
.empty-copy { margin:0; color:var(--app-muted); font-size:11px; }

@media (max-width:1100px){
  .document-ai-grid{grid-template-columns:minmax(260px,.55fr) minmax(0,1fr)}
}
@media (max-width:760px){
  .source-summary__main{align-items:flex-start;flex-direction:column}
  .source-summary__metrics{justify-content:flex-start}
  .source-summary__task{align-items:flex-start;flex-wrap:wrap}
  .source-summary__action{width:100%}
  .upload-bar{grid-template-columns:1fr}
  .upload-bar__submit{width:100%}
  .document-ai-grid{grid-template-columns:1fr;height:auto;min-height:0}
  .document-ai-grid__list{max-height:420px}
  .document-preview{min-height:520px}
  .document-list__identity{grid-template-columns:auto minmax(0,1fr)}
  .document-list__identity small{grid-column:2}
  .document-list__actions{align-items:stretch}
  .document-list__analysis-form{min-width:0;align-items:stretch;flex-direction:column}
  .document-list__manage{grid-template-columns:1fr;align-items:stretch}
  .document-preview__heading{align-items:stretch;flex-direction:column}
  .document-action{width:100%}
}
</style>
