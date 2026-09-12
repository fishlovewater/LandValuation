<script setup lang="ts">
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
  reclassify: [documentId: string]
  remove: [documentId: string, filename: string]
  download: [document: DocumentArtifactModel]
  updateAnalysisForm: [documentId: string, formCode: FieldAnalysisFormCode]
  updateCategory: [documentId: string, category: DocumentCategory]
  updateUploadCategory: [category: DocumentCategory]
  chooseUpload: [event: Event]
  upload: []
}>()

function analysisFormValue(documentId: string): FieldAnalysisFormCode {
  return props.documentAnalysisForm[documentId] ?? 'F03'
}

function categoryValue(documentId: string): DocumentCategory {
  return props.documentCategoryDraft[documentId] ?? 'original'
}

function hasActiveCategory(category: DocumentCategory): boolean {
  return props.documents.some((document) => document.isActive && document.documentType === category)
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
      <div>
        <strong>來源文件與文件辨識</strong>
        <span>新案件建議先準備宗地個別因素清冊、預定徵收範圍地籍圖與土地登記資料。上傳後可預覽並進行辨識；辨識結果仍需人工確認。</span>
      </div>
      <span>{{ documents.length }} 份</span>
    </div>

    <section class="startup-documents" aria-labelledby="startup-documents-title">
      <div class="startup-documents__heading">
        <strong id="startup-documents-title">案件啟動資料</strong>
        <span>先從這 3 類資料開始，不需要先準備完整查估書。</span>
      </div>
      <div class="startup-documents__grid">
        <article v-for="item in startupDocuments" :key="item.category">
          <div>
            <strong>{{ item.label }}</strong>
            <span>{{ item.detail }}</span>
          </div>
          <small
            :data-state="hasActiveCategory(item.category) ? 'ready' : item.requirement"
          >
            {{ hasActiveCategory(item.category) ? '已上傳' : item.requirement === 'required' ? '尚未上傳' : '建議上傳' }}
          </small>
        </article>
      </div>
    </section>

    <div class="document-ai-grid">
      <div class="document-ai-grid__list">
        <ul v-if="documents.length" class="document-list">
          <li
            v-for="document in documents"
            :key="document.documentId"
            :class="{ 'is-selected': previewDocumentId === document.documentId }"
          >
            <div class="document-list__identity">
              <strong>{{ document.filename }}</strong>
              <span>{{ documentCategoryLabel(document.documentType) }} · 第 {{ document.versionNo }} 版 · {{ formatFileSize(document.fileSizeBytes) }}</span>
              <small :data-ai-state="documentPendingCount(document.documentId) ? 'pending' : 'ready'">{{ documentAiStatus(document.documentId) }}</small>
            </div>
            <div class="document-list__actions">
              <button class="finding-action" type="button" @click="emit('preview', document.documentId)">預覽</button>
              <button
                v-if="canPrepareParcelImport(document)"
                class="finding-action finding-action--primary"
                type="button"
                :data-testid="`parcel-import-preview-${document.documentId}`"
                :disabled="Boolean(documentActionId)"
                @click="emit('prepareParcelImport', document.documentId)"
              >解析宗地清冊</button>
              <label v-if="canExtractDocument(document)" class="document-list__analysis-form">
                <span>文件類型提示</span>
                <select
                  :value="analysisFormValue(document.documentId)"
                  :data-testid="`document-analysis-form-${document.documentId}`"
                  :disabled="Boolean(extractionBusyDocumentId)"
                  @change="emit('updateAnalysisForm', document.documentId, ($event.target as HTMLSelectElement).value as FieldAnalysisFormCode)"
                >
                  <option v-for="code in analysisFormCodes" :key="code" :value="code">
                    {{ formDisplayName(code) }}
                  </option>
                </select>
              </label>
              <button
                v-if="canExtractDocument(document)"
                class="finding-action finding-action--primary"
                type="button"
                :data-testid="`extract-document-${document.documentId}`"
                :disabled="Boolean(extractionBusyDocumentId)"
                @click="emit('extract', document.documentId)"
              >
                {{ extractionBusyDocumentId === document.documentId ? '????' : documentCandidateCount(document.documentId) ? '????' : '??????' }}
              </button>
              <div v-if="canManageSourceDocument(document)" class="document-list__manage">
                <label :for="`document-category-${document.documentId}`">分類</label>
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
                  class="finding-action"
                  type="button"
                  :data-testid="`reclassify-document-${document.documentId}`"
                  :disabled="documentActionId === document.documentId || categoryValue(document.documentId) === document.documentType"
                  @click="emit('reclassify', document.documentId)"
                >套用</button>
                <button
                  class="finding-action finding-action--danger"
                  type="button"
                  :data-testid="`remove-document-${document.documentId}`"
                  :disabled="documentActionId === document.documentId"
                  @click="emit('remove', document.documentId, document.filename)"
                >移除</button>
              </div>
            </div>
          </li>
        </ul>
        <p v-else class="empty-copy">尚未上傳案件啟動資料。建議先從宗地個別因素清冊、地籍圖與土地登記資料開始。</p>
      </div>

      <section class="document-preview" aria-labelledby="document-preview-title">
        <div class="document-preview__heading">
          <div>
            <strong id="document-preview-title">文件預覽</strong>
            <span v-if="previewDocument">{{ previewDocument.filename }}{{ previewPage ? ` · 第 ${previewPage} 頁` : '' }}</span>
            <span v-else>從左側選擇一份文件查看內容</span>
          </div>
          <button v-if="previewDocument" class="finding-action" type="button" @click="emit('download', previewDocument)">下載原檔</button>
        </div>
        <div class="document-preview__body">
          <p v-if="previewLoading" class="empty-copy">正在載入文件預覽…</p>
          <p v-else-if="previewError" class="document-preview__message">{{ previewError }}</p>
          <iframe v-else-if="previewIsPdf && previewSourceUrl" :src="previewSourceUrl" title="PDF 文件預覽" />
          <img v-else-if="previewIsImage && previewSourceUrl" :src="previewSourceUrl" :alt="previewDocument?.filename || '來源文件預覽'">
          <SpreadsheetPreview v-else-if="previewIsSpreadsheet && spreadsheetPreview" :preview="spreadsheetPreview" />
          <DocumentTextPreview v-else-if="previewIsDocx && textPreview" :preview="textPreview" />
          <div v-else class="document-preview__empty">
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

    <form v-if="canUpload" class="upload-form" @submit.prevent="emit('upload')">
      <label><span>文件類型</span>
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
      <label class="upload-form__file">
        <span>選擇檔案</span>
        <input id="valuation-source-file" type="file" accept=".pdf,.xls,.xlsx,.png,.jpg,.jpeg,.docx" required @change="emit('chooseUpload', $event)" />
        <small>宗地個別因素清冊可直接使用既有 .xls／.xlsx；PDF 也可進行文字辨識。</small>
      </label>
      <button class="solid-button" type="submit" :disabled="uploading || !uploadFile">
        {{ uploading ? '上傳中…' : '上傳文件' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.document-workspace { display:grid; gap:12px; margin-top:16px; padding:14px; border:1px solid var(--app-line); border-radius:14px; background:rgba(255,255,255,.55); }
.document-workspace__heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.document-workspace__heading div { display:grid; gap:3px; }
.document-workspace__heading strong { color:var(--app-ink); }
.document-workspace__heading span { color:var(--app-muted); font-size:11px; }
.startup-documents { display:grid; gap:9px; padding:11px 12px; border:1px solid #d9e4ef; border-radius:11px; background:#f8fbfe; }
.startup-documents__heading { display:flex; align-items:baseline; justify-content:space-between; gap:12px; }
.startup-documents__heading strong { color:var(--app-ink); font-size:12px; }
.startup-documents__heading span { color:var(--app-muted); font-size:10px; }
.startup-documents__grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
.startup-documents__grid article { display:flex; min-width:0; align-items:flex-start; justify-content:space-between; gap:8px; padding:10px; border:1px solid #e0e7ef; border-radius:9px; background:#fff; }
.startup-documents__grid article > div { display:grid; gap:4px; min-width:0; }
.startup-documents__grid article strong { color:var(--app-ink); font-size:11px; }
.startup-documents__grid article span { color:var(--app-muted); font-size:9px; line-height:1.55; }
.startup-documents__grid article small { flex:0 0 auto; padding:4px 7px; border-radius:999px; color:#925421; background:#fff0df; font-size:9px; font-weight:850; white-space:nowrap; }
.startup-documents__grid article small[data-state="required"] { color:#a44334; background:#fff0ed; }
.startup-documents__grid article small[data-state="ready"] { color:#2f745b; background:#edf8f3; }
.document-ai-grid { display:grid; grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr); gap:14px; min-height:460px; }
.document-ai-grid__list { min-width:0; }
.document-list { display:grid; gap:7px; margin:0; padding:0; list-style:none; }
.document-list li { display:grid; grid-template-columns:minmax(0,1fr); align-items:stretch; gap:9px; min-width:0; padding:10px 11px; border:1px solid transparent; border-radius:10px; background:rgba(247,249,252,.84); }
.document-list li.is-selected { border-color:rgba(46,89,132,.36); background:#eef5fc; }
.document-list li div { display:grid; gap:2px; min-width:0; }
.document-list li strong { overflow:hidden; color:var(--app-ink); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.document-list li span { color:var(--app-muted); font-size:10px; }
.document-list__identity small { width:fit-content; margin-top:3px; padding:3px 7px; border-radius:999px; color:#52657a; background:#eef1f5; font-size:9px; font-weight:800; }
.document-list__identity small[data-ai-state="pending"] { color:#925421; background:#fff0df; }
.document-list__actions { display:flex !important; width:100%; min-width:0; align-items:center; flex-wrap:wrap; gap:6px !important; }
.document-list__analysis-form { display:flex; min-width:210px; flex:1 1 240px; align-items:center; gap:6px; color:var(--app-muted); font-size:10px; font-weight:800; }
.document-list__analysis-form > span { flex:0 0 auto; }
.document-list__analysis-form select,
.document-list__manage select { width:100%; min-width:0; min-height:36px; padding:6px 8px; border:1px solid var(--app-line); border-radius:7px; color:var(--app-ink); background:#fff; font-size:11px; }
.document-list__manage { display:grid !important; grid-template-columns:auto minmax(0,1fr) auto auto; flex:1 1 100%; width:100%; min-width:0; align-items:center; gap:6px !important; }
.document-list__manage label { color:var(--app-muted); font-size:10px; font-weight:800; }
.finding-action { justify-self:start; min-height:36px; margin-top:5px; padding:6px 11px; border:1px solid rgba(200,91,67,.26); border-radius:8px; color:var(--app-accent-deep); background:#fff; cursor:pointer; font-size:11px; font-weight:900; }
.document-list__actions .finding-action { margin-top:0; white-space:nowrap; }
.finding-action--primary { border-color:rgba(46,89,132,.34); color:#244d73; background:#edf4fb; }
.finding-action--danger { border-color:rgba(164,67,52,.28); color:#a44334; }
.upload-form { display:grid; grid-template-columns:180px minmax(0,1fr) auto; align-items:end; gap:10px; }
.upload-form label { display:grid; gap:5px; color:var(--app-ink-soft); font-size:11px; font-weight:800; }
.upload-form label small { color:var(--app-muted); font-size:9px; font-weight:500; line-height:1.45; }
.upload-form select,.upload-form input { min-height:44px; padding:8px 10px; border:1px solid var(--app-line); border-radius:9px; color:var(--app-ink); background:rgba(255,255,255,.82); }
.solid-button { min-height:44px; padding:10px 16px; border:1px solid var(--app-line); border-radius:9px; color:var(--app-ink-soft); background:var(--app-paper-strong); cursor:pointer; font-size:13px; font-weight:800; }
.solid-button:disabled { cursor:not-allowed; opacity:.55; }
.empty-copy { margin:0; color:var(--app-muted); font-size:13px; }
.document-preview { display:grid; grid-template-rows:auto minmax(340px,1fr) auto; min-width:0; overflow:hidden; border:1px solid #d8e1eb; border-radius:12px; background:#fff; }
.document-preview__heading { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:11px 13px; border-bottom:1px solid #e1e7ee; background:#f8fafc; }
.document-preview__heading > div { display:grid; gap:2px; min-width:0; }
.document-preview__heading strong { color:var(--app-ink); font-size:12px; }
.document-preview__heading span { overflow:hidden; color:var(--app-muted); font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.document-preview__body { display:grid; min-height:340px; place-items:center; overflow:hidden; background:#eef1f4; }
.document-preview__body iframe { width:100%; height:100%; min-height:460px; border:0; background:#fff; }
.document-preview__body img { display:block; max-width:100%; max-height:520px; object-fit:contain; }
.document-preview__empty { display:grid; gap:5px; max-width:300px; padding:26px; color:#6b798a; text-align:center; }
.document-preview__empty strong { color:#34495f; font-size:13px; }
.document-preview__empty span,.document-preview__message { color:#6b798a; font-size:11px; line-height:1.6; }
.document-preview__message { margin:0; padding:24px; text-align:center; }
.document-preview__evidence { display:grid; gap:6px; padding:11px 13px; border-top:1px solid #e1e7ee; background:#fff8ee; }
.document-preview__evidence strong { color:#8a531e; font-size:10px; }
.document-preview__evidence blockquote { margin:0; color:#3d4a58; font-size:11px; line-height:1.6; white-space:pre-wrap; }
@media (max-width:1100px){.document-ai-grid{grid-template-columns:1fr}.document-preview__body iframe{min-height:520px}}
@media (max-width:760px){.startup-documents__heading{align-items:flex-start;flex-direction:column}.startup-documents__grid{grid-template-columns:1fr}.upload-form{grid-template-columns:1fr}.document-list__actions{align-items:stretch}.document-list__analysis-form{min-width:0;align-items:stretch;flex-direction:column}.document-list__manage{grid-template-columns:1fr;align-items:stretch}.document-preview__heading{align-items:stretch;flex-direction:column}.solid-button{width:100%}}
</style>
