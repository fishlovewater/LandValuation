<script setup lang="ts">
import {
  PhCheckCircle as CheckCircle,
  PhLockKey as LockKey,
  PhPaperPlaneTilt as PaperPlaneTilt,
  PhShieldCheck as ShieldCheck,
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
  <section
    class="submission-bar"
    :data-state="submission ? 'submitted' : canSubmit ? 'ready' : 'blocked'"
    aria-label="送審操作"
  >
    <div class="submission-bar__status-icon" aria-hidden="true">
      <CheckCircle v-if="submission" :size="22" weight="fill" />
      <ShieldCheck v-else-if="canSubmit" :size="22" weight="duotone" />
      <LockKey v-else :size="21" weight="duotone" />
    </div>

    <div class="submission-bar__copy">
      <span>{{ submission ? '送審完成' : canSubmit ? '已符合送審條件' : '送審條件尚未完成' }}</span>
      <strong>{{ submission ? '案件已送出審查' : readinessMessage }}</strong>
      <p v-if="submission">送審時間：{{ formatDateZhTw(submission.submittedAt) }}</p>
      <p v-else-if="canSubmit">正式送審 PDF 與送審文件檢核皆已完成，可以送出本次審查。</p>
      <p v-else>完成查估書確認、送審文件檢核與正式送審 PDF 後即可送出審查。</p>
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
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 17px 18px;
  border: 1px solid #d9e2ec;
  border-radius: var(--app-radius-md);
  background: #fff;
  box-shadow: 0 10px 28px rgba(30, 52, 78, .12);
}
.submission-bar[data-state="ready"] { border-color: #bfd0e2; background: #f9fbfd; }
.submission-bar[data-state="submitted"] { border-color: #cfe4da; background: #f8fcfa; }
.submission-bar__status-icon { display: grid; width: 40px; height: 40px; place-items: center; border-radius: 10px; color: #6c7d8f; background: #f0f3f6; }
.submission-bar[data-state="ready"] .submission-bar__status-icon { color: #2e5984; background: #e8f1fa; }
.submission-bar[data-state="submitted"] .submission-bar__status-icon { color: #2f7456; background: #e8f5ee; }
.submission-bar__copy { display: grid; gap: 3px; min-width: 0; }
.submission-bar__copy > span { color: var(--app-muted); font-size: 9px; font-weight: 900; letter-spacing: .08em; }
.submission-bar[data-state="ready"] .submission-bar__copy > span { color: #2e5984; }
.submission-bar[data-state="submitted"] .submission-bar__copy > span { color: #2f7456; }
.submission-bar__copy strong { color: var(--app-ink); font-size: 14px; line-height: 1.4; }
.submission-bar__copy p { margin: 1px 0 0; color: var(--app-ink-soft); font-size: 11px; line-height: 1.5; }
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
  .submission-bar { position: static; grid-template-columns: 1fr; align-items: stretch; box-shadow: 0 8px 22px rgba(30, 52, 78, .10); }
  .submission-bar__status-icon { display: none; }
  .submission-bar__submit,
  .submission-bar__complete { width: 100%; }
  .submission-bar__complete { justify-content: center; }
}
</style>
