<script setup lang="ts">
import { computed } from 'vue'
import type { HistoryDocumentModel } from '../history.types'

const props = withDefaults(
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

interface DocumentVersionGroup {
  key: string
  current: HistoryDocumentModel
  history: HistoryDocumentModel[]
}

interface DocumentSourceGroup {
  key: HistoryDocumentModel['sourceModule']
  label: string
  documents: DocumentVersionGroup[]
}

const sourceGroups = computed<DocumentSourceGroup[]>(() => {
  const sourceOrder: HistoryDocumentModel['sourceModule'][] = ['valuation', 'review']

  return sourceOrder.flatMap((sourceModule) => {
    const sourceDocuments = props.documents.filter((document) => document.sourceModule === sourceModule)
    if (!sourceDocuments.length) return []

    const grouped = new Map<string, HistoryDocumentModel[]>()
    sourceDocuments.forEach((document) => {
      const key = document.documentGroupId || `${document.documentType}:${document.fileName}`
      grouped.set(key, [...(grouped.get(key) ?? []), document])
    })

    const documents = [...grouped.entries()].map(([key, versions]) => {
      const sorted = [...versions].sort((left, right) => right.versionNo - left.versionNo)
      const current = sorted.find((document) => document.isActive) ?? sorted[0]!
      return {
        key,
        current,
        history: sorted.filter((document) => document.documentId !== current.documentId),
      }
    })

    return [{
      key: sourceModule,
      label: sourceDocuments[0]?.sourceModuleLabel ?? (sourceModule === 'valuation' ? '估價作業' : '智慧審查'),
      documents,
    }]
  })
})

const documentSummary = computed(() => {
  const currentCount = sourceGroups.value.reduce((sum, source) => sum + source.documents.length, 0)
  const historyCount = sourceGroups.value.reduce(
    (sum, source) => sum + source.documents.reduce((groupSum, group) => groupSum + group.history.length, 0),
    0,
  )
  return historyCount
    ? `${currentCount} 份目前文件 · ${historyCount} 個歷史版本`
    : `${currentCount} 份目前文件`
})

const emit = defineEmits<{
  download: [document: HistoryDocumentModel]
  preview: [document: HistoryDocumentModel]
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
        <p class="document-list__eyebrow">文件查看與下載</p>
        <h2 id="history-documents-title">案件文件</h2>
        <p class="document-list__description">可先預覽內容，或直接下載目前帳號有權查看的文件。</p>
      </div>
      <span class="document-list__count">{{ documentSummary }}</span>
    </div>

    <p v-if="!documents.length" class="document-list__empty">目前沒有可查看的案件文件。</p>
    <div v-else class="document-list__sources">
      <section v-for="source in sourceGroups" :key="source.key" class="document-list__source">
        <div class="document-list__source-heading">
          <strong>{{ source.label }}文件</strong>
          <span>{{ source.documents.length }} 份目前文件</span>
        </div>

        <ul class="document-list__items">
          <li v-for="group in source.documents" :key="group.key" class="document-list__group">
            <div class="document-list__item">
              <div class="document-list__icon" aria-hidden="true">↗</div>
              <div class="document-list__copy">
                <div class="document-list__title-line">
                  <strong>{{ group.current.fileName }}</strong>
                  <span class="document-list__current-badge">目前版本</span>
                </div>
                <span>{{ group.current.documentTypeLabel }} · 第 {{ group.current.versionNo }} 版</span>
                <small>{{ group.current.contentTypeLabel }} · {{ fileSize(group.current.fileSizeBytes) }}</small>
                <p v-if="group.current.downloadAvailable === false" class="document-list__error" role="status">文件目前無法下載</p>
                <p v-if="errorByDocument[group.current.documentId]" class="document-list__error" role="alert">
                  {{ errorByDocument[group.current.documentId] }}
                </p>
              </div>
              <div class="document-list__actions">
                <button
                  type="button"
                  class="document-list__preview"
                  :data-testid="`history-preview-${group.current.documentId}`"
                  :disabled="busyDocumentId === group.current.documentId || group.current.downloadAvailable === false"
                  :title="group.current.downloadAvailable === false ? '文件目前無法讀取' : undefined"
                  @click="emit('preview', group.current)"
                >預覽</button>
                <button
                  type="button"
                  class="document-list__download"
                  :data-testid="`history-download-${group.current.documentId}`"
                  :disabled="busyDocumentId === group.current.documentId || group.current.downloadAvailable === false"
                  :title="group.current.downloadAvailable === false ? '文件目前無法下載' : undefined"
                  @click="emit('download', group.current)"
                >
                  <template v-if="busyDocumentId === group.current.documentId">處理中…</template>
                  <template v-else-if="errorByDocument[group.current.documentId]">再試一次</template>
                  <template v-else-if="group.current.downloadAvailable === false">無法下載</template>
                  <template v-else>下載</template>
                </button>
              </div>
            </div>

            <details v-if="group.history.length" class="document-list__versions">
              <summary>歷史版本 {{ group.history.length }} 個</summary>
              <ul>
                <li v-for="version in group.history" :key="version.documentId">
                  <div>
                    <strong>第 {{ version.versionNo }} 版</strong>
                    <span>{{ version.fileName }} · {{ fileSize(version.fileSizeBytes) }}</span>
                  </div>
                  <div class="document-list__version-actions">
                    <button
                      type="button"
                      :data-testid="`history-preview-${version.documentId}`"
                      :disabled="busyDocumentId === version.documentId || version.downloadAvailable === false"
                      @click="emit('preview', version)"
                    >預覽</button>
                    <button
                      type="button"
                      :data-testid="`history-download-${version.documentId}`"
                      :disabled="busyDocumentId === version.documentId || version.downloadAvailable === false"
                      @click="emit('download', version)"
                    >下載</button>
                  </div>
                </li>
              </ul>
            </details>
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>

<style scoped>
.document-list {
  padding: 18px;
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
  font-size: 22px;
}

.document-list__description { margin:5px 0 0; color:var(--app-muted); font-size:10px; line-height:1.5; }

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

.document-list__sources { display:grid; gap:16px; }
.document-list__source { display:grid; gap:8px; }
.document-list__source-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:0 2px; }
.document-list__source-heading strong { color:var(--app-ink-soft); font-size:11px; }
.document-list__source-heading span { color:var(--app-muted); font-size:9px; }
.document-list__group { display:grid; gap:7px; }

.document-list__item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
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

.document-list__title-line { display:flex; min-width:0; align-items:center; gap:7px; }
.document-list__title-line > strong { min-width:0; }
.document-list__current-badge { flex:0 0 auto; padding:2px 6px; border-radius:999px; color:#276345 !important; background:#eef7f2; font-size:8px !important; font-weight:900; }

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

.document-list__actions { display:flex; align-items:center; gap:7px; }
.document-list__download,
.document-list__preview {
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

.document-list__preview { min-width:70px; color:var(--app-blue); }
.document-list__download { border-color:var(--app-accent); color:#fff; background:var(--app-accent); }
.document-list__download:hover:not(:disabled),
.document-list__preview:hover:not(:disabled) {
  border-color: var(--app-accent);
  color: var(--app-accent-deep);
}
.document-list__download:hover:not(:disabled) { color:#fff; background:var(--app-accent-deep); }

.document-list__download:disabled,
.document-list__preview:disabled { cursor: not-allowed; opacity: .55; }

.document-list__versions { margin-left:48px; padding:8px 10px; border:1px solid #e5e9f0; border-radius:8px; background:rgba(248,250,252,.7); }
.document-list__versions summary { color:var(--app-ink-soft); cursor:pointer; font-size:10px; font-weight:800; }
.document-list__versions ul { display:grid; gap:6px; margin:8px 0 0; padding:0; list-style:none; }
.document-list__versions li { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:7px 8px; border-radius:7px; background:#fff; }
.document-list__versions li > div:first-child { display:grid; gap:2px; min-width:0; }
.document-list__versions strong { color:var(--app-ink); font-size:10px; }
.document-list__versions span { overflow:hidden; color:var(--app-muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.document-list__version-actions { display:flex; gap:5px; }
.document-list__version-actions button { min-height:34px; padding:5px 8px; border:1px solid var(--app-line); border-radius:6px; color:var(--app-ink-soft); background:#fff; cursor:pointer; font-size:10px; font-weight:800; }
.document-list__version-actions button:hover:not(:disabled) { border-color:var(--app-accent); color:var(--app-accent-deep); }
.document-list__version-actions button:disabled { cursor:not-allowed; opacity:.55; }

.document-list__empty {
  margin: 0;
  padding: 18px 0 4px;
  color: var(--app-muted);
  font-size: 13px;
}

@media (max-width: 640px) {
  .document-list__item { grid-template-columns: 36px minmax(0, 1fr); }
  .document-list__actions { grid-column: 2; justify-self: start; }
  .document-list__versions { margin-left:0; }
  .document-list__versions li { align-items:flex-start; flex-direction:column; }
}
</style>
