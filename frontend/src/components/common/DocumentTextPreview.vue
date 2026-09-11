<script setup lang="ts">
import type { DocumentTextPreviewDto } from '../../types/documentPreview'

defineProps<{
  preview: DocumentTextPreviewDto
}>()
</script>

<template>
  <div class="document-text-preview" data-testid="document-text-preview">
    <div class="document-text-preview__notice">
      <strong>DOCX 文字預覽</strong>
      <span>此處顯示可讀文字與表格內容，不還原 Word 原始版面。</span>
      <span v-if="preview.truncated">內容較長，目前僅顯示前段文字；完整內容請下載原始文件。</span>
    </div>
    <pre v-if="preview.text">{{ preview.text }}</pre>
    <p v-else class="document-text-preview__empty">此 DOCX 目前沒有可顯示的文字內容。</p>
  </div>
</template>

<style scoped>
.document-text-preview { display:grid; width:100%; min-width:0; gap:10px; align-self:stretch; }
.document-text-preview__notice { display:flex; flex-wrap:wrap; gap:5px 12px; width:100%; padding:10px 12px; border-bottom:1px solid var(--app-line); color:var(--app-muted); background:#f8fafc; font-size:10px; }
.document-text-preview__notice strong { color:var(--app-ink); }
.document-text-preview pre { box-sizing:border-box; width:100%; min-height:360px; max-height:560px; margin:0; padding:18px; overflow:auto; color:var(--app-ink-soft); background:#fff; font-family:var(--app-font-body); font-size:12px; line-height:1.75; white-space:pre-wrap; overflow-wrap:anywhere; }
.document-text-preview__empty { margin:0; padding:28px; color:var(--app-muted); background:#fff; text-align:center; font-size:12px; }
</style>
