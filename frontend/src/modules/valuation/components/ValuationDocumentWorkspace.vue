<script setup lang="ts">
import { computed } from 'vue'
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

function focusUpload(category?: DocumentCategory): void {
  if (category) emit('updateUploadCategory', category)
  requestAnimationFrame(() => {
    const panel = document.getElementById('valuation-upload-panel')
    panel?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    panel?.querySelector<HTMLElement>('select, input, button')?.focus()
  })
}

function runNextSourceAction(): void {
  const missing = missingRequiredDocuments.value[0]
  if (missing) {
    focusUpload(missing.category)
    return
  }
  const pendingDocument = documentsWaitingForRecognition.value[0]
  if (pendingDocument) {
    emit('extract', pendingDocument.documentId)
    return
  }
  if (pendingRecognitionCount.value) emit('reviewCandidates')
}

function sourceNextActionLabel(): string {
  const missing = missingRequiredDocuments.value[0]
  if (missing) return `上傳${missing.label}`
  if (documentsWaitingForRecognition.value.length) return `辨識下一份文件（${documentsWaitingForRecognition.value.length}）`
  if (pendingRecognitionCount.value) return `確認辨識結果（${pendingRecognitionCount.value}）`
  return '來源資料已完成'
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
    <div class="document-workspace__heading">
      <div class="document-workspace__title">
        <span class="document-workspace__title-icon" aria-hidden="true">
          <FileSearch :size="21" weight="duotone" />
        </span>
        <div>
          <strong>來源文件</strong>
          <span>先整理案件來源文件，再執行文字擷取與欄位辨識。辨識結果不會直接寫入正式資料，仍需人工確認。</span>
        </div>
      </div>
      <div class="document-workspace__stats" aria-label="文件處理摘要">
        <span><b>{{ documents.length }}</b> 份文件</span>
        <span><b>{{ uploadedRequiredDocumentCount }}/{{ requiredDocumentCount }}</b> 必要資料</span>
        <span :data-state="pendingRecognitionCount ? 'attention' : 'ready'"><b>{{ pendingRecognitionCount }}</b> 待確認</span>
      </div>
    </div>

    <section class="source-flow" data-testid="source-data-flow" aria-labelledby="source-data-flow-title">
      <div class="source-flow__heading">
        <div>
          <span>目前進度</span>
          <strong id="source-data-flow-title">把來源資料整理到可以進入估價資料</strong>
        </div>
        <button
          v-if="!sourceReady"
          class="source-flow__next"
          type="button"
          data-testid="source-next-action"
          :disabled="Boolean(extractionBusyDocumentId)"
          @click="runNextSourceAction"
        >
          {{ sourceNextActionLabel() }}
        </button>
        <span v-else class="source-flow__ready">
          <CheckCircle :size="15" weight="fill" aria-hidden="true" />
          來源資料已完成
        </span>
      </div>
      <div class="source-flow__steps">
        <article :data-state="missingRequiredDocuments.length ? 'active' : 'done'">
          <span class="source-flow__index">1</span>
          <div>
            <strong>補齊必要來源</strong>
            <small>{{ missingRequiredDocuments.length ? `還缺 ${missingRequiredDocuments.length} 類必要資料` : '必要來源已齊' }}</small>
          </div>
        </article>
        <article :data-state="missingRequiredDocuments.length ? 'pending' : documentsWaitingForRecognition.length ? 'active' : 'done'">
          <span class="source-flow__index">2</span>
          <div>
            <strong>自動辨識文件</strong>
            <small>{{ documentsWaitingForRecognition.length ? `${documentsWaitingForRecognition.length} 份可辨識文件尚未處理` : '目前文件已完成辨識' }}</small>
          </div>
        </article>
        <article :data-state="missingRequiredDocuments.length || documentsWaitingForRecognition.length ? 'pending' : pendingRecognitionCount ? 'active' : 'done'">
          <span class="source-flow__index">3</span>
          <div>
            <strong>人工確認結果</strong>
            <small>{{ pendingRecognitionCount ? `${pendingRecognitionCount} 筆辨識結果待確認` : '沒有待確認結果' }}</small>
          </div>
        </article>
      </div>
    </section>

    <section class="startup-documents" aria-labelledby="startup-documents-title">
      <div class="startup-documents__heading">
        <div>
          <strong id="startup-documents-title">建議先準備的來源資料</strong>
          <span>不用先準備完整查估書；先補齊案件啟動所需資料即可。</span>
        </div>
        <small>{{ uploadedRequiredDocumentCount === requiredDocumentCount ? '必要資料已齊' : `必要資料尚缺 ${requiredDocumentCount - uploadedRequiredDocumentCount} 類` }}</small>
      </div>
      <div class="startup-documents__grid">
        <article v-for="item in startupDocuments" :key="item.category" :data-ready="hasActiveCategory(item.category)">
          <span class="startup-documents__icon" aria-hidden="true">
            <CheckCircle v-if="hasActiveCategory(item.category)" :size="18" weight="fill" />
            <WarningCircle v-else :size="18" weight="regular" />
          </span>
          <div class="startup-documents__copy">
            <strong>{{ item.label }}</strong>
            <span>{{ item.detail }}</span>
          </div>
          <div class="startup-documents__state">
            <small :data-state="hasActiveCategory(item.category) ? 'ready' : item.requirement">
              {{ hasActiveCategory(item.category) ? '已上傳' : item.requirement === 'required' ? '尚未上傳' : '建議上傳' }}
            </small>
            <button
              v-if="!hasActiveCategory(item.category) && canUpload"
              type="button"
              @click="focusUpload(item.category)"
            >
              上傳此類
            </button>
          </div>
        </article>
      </div>
    </section>

    <form v-if="canUpload" class="upload-panel" data-testid="valuation-upload-panel" @submit.prevent="emit('upload')">
      <div class="upload-panel__intro">
        <span class="upload-panel__icon" aria-hidden="true"><UploadSimple :size="20" weight="bold" /></span>
        <div>
          <strong>上傳來源文件</strong>
          <span>支援 PDF、Excel、圖片與 DOCX。宗地個別因素清冊建議直接上傳原始 XLS／XLSX。</span>
        </div>
      </div>
      <div class="upload-panel__controls">
        <label class="upload-panel__category">
          <span>文件類型</span>
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
        <div class="upload-dropzone" @dragover.prevent @drop.prevent="handleDrop">
          <label for="valuation-source-file">
            <UploadSimple :size="18" weight="bold" aria-hidden="true" />
            <span v-if="uploadFile" class="upload-dropzone__selected">
              <strong>{{ uploadFile.name }}</strong>
              <small>{{ formatFileSize(uploadFile.size) }} · 可直接上傳</small>
            </span>
            <span v-else class="upload-dropzone__selected">
              <strong>拖曳檔案到這裡，或點擊選擇</strong>
              <small>PDF、XLS、XLSX、PNG、JPG、DOCX</small>
            </span>
          </label>
          <input id="valuation-source-file" type="file" accept=".pdf,.xls,.xlsx,.png,.jpg,.jpeg,.docx" required @change="emit('chooseUpload', $event)" />
        </div>
        <button class="upload-panel__submit" type="submit" :disabled="uploading || !uploadFile">
          <UploadSimple :size="16" weight="bold" aria-hidden="true" />
          {{ uploading ? '上傳中…' : '上傳文件' }}
        </button>
      </div>
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
.document-workspace { display:grid; gap:14px; margin-top:16px; }
.document-workspace__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; padding:2px 2px 0; }
.document-workspace__title { display:flex; align-items:flex-start; gap:10px; min-width:0; }
.document-workspace__title-icon { display:grid; width:38px; height:38px; flex:0 0 auto; place-items:center; border-radius:9px; color:#2e5984; background:#edf4fb; }
.document-workspace__title > div { display:grid; gap:4px; min-width:0; }
.document-workspace__title strong { color:var(--app-ink); font-size:16px; }
.document-workspace__title span { max-width:760px; color:var(--app-muted); font-size:11px; line-height:1.65; }
.document-workspace__stats { display:flex; flex:0 0 auto; flex-wrap:wrap; justify-content:flex-end; gap:6px; }
.document-workspace__stats span { padding:6px 9px; border-radius:999px; color:#56697e; background:#f0f4f8; font-size:9px; font-weight:750; white-space:nowrap; }
.document-workspace__stats b { color:#293f56; font-size:10px; }
.document-workspace__stats [data-state="attention"] { color:#925421; background:#fff0df; }
.document-workspace__stats [data-state="ready"] { color:#2f745b; background:#edf8f3; }

.source-flow { display:grid; gap:12px; padding:14px 15px; border:1px solid #cfdce8; border-radius:10px; background:#f7fafd; }
.source-flow__heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.source-flow__heading > div { display:grid; gap:3px; }
.source-flow__heading > div > span { color:#63768a; font-size:9px; font-weight:900; letter-spacing:.08em; }
.source-flow__heading strong { color:var(--app-ink); font-size:13px; }
.source-flow__next { min-height:38px; padding:7px 12px; border:1px solid #2e5984; border-radius:8px; color:#fff; background:#2e5984; cursor:pointer; font-size:10px; font-weight:900; }
.source-flow__next:disabled { cursor:not-allowed; opacity:.5; }
.source-flow__ready { display:inline-flex; align-items:center; gap:6px; padding:7px 10px; border-radius:999px; color:#2f745b; background:#eaf7f0; font-size:10px; font-weight:900; }
.source-flow__steps { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
.source-flow__steps article { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:start; gap:8px; padding:10px 11px; border:1px solid #e0e6ec; border-radius:8px; background:#fff; }
.source-flow__steps article[data-state="active"] { border-color:#b7cce0; background:#f2f7fc; }
.source-flow__steps article[data-state="done"] { border-color:#d3e5dc; background:#f7fbf9; }
.source-flow__steps article[data-state="pending"] { opacity:.62; }
.source-flow__index { display:grid; width:23px; height:23px; place-items:center; border-radius:999px; color:#fff; background:#7a8b9d; font-size:9px; font-weight:900; }
.source-flow__steps article[data-state="active"] .source-flow__index { background:#2e5984; }
.source-flow__steps article[data-state="done"] .source-flow__index { background:#3c8368; }
.source-flow__steps article > div { display:grid; gap:3px; min-width:0; }
.source-flow__steps strong { color:var(--app-ink); font-size:10px; }
.source-flow__steps small { color:var(--app-muted); font-size:9px; line-height:1.45; }

.startup-documents { display:grid; gap:10px; padding:13px 14px; border:1px solid #dce5ee; border-radius:10px; background:#f8fafc; }
.startup-documents__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; }
.startup-documents__heading > div { display:grid; gap:3px; }
.startup-documents__heading strong { color:var(--app-ink); font-size:12px; }
.startup-documents__heading span { color:var(--app-muted); font-size:10px; }
.startup-documents__heading > small { padding:4px 7px; border-radius:999px; color:#52657a; background:#eaf0f6; font-size:9px; font-weight:850; white-space:nowrap; }
.startup-documents__grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
.startup-documents__grid article { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:start; gap:8px; min-width:0; padding:10px; border:1px solid #e1e7ed; border-radius:8px; background:#fff; }
.startup-documents__grid article[data-ready="true"] { border-color:#d3e5dc; background:#fbfefd; }
.startup-documents__icon { display:grid; width:22px; height:22px; place-items:center; color:#a76c2d; }
.startup-documents__grid article[data-ready="true"] .startup-documents__icon { color:#3c8368; }
.startup-documents__copy { display:grid; gap:3px; min-width:0; }
.startup-documents__copy strong { color:var(--app-ink); font-size:10px; }
.startup-documents__copy span { color:var(--app-muted); font-size:9px; line-height:1.5; }
.startup-documents__state { display:grid; justify-items:end; gap:5px; }
.startup-documents__state small { padding:4px 7px; border-radius:999px; color:#925421; background:#fff0df; font-size:8px; font-weight:850; white-space:nowrap; }
.startup-documents__state small[data-state="required"] { color:#a44334; background:#fff0ed; }
.startup-documents__state small[data-state="ready"] { color:#2f745b; background:#edf8f3; }
.startup-documents__state button { padding:0; border:0; color:#2e5984; background:transparent; cursor:pointer; font-size:8px; font-weight:900; text-decoration:underline; text-underline-offset:2px; }

.upload-panel { display:grid; gap:12px; padding:14px; border:1px solid #d7e1eb; border-radius:10px; background:#fff; }
.upload-panel__intro { display:flex; align-items:flex-start; gap:9px; }
.upload-panel__icon { display:grid; width:32px; height:32px; flex:0 0 32px; place-items:center; border-radius:8px; color:#2e5984; background:#edf4fb; }
.upload-panel__intro > div { display:grid; gap:3px; }
.upload-panel__intro strong { color:var(--app-ink); font-size:12px; }
.upload-panel__intro span { color:var(--app-muted); font-size:10px; line-height:1.55; }
.upload-panel__controls { display:grid; grid-template-columns:210px minmax(0,1fr) auto; align-items:stretch; gap:9px; }
.upload-panel__category { display:grid; align-content:start; gap:5px; color:var(--app-ink-soft); font-size:10px; font-weight:800; }
.upload-panel__category select { min-height:50px; padding:8px 10px; border:1px solid #ccd7e2; border-radius:8px; color:var(--app-ink); background:#fff; font:inherit; }
.upload-dropzone { position:relative; min-width:0; border:1px dashed #aebfce; border-radius:8px; background:#f9fbfd; }
.upload-dropzone:focus-within { border-color:#2e5984; box-shadow:0 0 0 3px rgba(46,89,132,.09); }
.upload-dropzone label { display:flex; min-height:50px; align-items:center; gap:9px; padding:8px 11px; color:#536b83; cursor:pointer; }
.upload-dropzone input { position:absolute; width:1px; height:1px; overflow:hidden; opacity:0; pointer-events:none; }
.upload-dropzone__selected { display:grid; gap:2px; min-width:0; }
.upload-dropzone__selected strong { overflow:hidden; color:#34495f; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.upload-dropzone__selected small { color:#7a8999; font-size:9px; line-height:1.4; }
.upload-panel__submit { display:inline-flex; min-width:116px; min-height:50px; align-items:center; justify-content:center; gap:6px; padding:9px 13px; border:1px solid #2e5984; border-radius:8px; color:#fff; background:#2e5984; cursor:pointer; font-size:10px; font-weight:900; }
.upload-panel__submit:disabled { cursor:not-allowed; opacity:.46; }

.document-ai-grid { display:grid; grid-template-columns:minmax(0,.86fr) minmax(0,1.14fr); gap:12px; min-height:500px; }
.document-ai-grid__list { min-width:0; overflow:hidden; border:1px solid #dbe3eb; border-radius:10px; background:#fff; }
.document-list__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:12px 13px; border-bottom:1px solid #e4e9ef; background:#fafbfd; }
.document-list__heading > div { display:grid; gap:2px; min-width:0; }
.document-list__heading strong { color:var(--app-ink); font-size:11px; }
.document-list__heading span { color:var(--app-muted); font-size:9px; }
.document-list__heading > small { color:#63768a; font-size:9px; font-weight:850; }
.document-list { display:grid; gap:0; margin:0; padding:0; list-style:none; }
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
.document-list__empty { display:grid; min-height:270px; place-items:center; align-content:center; gap:6px; padding:24px; color:#8090a0; text-align:center; }
.document-list__empty strong { color:#4c6075; font-size:11px; }
.document-list__empty span { max-width:300px; font-size:9px; line-height:1.6; }

.document-preview { display:grid; grid-template-rows:auto minmax(390px,1fr) auto; min-width:0; overflow:hidden; border:1px solid #d8e1eb; border-radius:10px; background:#fff; }
.document-preview__heading { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:11px 13px; border-bottom:1px solid #e1e7ee; background:#fafbfd; }
.document-preview__heading > div { display:grid; gap:2px; min-width:0; }
.document-preview__heading strong { color:var(--app-ink); font-size:11px; }
.document-preview__heading span { overflow:hidden; color:var(--app-muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.document-preview__heading .document-action { flex:0 0 auto; }
.document-preview__body { display:grid; min-height:390px; place-items:center; overflow:hidden; background:#eef1f4; }
.document-preview__body iframe { width:100%; height:100%; min-height:500px; border:0; background:#fff; }
.document-preview__body img { display:block; max-width:100%; max-height:560px; object-fit:contain; }
.document-preview__empty { display:grid; gap:6px; max-width:310px; justify-items:center; padding:28px; color:#75879a; text-align:center; }
.document-preview__empty strong { color:#34495f; font-size:12px; }
.document-preview__empty span,.document-preview__message { color:#6b798a; font-size:10px; line-height:1.6; }
.document-preview__message { margin:0; padding:24px; text-align:center; }
.document-preview__evidence { display:grid; gap:6px; padding:11px 13px; border-top:1px solid #e1e7ee; background:#fff8ee; }
.document-preview__evidence strong { color:#8a531e; font-size:9px; }
.document-preview__evidence blockquote { margin:0; color:#3d4a58; font-size:10px; line-height:1.6; white-space:pre-wrap; }
.empty-copy { margin:0; color:var(--app-muted); font-size:11px; }

@media (max-width:1100px){
  .document-ai-grid{grid-template-columns:1fr}
  .document-preview__body iframe{min-height:520px}
}
@media (max-width:760px){
  .document-workspace__heading,.source-flow__heading,.startup-documents__heading{align-items:flex-start;flex-direction:column}
  .document-workspace__stats{justify-content:flex-start}
  .source-flow__steps{grid-template-columns:1fr}
  .source-flow__next{width:100%}
  .startup-documents__grid{grid-template-columns:1fr}
  .upload-panel__controls{grid-template-columns:1fr}
  .document-list__identity{grid-template-columns:auto minmax(0,1fr)}
  .document-list__identity small{grid-column:2}
  .document-list__actions{align-items:stretch}
  .document-list__analysis-form{min-width:0;align-items:stretch;flex-direction:column}
  .document-list__manage{grid-template-columns:1fr;align-items:stretch}
  .document-preview__heading{align-items:stretch;flex-direction:column}
  .document-action,.upload-panel__submit{width:100%}
}
</style>
