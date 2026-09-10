<script setup lang="ts">
import type { AssistantCitationModel } from '../assistant.types'

defineProps<{
  citation: AssistantCitationModel
  index: number
}>()

function pageLabel(citation: AssistantCitationModel): string {
  if (citation.pageStart !== null && citation.pageEnd !== null) {
    return citation.pageStart === citation.pageEnd
      ? `第 ${citation.pageStart} 頁`
      : `第 ${citation.pageStart}–${citation.pageEnd} 頁`
  }
  if (citation.pageStart !== null) return `第 ${citation.pageStart} 頁`
  if (citation.pageEnd !== null) return `第 ${citation.pageEnd} 頁`
  return '頁碼未提供'
}
</script>

<template>
  <section class="citation-panel" :data-testid="`assistant-citation-panel-${index}`" aria-label="引用來源">
    <div class="citation-panel__heading">
      <span class="citation-panel__eyebrow">SOURCE {{ index }}</span>
      <h3>{{ citation.documentName || '文件名稱未提供' }}</h3>
    </div>
    <dl class="citation-panel__facts">
      <div>
        <dt>文件編號</dt>
        <dd>{{ citation.documentCode || '未提供' }}</dd>
      </div>
      <div>
        <dt>版本</dt>
        <dd>{{ citation.versionNo ?? '未提供' }}</dd>
      </div>
      <div>
        <dt>條文</dt>
        <dd>{{ citation.articleNo || '條文未提供' }}</dd>
      </div>
      <div>
        <dt>頁碼</dt>
        <dd>{{ pageLabel(citation) }}</dd>
      </div>
      <div>
        <dt>來源位置</dt>
        <dd>{{ citation.sectionTitle || citation.articleNo || pageLabel(citation) }}</dd>
      </div>
    </dl>
    <blockquote v-if="citation.supportingQuote || citation.quotedText" class="citation-panel__quote">
      {{ citation.supportingQuote || citation.quotedText }}
    </blockquote>
    <p v-if="citation.supportedClaim" class="citation-panel__claim">
      支持主張：{{ citation.supportedClaim }}
    </p>
  </section>
</template>

<style scoped>
.citation-panel {
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
  box-shadow: var(--app-shadow-soft);
}

.citation-panel__heading {
  display: grid;
  gap: 5px;
}

.citation-panel__eyebrow {
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.citation-panel h3 {
  margin: 0;
  color: var(--app-ink);
  font-size: 16px;
  line-height: 1.45;
}

.citation-panel__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
  margin: 0;
}

.citation-panel__facts div {
  min-width: 0;
}

.citation-panel__facts dt {
  color: var(--app-muted);
  font-size: 11px;
}

.citation-panel__facts dd {
  margin: 3px 0 0;
  color: var(--app-ink-soft);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.citation-panel__quote {
  margin: 0;
  padding: 12px 14px;
  border-left: 3px solid var(--app-accent);
  color: var(--app-ink);
  background: #fffaf7;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.citation-panel__claim {
  margin: 0;
  color: var(--app-ink-soft);
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 560px) {
  .citation-panel__facts { grid-template-columns: 1fr; }
}
</style>
