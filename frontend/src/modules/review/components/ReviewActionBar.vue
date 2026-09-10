<script setup lang="ts">
import { computed } from 'vue'
import GlassButton from '../../../components/glass/GlassButton.vue'
import type { GeneratedReportDto } from '../review.types'

const props = withDefaults(
  defineProps<{
    canDecide?: boolean
    canFinalize?: boolean
    canExecute?: boolean
    canGenerateReport?: boolean
    canRequestCorrection?: boolean
    canSendCorrection?: boolean
    canRecheckCorrection?: boolean
    correctionStatus?: string | null
    correctionActionReason?: string
    reviewStatusCode?: string
    unresolvedFindingCount?: number
    latestRunId?: string | null
    reportDocument?: GeneratedReportDto | null
    reportActionReason?: string
    finalizeActionReason?: string
    busy?: boolean
  }>(),
  {
    canDecide: false,
    canFinalize: false,
    canExecute: false,
    canGenerateReport: false,
    canRequestCorrection: false,
    canSendCorrection: false,
    canRecheckCorrection: false,
    correctionStatus: null,
    correctionActionReason: '請先完成所有疑點判定；至少一項確認為需修正後，才能送出修正通知。',
    reviewStatusCode: '',
    unresolvedFindingCount: 0,
    latestRunId: null,
    reportDocument: null,
    reportActionReason: '案件完成且最新檢核完成後，才可產生審查報告。',
    finalizeActionReason: '最新檢核完成且所有阻擋項目處理後，才可完成審查。',
    busy: false,
  },
)

const emit = defineEmits<{
  'finalize-request': []
  'correction-request': []
  'send-correction': []
  'recheck-correction': []
  'generate-report': []
  'open-result': []
}>()

const finalState = computed(() => ['APPROVED', 'REVIEW_COMPLETED'].includes(props.reviewStatusCode))
</script>

<template>
  <div class="review-action-bar" data-testid="review-action-bar">
    <div class="review-action-bar__status">
      <span>目前狀態</span>
      <strong>{{ finalState ? '已完成審查' : '可接續處理' }}</strong>
      <small v-if="unresolvedFindingCount > 0">尚有 {{ unresolvedFindingCount }} 個未處理疑點</small>
    </div>
    <div class="review-action-bar__actions">
      <GlassButton
        v-if="!correctionStatus || correctionStatus === 'RECHECKED'"
        data-testid="request-correction"
        :disabled="!canRequestCorrection || busy || finalState"
        :title="correctionActionReason"
        @click="emit('correction-request')"
      >
        要求修正
      </GlassButton>
      <GlassButton
        v-else-if="correctionStatus === 'DRAFT'"
        data-testid="send-correction"
        :disabled="!canSendCorrection || busy"
        :title="correctionActionReason"
        @click="emit('send-correction')"
      >
        送出修正通知
      </GlassButton>
      <GlassButton
        v-else-if="correctionStatus === 'SENT'"
        data-testid="awaiting-correction"
        :disabled="true"
        title="已退回估價端，等待較新的正式版本重新送審。"
      >
        等待補正回件
      </GlassButton>
      <GlassButton
        v-else-if="correctionStatus === 'RESUBMITTED'"
        data-testid="recheck-correction"
        :disabled="!canRecheckCorrection || busy"
        :title="correctionActionReason"
        @click="emit('recheck-correction')"
      >
        新版重檢
      </GlassButton>
      <GlassButton
        v-else-if="correctionStatus === 'RECHECKING'"
        data-testid="rechecking-correction"
        :disabled="true"
      >
        新版重檢中
      </GlassButton>
      <GlassButton
        data-testid="finalize-review"
        variant="accent"
        :disabled="!canFinalize || busy || finalState"
        :title="finalState ? '案件已完成審查。' : finalizeActionReason"
        @click="emit('finalize-request')"
      >
        完成審查
      </GlassButton>
      <GlassButton
        v-if="latestRunId"
        data-testid="generate-review-report"
        :disabled="!canGenerateReport || busy"
        :title="reportActionReason"
        @click="emit('generate-report')"
      >
        產生審查報告
      </GlassButton>
      <GlassButton
        v-if="reportDocument"
        data-testid="open-review-result"
        :disabled="busy"
        @click="emit('open-result')"
      >
        查看報告
      </GlassButton>
      <small v-if="latestRunId && !canGenerateReport" class="review-action-bar__hint" data-testid="report-action-reason">
        {{ reportActionReason }}
      </small>
    </div>
  </div>
</template>

<style scoped>
.review-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 18px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
}

.review-action-bar__status { display: grid; gap: 3px; color: var(--app-muted); font-size: 11px; }
.review-action-bar__status strong { color: var(--app-ink); font-size: 14px; }
.review-action-bar__status small { color: #9b3f35; font-size: 11px; }
.review-action-bar__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.review-action-bar__hint { align-self: center; max-width: 250px; color: var(--app-muted); font-size: 11px; line-height: 1.5; }
.review-action-bar :deep(.lg-btn) { min-height: 42px; padding-inline: 13px; font-size: 12px; }

@media (max-width: 980px) {
  .review-action-bar { align-items: flex-start; flex-direction: column; }
  .review-action-bar__actions { justify-content: flex-start; }
}

@media (max-width: 640px) {
  .review-action-bar__actions { width: 100%; }
  .review-action-bar :deep(.lg-btn) { flex: 1 1 calc(50% - 8px); }
}
</style>
