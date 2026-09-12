<script setup lang="ts">
import {
  PhArrowRight as ArrowRight,
  PhCheckCircle as CheckCircle,
  PhFileText as FileText,
  PhListChecks as ListChecks,
  PhShieldCheck as ShieldCheck,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'

const props = defineProps<{
  title: string
  stageLabel: string
  documentCount: number
  pendingCandidateCount?: number | null
  missingFieldCount?: number | null
  validationErrorCount?: number | null
  issueCount: number
  issueTitle?: string
  issueDetail?: string
}>()

const emit = defineEmits<{
  nextAction: []
}>()
</script>

<template>
  <section class="workflow-status" data-testid="valuation-workflow-guide" aria-labelledby="workflow-status-title">
    <div class="workflow-status__copy">
      <div class="workflow-status__title">
        <span class="workflow-status__title-icon" aria-hidden="true">
          <ListChecks :size="20" weight="duotone" />
        </span>
        <div>
          <p>目前進度</p>
          <h2 id="workflow-status-title">{{ props.title }}</h2>
        </div>
      </div>
      <span class="workflow-status__stage">{{ props.stageLabel }}</span>
    </div>

    <div class="workflow-status__stats">
      <span>
        <FileText :size="14" weight="duotone" aria-hidden="true" />
        來源文件 {{ props.documentCount }} 份
      </span>
      <span v-if="props.pendingCandidateCount !== null && props.pendingCandidateCount !== undefined">
        <WarningCircle v-if="props.pendingCandidateCount" :size="14" weight="fill" aria-hidden="true" />
        <CheckCircle v-else :size="14" weight="fill" aria-hidden="true" />
        辨識結果待確認 {{ props.pendingCandidateCount }} 筆
      </span>
      <span v-if="props.missingFieldCount !== null && props.missingFieldCount !== undefined">
        <WarningCircle v-if="props.missingFieldCount" :size="14" weight="fill" aria-hidden="true" />
        <CheckCircle v-else :size="14" weight="fill" aria-hidden="true" />
        比準地地價估計表缺欄位 {{ props.missingFieldCount }} 項
      </span>
      <span v-if="props.validationErrorCount !== null && props.validationErrorCount !== undefined">
        <WarningCircle v-if="props.validationErrorCount" :size="14" weight="fill" aria-hidden="true" />
        <ShieldCheck v-else :size="14" weight="fill" aria-hidden="true" />
        檢核錯誤 {{ props.validationErrorCount }} 項
      </span>
    </div>

    <div class="workflow-status__action">
      <span v-if="!props.issueCount" class="workflow-status__ready">
        <CheckCircle :size="15" weight="fill" aria-hidden="true" />
        目前沒有阻擋事項
      </span>
      <div v-else class="workflow-status__current-task" data-testid="workflow-current-task">
        <span class="workflow-status__current-task-icon" aria-hidden="true">
          <WarningCircle :size="16" weight="fill" />
        </span>
        <span class="workflow-status__current-task-copy">
          <small>目前要處理</small>
          <strong>{{ props.issueTitle || `尚有 ${props.issueCount} 項待處理` }}</strong>
          <span v-if="props.issueDetail">{{ props.issueDetail }}</span>
        </span>
        <button
          type="button"
          data-testid="workflow-next-action"
          @click="emit('nextAction')"
        >
          <span>前往處理</span>
          <ArrowRight :size="14" weight="bold" aria-hidden="true" />
        </button>
      </div>
    </div>
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

.workflow-status__title {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
}

.workflow-status__title-icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 8px;
  color: var(--app-accent-deep);
  background: #e8f1fa;
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
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 10px;
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: rgba(255, 255, 255, .82);
  font-size: 11px;
  font-weight: 800;
}

.workflow-status__stats span > svg { flex: 0 0 auto; color: #55738f; }

.workflow-status__action { flex: 0 1 420px; }

.workflow-status__ready {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 900;
  white-space: nowrap;
}

.workflow-status__ready {
  padding: 6px 10px;
  border: 1px solid #cfe4da;
  color: #2f7456;
  background: #f3f9f6;
}

.workflow-status__current-task {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  min-width: 280px;
  padding: 9px 10px;
  border: 1px solid #ead9b2;
  border-radius: 9px;
  background: #fffaf0;
}

.workflow-status__current-task-icon {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 999px;
  color: #8a6515;
  background: #fff1c9;
}

.workflow-status__current-task-copy { display: grid; gap: 2px; min-width: 0; }
.workflow-status__current-task-copy small { color: #8a6515; font-size: 9px; font-weight: 900; letter-spacing: .08em; }
.workflow-status__current-task-copy strong { color: var(--app-ink); font-size: 11px; line-height: 1.4; }
.workflow-status__current-task-copy > span { color: var(--app-muted); font-size: 9px; line-height: 1.45; }
.workflow-status__current-task button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 6px 10px;
  border: 1px solid #d4b56b;
  border-radius: 8px;
  color: #795713;
  background: #fff;
  cursor: pointer;
  font-size: 10px;
  font-weight: 900;
  white-space: nowrap;
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

  .workflow-status__action,
  .workflow-status__ready { width: 100%; }
  .workflow-status__current-task { min-width: 0; grid-template-columns: auto minmax(0, 1fr); }
  .workflow-status__current-task button { grid-column: 1 / -1; width: 100%; }
}
</style>
