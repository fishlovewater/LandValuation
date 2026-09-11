<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import { reviewApi, safeReviewErrorMessage } from '../review.api'
import type { ReviewDocumentModel } from '../review.types'

const props = defineProps<{
  reviewId: string
  document: ReviewDocumentModel | null
  pageNumber?: number | null
  fieldPath?: string | null
}>()

const loading = ref(false)
const error = ref('')
const previewUrl = ref('')
let requestSerial = 0
let loadedDocumentKey = ''

const safePageNumber = computed(() => {
  const page = Number(props.pageNumber)
  return Number.isInteger(page) && page > 0 ? page : null
})
const previewSource = computed(() => {
  if (!previewUrl.value) return ''
  return safePageNumber.value ? `${previewUrl.value}#page=${safePageNumber.value}` : previewUrl.value
})

function clearPreview(): void {
  if (previewUrl.value && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

async function loadEvidence(): Promise<void> {
  const document = props.document
  const serial = ++requestSerial
  const documentKey = document ? `${props.reviewId}:${document.documentId}` : ''
  if (documentKey && documentKey === loadedDocumentKey && !error.value) return
  clearPreview()
  error.value = ''
  if (!document) {
    loadedDocumentKey = ''
    return
  }
  loading.value = true
  try {
    const blob = await reviewApi.getDocumentContent(props.reviewId, document.documentId)
    if (serial !== requestSerial) return
    loadedDocumentKey = documentKey
    if (typeof URL.createObjectURL === 'function') previewUrl.value = URL.createObjectURL(blob)
  } catch (caught: unknown) {
    if (serial === requestSerial) error.value = safeReviewErrorMessage(caught)
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

watch(() => [props.reviewId, props.document?.documentId], loadEvidence, { immediate: true })

onBeforeUnmount(clearPreview)
</script>

<template>
  <section class="evidence-viewer" data-testid="evidence-viewer" aria-label="證據與表單">
    <header class="evidence-viewer__header">
      <div>
        <p class="evidence-viewer__eyebrow">來源文件</p>
        <h2>證據／表單檢視</h2>
      </div>
      <span v-if="document" class="evidence-viewer__version">第 {{ document.versionNo }} 版</span>
    </header>

    <LoadingSkeleton v-if="loading" :rows="5" label="證據載入中" />
    <ErrorState v-else-if="error" :message="error" @retry="loadEvidence" />
    <EmptyState
      v-else-if="!document"
      title="尚未選取證據"
      description="選取右側疑點後，這裡會開啟同一份授權文件。"
    />
    <div v-else class="evidence-viewer__surface">
      <div class="evidence-viewer__meta">
        <strong>{{ document.filename }}</strong>
        <span>{{ document.documentTypeLabel }}</span>
        <span>{{ document.mimeTypeLabel }}</span>
        <span v-if="pageNumber">第 {{ pageNumber }} 頁</span>
        <span v-if="fieldPath">已定位至相關欄位</span>
      </div>
      <object
        v-if="previewSource && document.mimeType === 'application/pdf'"
        :key="previewSource"
        data-testid="evidence-pdf"
        class="evidence-viewer__pdf"
        :data="previewSource"
        type="application/pdf"
        :aria-label="`${document.filename} PDF 預覽`"
      >
        <p>瀏覽器無法內嵌此 PDF，請使用文件下載功能查看完整內容。</p>
      </object>
      <div v-else class="evidence-viewer__form" role="status">
        <div class="evidence-viewer__form-mark" aria-hidden="true">PDF</div>
        <p>文件已可讀取，但目前無法直接在這裡預覽。</p>
        <small>請使用文件下載功能查看完整內容。</small>
      </div>
      <details class="evidence-viewer__technical">
        <summary>查看文件技術細節</summary>
        <dl>
          <div><dt>文件類型</dt><dd>{{ document.documentType }}</dd></div>
          <div><dt>檔案格式</dt><dd>{{ document.mimeType }}</dd></div>
          <div v-if="fieldPath"><dt>技術欄位路徑</dt><dd>{{ fieldPath }}</dd></div>
        </dl>
      </details>
    </div>
  </section>
</template>

<style scoped>
.evidence-viewer {
  display: grid;
  min-width: 0;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-paper-strong);
  box-shadow: var(--app-shadow-soft);
}

.evidence-viewer__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.evidence-viewer__eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.evidence-viewer h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 23px;
}

.evidence-viewer__version {
  padding: 6px 10px;
  border-radius: var(--app-radius-pill);
  color: var(--app-blue);
  background: #edf4fb;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}

.evidence-viewer__surface {
  display: grid;
  min-height: 520px;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid #cbd5e3;
  border-radius: 8px;
  background: #f5f7fa;
}

.evidence-viewer__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 12px 14px;
  border-bottom: 1px solid #cbd5e3;
  color: var(--app-ink-soft);
  background: #fff;
  font-size: 12px;
}

.evidence-viewer__meta strong { color: var(--app-ink); }
.evidence-viewer__technical { padding: 0 14px 14px; color: var(--app-muted); font-size: 11px; }
.evidence-viewer__technical summary { cursor: pointer; font-weight: 800; }
.evidence-viewer__technical dl { display: grid; gap: 5px; margin: 8px 0 0; }
.evidence-viewer__technical dl div { display: flex; justify-content: space-between; gap: 14px; }
.evidence-viewer__technical dt { font-weight: 700; }
.evidence-viewer__technical dd { margin: 0; color: var(--app-ink-soft); overflow-wrap: anywhere; text-align: right; }

.evidence-viewer__pdf {
  width: 100%;
  min-height: 470px;
  border: 0;
  background: #e6ebf2;
}

.evidence-viewer__form {
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 12px;
  padding: 40px;
  color: var(--app-ink-soft);
  text-align: center;
}

.evidence-viewer__form p,
.evidence-viewer__form small { margin: 0; }

.evidence-viewer__form-mark {
  display: grid;
  width: 76px;
  height: 92px;
  place-items: center;
  border: 1px solid #c4cfdd;
  border-radius: 8px;
  color: var(--app-accent-deep);
  background: #fff;
  box-shadow: 0 7px 16px rgba(45, 63, 90, 0.08);
  font-size: 12px;
  font-weight: 900;
}

@media (max-width: 640px) {
  .evidence-viewer { padding: 14px; }
  .evidence-viewer__surface { min-height: 410px; }
  .evidence-viewer__pdf { min-height: 360px; }
}
</style>
