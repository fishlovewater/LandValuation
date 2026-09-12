<script setup lang="ts">
import { PhArrowRight as ArrowRight } from '@phosphor-icons/vue'

const props = defineProps<{
  title: string
  stageLabel: string
  documentCount: number
  pendingCandidateCount?: number | null
  missingFieldCount?: number | null
  validationErrorCount?: number | null
  issueCount: number
}>()

const emit = defineEmits<{
  nextAction: []
}>()
</script>

<template>
  <section class="workflow-status" data-testid="valuation-workflow-guide" aria-labelledby="workflow-status-title">
    <div class="workflow-status__copy">
      <div>
        <p>目前進度</p>
        <h2 id="workflow-status-title">{{ props.title }}</h2>
      </div>
      <span class="workflow-status__stage">{{ props.stageLabel }}</span>
    </div>

    <div class="workflow-status__stats">
      <span>來源文件 {{ props.documentCount }} 份</span>
      <span v-if="props.pendingCandidateCount !== null && props.pendingCandidateCount !== undefined">
        辨識結果待確認 {{ props.pendingCandidateCount }} 筆
      </span>
      <span v-if="props.missingFieldCount !== null && props.missingFieldCount !== undefined">
        比準地地價估計表缺欄位 {{ props.missingFieldCount }} 項
      </span>
      <span v-if="props.validationErrorCount !== null && props.validationErrorCount !== undefined">
        檢核錯誤 {{ props.validationErrorCount }} 項
      </span>
    </div>

    <button
      v-if="props.issueCount"
      type="button"
      data-testid="workflow-next-action"
      @click="emit('nextAction')"
    >
      <span>查看第一個待處理項目</span>
      <ArrowRight :size="14" weight="bold" aria-hidden="true" />
    </button>
  </section>
</template>

<style scoped>
.workflow-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid #d9e4ef;
  border-radius: 12px;
  background: #f7fbff;
}

.workflow-status__copy {
  display: flex;
  min-width: 190px;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.workflow-status__copy p {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}

.workflow-status__copy h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 17px;
  font-weight: 600;
}

.workflow-status__stage {
  padding: 7px 11px;
  border-radius: var(--app-radius-pill);
  color: #2e5984;
  background: #edf4fb;
  font-size: 11px;
  font-weight: 900;
  white-space: nowrap;
}

.workflow-status__stats {
  display: flex;
  flex: 1 1 auto;
  flex-wrap: wrap;
  gap: 8px;
}

.workflow-status__stats span {
  padding: 7px 10px;
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: rgba(255, 255, 255, .82);
  font-size: 11px;
  font-weight: 800;
}

.workflow-status > button {
  display: inline-flex;
  min-height: 36px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 11px;
  border: 1px solid rgba(200, 91, 67, .26);
  border-radius: 8px;
  color: var(--app-accent-deep);
  background: #fff;
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

@media (max-width: 760px) {
  .workflow-status {
    align-items: stretch;
    flex-direction: column;
  }

  .workflow-status__copy {
    min-width: 0;
    flex-direction: column;
  }

  .workflow-status > button { width: 100%; }
}
</style>
