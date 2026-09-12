<script setup lang="ts">
import { computed } from 'vue'
import {
  PhArrowBendUpLeft as ArrowBendUpLeft,
  PhCheckCircle as CheckCircle,
  PhWarningCircle as WarningCircle,
  PhXCircle as XCircle,
} from '@phosphor-icons/vue'
import type { ValidationRunModel } from '../valuation.types'

const props = defineProps<{
  validation: ValidationRunModel
}>()

const emit = defineEmits<{
  fix: [fieldPath: string | null]
}>()

const blockerCount = computed(() => props.validation.findings.filter((finding) => finding.severity === 'ERROR').length)
</script>

<template>
  <section class="general-validation" data-testid="submit-validation" aria-labelledby="submit-validation-title">
    <div class="general-validation__heading">
      <div>
        <p>檢核結果</p>
        <h2 id="submit-validation-title">檢核與未解決項目</h2>
      </div>
      <span
        class="general-validation__state"
        :data-validation-state="validation.canGenerateReport ? 'ready' : 'blocked'"
      >
        <CheckCircle v-if="validation.canGenerateReport" :size="16" weight="fill" aria-hidden="true" />
        <WarningCircle v-else :size="16" weight="fill" aria-hidden="true" />
        {{ validation.canGenerateReport ? '可以產出' : '仍有待修正項目' }}
      </span>
    </div>

    <div class="general-validation__counts" aria-label="檢核統計">
      <span data-state="passed"><CheckCircle :size="16" weight="fill" aria-hidden="true" />通過 {{ validation.passedCount }}</span>
      <span data-state="warning"><WarningCircle :size="16" weight="fill" aria-hidden="true" />警示 {{ validation.warningCount }}</span>
      <span data-state="error"><XCircle :size="16" weight="fill" aria-hidden="true" />錯誤 {{ validation.failedCount }}</span>
    </div>

    <ul v-if="validation.findings.length" class="general-validation__findings">
      <li
        v-for="finding in validation.findings"
        :key="finding.findingId"
        :data-severity="finding.severity"
      >
        <div class="general-validation__finding-heading">
          <XCircle v-if="finding.severity === 'ERROR'" :size="17" weight="fill" aria-hidden="true" />
          <WarningCircle v-else :size="17" weight="fill" aria-hidden="true" />
          <strong>{{ finding.severity === 'ERROR' ? '需要修正' : '請確認' }}</strong>
        </div>
        <span>{{ finding.message }}</span>
        <div class="general-validation__values">
          <small>實際值：{{ finding.actualValue ?? '—' }}</small>
          <small>預期值：{{ finding.expectedValue ?? '—' }}</small>
        </div>
        <button class="general-validation__fix" type="button" @click="emit('fix', finding.fieldPath)">
          <ArrowBendUpLeft :size="15" weight="bold" aria-hidden="true" />
          <span>返回資料確認修正</span>
        </button>
      </li>
    </ul>
    <p v-else class="general-validation__empty">目前沒有其他需要處理的檢核項目。</p>

    <p v-if="blockerCount" class="general-validation__blocker">
      <WarningCircle :size="17" weight="fill" aria-hidden="true" />
      <span>仍有 {{ blockerCount }} 項待修正內容，請回到資料確認頁處理。</span>
    </p>
  </section>
</template>

<style scoped>
.general-validation {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: #fff;
}
.general-validation__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.general-validation__heading p { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.general-validation__heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; font-weight: 650; letter-spacing: -.035em; }
.general-validation__state,
.general-validation__counts span,
.general-validation__finding-heading,
.general-validation__fix,
.general-validation__blocker {
  display: inline-flex;
  align-items: center;
}
.general-validation__state {
  min-height: 30px;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid rgba(57, 123, 92, .22);
  border-radius: var(--app-radius-pill);
  color: #2f7456;
  background: #edf8f2;
  font-size: 11px;
  font-weight: 850;
  white-space: nowrap;
}
.general-validation__state[data-validation-state="blocked"] { border-color: rgba(193, 92, 65, .24); color: #a44334; background: #fff3f0; }
.general-validation__counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.general-validation__counts span { gap: 6px; padding: 8px 11px; border-radius: 8px; color: var(--app-ink-soft); background: #f5f7fb; font-size: 12px; font-weight: 800; }
.general-validation__counts span[data-state="passed"] { color: #2f7456; background: #edf8f2; }
.general-validation__counts span[data-state="warning"] { color: #946d16; background: #fff8e8; }
.general-validation__counts span[data-state="error"] { color: #a44334; background: #fff3f0; }
.general-validation__findings { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.general-validation__findings li { display: grid; gap: 7px; padding: 13px 14px; border-left: 4px solid #d6a63e; border-radius: 0 8px 8px 0; color: var(--app-ink-soft); background: #fffaf0; font-size: 13px; }
.general-validation__findings li[data-severity="ERROR"] { border-left-color: #c85b43; background: #fff3f0; }
.general-validation__finding-heading { gap: 6px; color: #946d16; }
.general-validation__findings li[data-severity="ERROR"] .general-validation__finding-heading { color: #a44334; }
.general-validation__finding-heading strong { color: currentColor; font-size: 12px; }
.general-validation__values { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--app-muted); }
.general-validation__fix { justify-self: start; min-height: 36px; gap: 6px; margin-top: 2px; padding: 6px 11px; border: 1px solid rgba(46, 89, 132, .24); border-radius: 8px; color: var(--app-accent-deep); background: #fff; cursor: pointer; font-size: 11px; font-weight: 850; }
.general-validation__empty { margin: 0; color: var(--app-muted); font-size: 13px; }
.general-validation__blocker { gap: 7px; margin: 14px 0 0; color: #a44334; font-size: 13px; font-weight: 750; }

@media (max-width: 640px) {
  .general-validation { padding: 16px; }
  .general-validation__heading { flex-direction: column; }
}
</style>
