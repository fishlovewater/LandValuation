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
</script>

<template>
  <div id="valuation-document-workspace" class="document-workspace" tabindex="-1">
    <div class="document-workspace__heading">
      <div>
        <strong>來源文件與 AI 辨識</strong>
        <span>先選文件預覽，再執行 AI / OCR 辨識。辨識結果不會直接改寫正式資料，仍需人工確認。</span>
      </div>
      <span>{{ documents.length }} 份</span>
    </div>

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
              <label v-if="canExtractDocument(document)" class="document-list__analysis-form">
                <span>檔名表單提示（不限制掃描範圍）</span>
                <select
                  :value="analysisFormValue(document.documentId)"
                  :data-testid="`document-analysis-form-${document.documentId}`"
                  :disabled="Boolean(extractionBusyDocumentId)"
                  @change="emit('updateAnalysisForm', document.documentId, ($event.target as HTMLSelectElement).value as FieldAnalysisFormCode)"
                >
                  <option v-for="code in analysisFormCodes" :key="code" :value="code">
                    {{ formDisplayName(code) }}（{{ code }}）
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
                {{ extractionBusyDocumentId === document.documentId ? '六表 AI 辨識中…' : documentCandidateCount(document.documentId) ? '重新六表 AI 辨識' : '開始六表 AI 辨識' }}
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
        <p v-else class="empty-copy">尚未上傳案件來源文件。請先選擇文件類型並上傳。</p>
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
          <strong>AI 對應原文{{ selectedCandidate.source_page ? ` · 第 ${selectedCandidate.source_page} 頁` : '' }}</strong>
          <blockquote>{{ selectedCandidate.source_text }}</blockquote>
        </div>
      </section>
    </div>

    <form v-if="canUpload" class="upload-form" @submit.prevent="emit('upload')">
      <label><span>文件類型</span>
        <select :value="uploadCategory" @change="emit('updateUploadCategory', ($event.target as HTMLSelectElement).value as DocumentCategory)">
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
      <label class="upload-form__file"><span>選擇檔案</span><input id="valuation-source-file" type="file" required @change="emit('chooseUpload', $event)" /></label>
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
@media (max-width:760px){.upload-form{grid-template-columns:1fr}.document-list__actions{align-items:stretch}.document-list__analysis-form{min-width:0;align-items:stretch;flex-direction:column}.document-list__manage{grid-template-columns:1fr;align-items:stretch}.document-preview__heading{align-items:stretch;flex-direction:column}.solid-button{width:100%}}
</style>
