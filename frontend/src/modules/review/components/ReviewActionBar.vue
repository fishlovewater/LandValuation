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
    caseSourceCode?: string
    correctionActionReason?: string
    reviewStatusCode?: string
    totalFindingCount?: number
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
    caseSourceCode: 'PLATFORM',
    correctionActionReason: '請先完成所有疑點判定；至少一項確認為需修正後，才能送出修正通知。',
    reviewStatusCode: '',
    totalFindingCount: 0,
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
const externalCase = computed(() => props.caseSourceCode === 'EXTERNAL')
const requestCorrectionLabel = computed(() => externalCase.value ? '建立修正通知' : '要求修正')
const sendCorrectionLabel = computed(() => externalCase.value ? '確認已對外通知' : '送出修正通知')
const awaitingCorrectionLabel = computed(() => externalCase.value ? '等待外部回件' : '等待補正回件')
const awaitingCorrectionTitle = computed(() => externalCase.value
  ? '修正通知已記錄為對外通知，等待外部廠商回傳新版文件。'
  : '已退回估價端，等待較新的正式版本重新送審。')
const correctionActionIsPrimary = computed(() => ['DRAFT', 'RESUBMITTED'].includes(props.correctionStatus ?? ''))
const finalizeIsPrimary = computed(() => !finalState.value && !correctionActionIsPrimary.value)
const resolvedFindingCount = computed(() => Math.max(0, props.totalFindingCount - props.unresolvedFindingCount))
const findingProgress = computed(() => props.totalFindingCount > 0
  ? Math.round((resolvedFindingCount.value / props.totalFindingCount) * 100)
  : 100)
</script>

<template>
  <div class="review-action-bar" data-testid="review-action-bar">
    <div class="review-action-bar__status">
      <span>目前狀態</span>
      <strong>{{ finalState ? '已完成審查' : '可接續處理' }}</strong>
      <div v-if="totalFindingCount > 0" class="review-action-bar__progress-copy">
        <small>疑點已處理 {{ resolvedFindingCount }} / {{ totalFindingCount }}</small>
        <small v-if="unresolvedFindingCount > 0">尚有 {{ unresolvedFindingCount }} 個未處理</small>
      </div>
      <div
        v-if="totalFindingCount > 0"
        class="review-action-bar__progress"
        role="progressbar"
        aria-label="疑點處理進度"
        :aria-valuenow="resolvedFindingCount"
        aria-valuemin="0"
        :aria-valuemax="totalFindingCount"
      >
        <span :style="{ width: `${findingProgress}%` }" />
      </div>
    </div>
    <div class="review-action-bar__actions">
      <GlassButton
        v-if="!correctionStatus || correctionStatus === 'RECHECKED'"
        data-testid="request-correction"
        :disabled="!canRequestCorrection || busy || finalState"
        :title="correctionActionReason"
        @click="emit('correction-request')"
      >
        {{ requestCorrectionLabel }}
      </GlassButton>
      <GlassButton
        v-else-if="correctionStatus === 'DRAFT'"
        variant="accent"
        data-testid="send-correction"
        :disabled="!canSendCorrection || busy"
        :title="correctionActionReason"
        @click="emit('send-correction')"
      >
        {{ sendCorrectionLabel }}
      </GlassButton>
      <GlassButton
        v-else-if="correctionStatus === 'SENT'"
        data-testid="awaiting-correction"
        :disabled="true"
        :title="awaitingCorrectionTitle"
      >
        {{ awaitingCorrectionLabel }}
      </GlassButton>
      <GlassButton
        v-else-if="correctionStatus === 'RESUBMITTED'"
        variant="accent"
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
        :variant="finalizeIsPrimary ? 'accent' : 'default'"
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
.review-action-bar__progress-copy { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.review-action-bar__progress-copy small:first-child { color: var(--app-ink-soft); font-weight: 800; }
.review-action-bar__progress { width: min(220px, 38vw); height: 5px; overflow: hidden; border-radius: 999px; background: #e9edf2; }
.review-action-bar__progress > span { display: block; height: 100%; border-radius: inherit; background: var(--app-green); transition: width 160ms ease; }
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
