<script setup lang="ts">
import type { HistoryDocumentModel } from '../history.types'

withDefaults(
  defineProps<{
    documents: HistoryDocumentModel[]
    busyDocumentId?: string | null
    errorByDocument?: Record<string, string>
  }>(),
  {
    busyDocumentId: null,
    errorByDocument: () => ({}),
  },
)

const emit = defineEmits<{
  download: [document: HistoryDocumentModel]
}>()

function fileSize(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '大小未知'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${Math.round(value / 102.4) / 10} KB`
  return `${Math.round(value / 104857.6) / 10} MB`
}
</script>

<template>
  <section class="document-list" aria-labelledby="history-documents-title">
    <div class="document-list__heading">
      <div>
        <p class="document-list__eyebrow">AUTHORIZED DOCUMENTS</p>
        <h2 id="history-documents-title">授權文件</h2>
      </div>
      <span class="document-list__count">{{ documents.length }} 份</span>
    </div>

    <p v-if="!documents.length" class="document-list__empty">目前沒有文件 metadata。</p>
    <ul v-else class="document-list__items">
      <li v-for="document in documents" :key="document.documentId" class="document-list__item">
        <div class="document-list__icon" aria-hidden="true">↗</div>
        <div class="document-list__copy">
          <strong>{{ document.fileName }}</strong>
          <span>{{ document.documentTypeLabel }} · {{ document.sourceModuleLabel }} · 第 {{ document.versionNo }} 版</span>
          <small>{{ document.contentTypeLabel }} · {{ fileSize(document.fileSizeBytes) }}</small>
          <p v-if="document.downloadAvailable === false" class="document-list__error" role="status">文件目前無法下載</p>
          <p v-if="errorByDocument[document.documentId]" class="document-list__error" role="alert">
            {{ errorByDocument[document.documentId] }}
          </p>
        </div>
        <button
          type="button"
          class="document-list__download"
          :data-testid="`history-download-${document.documentId}`"
          :disabled="busyDocumentId === document.documentId || document.downloadAvailable === false"
          :title="document.downloadAvailable === false ? '文件目前無法下載' : undefined"
          @click="emit('download', document)"
        >
          <template v-if="busyDocumentId === document.documentId">下載中…</template>
          <template v-else-if="errorByDocument[document.documentId]">再試一次</template>
          <template v-else-if="document.downloadAvailable === false">無法下載</template>
          <template v-else>下載文件</template>
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.document-list {
  padding: 20px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
}

.document-list__heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 15px;
}

.document-list__eyebrow {
  margin: 0 0 5px;
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .15em;
}

.document-list h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 24px;
}

.document-list__count {
  color: var(--app-muted);
  font-size: 12px;
}

.document-list__items {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.document-list__item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 13px;
  border: 1px solid #e5e9f0;
  border-radius: 10px;
  background: #fbfcfe;
}

.document-list__icon {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 10px;
  color: var(--app-blue);
  background: #e9f0f8;
  font-size: 19px;
  font-weight: 800;
}

.document-list__copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.document-list__copy strong {
  overflow: hidden;
  color: var(--app-ink);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-list__copy span,
.document-list__copy small {
  overflow-wrap: anywhere;
  color: var(--app-ink-soft);
  font-size: 11px;
}

.document-list__copy small { color: var(--app-muted); }

.document-list__error {
  margin: 4px 0 0;
  color: #ac3c37;
  font-size: 12px;
  font-weight: 700;
}

.document-list__download {
  min-width: 94px;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}

.document-list__download:hover:not(:disabled) {
  border-color: var(--app-accent);
  color: var(--app-accent-deep);
}

.document-list__download:disabled { cursor: not-allowed; opacity: .55; }

.document-list__empty {
  margin: 0;
  padding: 18px 0 4px;
  color: var(--app-muted);
  font-size: 13px;
}

@media (max-width: 640px) {
  .document-list__item { grid-template-columns: 36px minmax(0, 1fr); }
  .document-list__download { grid-column: 2; justify-self: start; }
}
</style>
