<script setup lang="ts">
import { PhArrowLeft as ArrowLeft, PhArrowRight as ArrowRight } from '@phosphor-icons/vue'

const props = defineProps<{
  title: string
  nextLabel: string
  isFirstStep: boolean
  confirming: boolean
  nextDisabled: boolean
}>()

const emit = defineEmits<{
  previous: []
  next: []
}>()
</script>

<template>
  <footer class="wizard-footer" data-testid="valuation-workflow-guide" aria-label="估價流程導覽">
    <button
      class="wizard-footer__secondary"
      type="button"
      :disabled="props.isFirstStep"
      @click="emit('previous')"
    >
      <ArrowLeft :size="15" weight="bold" aria-hidden="true" />
      <span>上一步</span>
    </button>
    <div class="wizard-footer__status">
      <strong>{{ props.title }}</strong>
      <span>{{ props.nextLabel }}</span>
    </div>
    <button
      class="wizard-footer__primary"
      type="button"
      data-testid="wizard-next"
      :disabled="props.confirming || props.nextDisabled"
      @click="emit('next')"
    >
      <span>{{ props.confirming ? '確認中…' : props.nextLabel }}</span>
      <ArrowRight v-if="!props.confirming" :size="15" weight="bold" aria-hidden="true" />
    </button>
  </footer>
</template>

<style scoped>
.wizard-footer {
  position: sticky;
  z-index: 8;
  bottom: 14px;
  display: grid;
  grid-template-columns: auto minmax(180px, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(190, 204, 220, .9);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(30, 52, 78, .12);
}

.wizard-footer button {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 9px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

.wizard-footer button:disabled {
  cursor: not-allowed;
  opacity: .48;
}

.wizard-footer__secondary {
  border: 1px solid #ccd7e3;
  color: #465a70;
  background: #fff;
}

.wizard-footer__primary {
  border: 1px solid #2e5984;
  color: #fff;
  background: #2e5984;
}

.wizard-footer__status {
  display: grid;
  gap: 2px;
  text-align: center;
}

.wizard-footer__status strong {
  color: var(--app-ink);
  font-size: 11px;
}

.wizard-footer__status span {
  color: var(--app-muted);
  font-size: 9px;
}

@media (max-width: 760px) {
  .wizard-footer {
    bottom: 8px;
    grid-template-columns: 1fr 1fr;
  }

  .wizard-footer__status {
    grid-column: 1 / -1;
    grid-row: 1;
  }
}
</style>
