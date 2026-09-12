<script setup lang="ts">
import {
  PhCheckCircle as CheckCircle,
  PhPaperPlaneTilt as PaperPlaneTilt,
} from '@phosphor-icons/vue'
import { statusLabel } from '../../../utils/enumLabels'
import { formatDateZhTw } from '../../../utils/formatters'
import type { SubmissionModel } from '../valuation.types'

defineProps<{
  submission: SubmissionModel | null
  readinessMessage: string
  canSubmit: boolean
  submitting: boolean
}>()

const emit = defineEmits<{
  submit: []
}>()
</script>

<template>
  <section class="submission-bar" aria-label="送審操作">
    <div class="submission-bar__copy">
      <strong>{{ submission ? '案件已送出審查' : readinessMessage }}</strong>
      <p v-if="submission">送審時間：{{ formatDateZhTw(submission.submittedAt) }}</p>
      <p v-else>完成必要檢核與完整送審 PDF 後即可送出審查。</p>
    </div>

    <button
      v-if="!submission"
      class="submission-bar__submit"
      type="button"
      data-testid="submit-for-review"
      :disabled="!canSubmit || submitting"
      @click="emit('submit')"
    >
      <PaperPlaneTilt v-if="!submitting" :size="17" weight="bold" aria-hidden="true" />
      <span>{{ submitting ? '送審中…' : '送出審查' }}</span>
    </button>

    <div
      v-else
      class="submission-bar__complete"
      data-testid="submission-result"
      :data-status="submission.caseStatus"
    >
      <CheckCircle :size="20" weight="fill" aria-hidden="true" />
      <div>
        <strong>第 {{ submission.submissionNo }} 次送審</strong>
        <span>案件狀態：{{ statusLabel(submission.caseStatus) }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.submission-bar {
  position: sticky;
  z-index: 12;
  bottom: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  border: 1px solid #d9e2ec;
  border-radius: var(--app-radius-md);
  background: #fff;
  box-shadow: 0 10px 28px rgba(30, 52, 78, .12);
}
.submission-bar__copy strong { color: var(--app-ink); font-size: 15px; }
.submission-bar__copy p { margin: 5px 0 0; color: var(--app-ink-soft); font-size: 12px; }
.submission-bar__submit {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 10px 18px;
  border: 1px solid var(--app-accent);
  border-radius: 9px;
  color: #fff;
  background: var(--app-accent);
  cursor: pointer;
  font-size: 13px;
  font-weight: 850;
}
.submission-bar__submit:disabled { cursor: not-allowed; opacity: .55; }
.submission-bar__complete {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 14px;
  border: 1px solid rgba(59, 129, 102, .24);
  border-radius: 9px;
  color: var(--app-green);
  background: rgba(59, 129, 102, .08);
}
.submission-bar__complete > div { display: grid; gap: 3px; }
.submission-bar__complete span { color: var(--app-ink-soft); font-size: 12px; }

@media (max-width: 640px) {
  .submission-bar { position: static; align-items: stretch; flex-direction: column; box-shadow: 0 8px 22px rgba(30, 52, 78, .10); }
  .submission-bar__submit { width: 100%; }
}
</style>
