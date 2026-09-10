<script setup lang="ts">
import type { FindingViewModel } from '../review.types'
defineProps<{ finding: FindingViewModel | null }>()
defineEmits<{ selectDocument: [documentId: string] }>()
</script>

<template>
  <section class="finding-panel solid-panel" aria-label="疑點內容">
    <template v-if="finding">
      <header>
        <div><span class="eyebrow">{{ finding.findingCode }}</span><h2>{{ finding.title }}</h2></div>
        <span class="badge">{{ finding.severityLabel }}</span>
      </header>
      <p>{{ finding.description }}</p>
      <dl class="evidence-list">
        <template v-if="finding.pageNumber"><dt>來源頁面</dt><dd>第 {{ finding.pageNumber }} 頁</dd></template>
        <template v-if="finding.reportedValue"><dt>申報值</dt><dd>{{ finding.reportedValue }}</dd></template>
        <template v-if="finding.reportedGrade"><dt>申報等級</dt><dd>{{ finding.reportedGrade }}</dd></template>
        <template v-if="finding.systemGrade"><dt>系統等級</dt><dd>{{ finding.systemGrade }}</dd></template>
        <template v-if="finding.reportedAdjustmentRate"><dt>申報調整率</dt><dd>{{ finding.reportedAdjustmentRate }}</dd></template>
        <template v-if="finding.systemAdjustmentRate"><dt>系統調整率</dt><dd>{{ finding.systemAdjustmentRate }}</dd></template>
      </dl>
      <section v-if="finding.aiReasoningSummary" class="ai-note"><strong>AI 說明</strong><p>{{ finding.aiReasoningSummary }}</p></section>
      <button v-if="finding.documentId" class="text-button" type="button" @click="$emit('selectDocument', finding.documentId)">查看來源文件</button>
    </template>
    <p v-else>請從左側選擇一項疑點。</p>
  </section>
</template>