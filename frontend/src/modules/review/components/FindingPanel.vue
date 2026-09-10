<script setup lang="ts">
import { ref } from 'vue'
import type { FindingViewModel } from '../review.types'
import type { FindingTriageDecision } from '../review.types'
defineProps<{ finding: FindingViewModel | null; canDecide?: boolean; busy?: boolean }>()
const emit = defineEmits<{
  selectDocument: [documentId: string]
  requestDecision: [payload: { decision: FindingTriageDecision; reason: string }]
}>()
const decision = ref<FindingTriageDecision>('CONFIRMED_ISSUE')
const reason = ref('')
function submitDecision() {
  const trimmed = reason.value.trim()
  if (!trimmed) return
  emit('requestDecision', { decision: decision.value, reason: trimmed })
}
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
      <form v-if="canDecide" class="decision-form" @submit.prevent="submitDecision">
        <label>人工判定<select v-model="decision"><option value="CONFIRMED_ISSUE">確認疑點</option><option value="DISMISSED_FALSE_POSITIVE">排除誤報</option><option value="EXPERT_REVIEW">送專家審查</option></select></label>
        <label>判定理由<textarea v-model="reason" required maxlength="2000" rows="4" /></label>
        <button class="primary-button" type="submit" :disabled="busy || !reason.trim()">{{ busy ? '送出中…' : '送出判定' }}</button>
      </form>
    </template>
    <p v-else>請從左側選擇一項疑點。</p>
  </section>
</template>