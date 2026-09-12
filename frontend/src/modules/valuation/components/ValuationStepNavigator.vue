<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  currentStep: 1 | 2 | 3 | 4 | 5 | 6
  availableSteps?: number[]
  issueCounts?: Partial<Record<1 | 2 | 3 | 4 | 5 | 6, number>>
}>(), {
  availableSteps: () => [1, 2, 3, 4, 5, 6],
  issueCounts: () => ({}),
})

const emit = defineEmits<{
  navigate: [step: 1 | 2 | 3 | 4 | 5 | 6]
}>()

const steps = [
  { number: 1, label: '案件設定' },
  { number: 2, label: '文件與 AI 辨識' },
  { number: 3, label: '資料確認' },
  { number: 4, label: '計算與檢核' },
  { number: 5, label: '查估書確認' },
  { number: 6, label: '送審' },
] as const

const currentStepMeta = computed(() => steps.find((step) => step.number === props.currentStep) ?? steps[0])
const progressPercent = computed(() => `${Math.round((props.currentStep / steps.length) * 100)}%`)

function isAvailable(step: number): boolean {
  return props.availableSteps.includes(step)
}

</script>

<template>
  <nav class="valuation-steps" aria-label="估價作業步驟">
    <div class="valuation-steps__summary" data-testid="valuation-step-summary">
      <div>
        <span>估價流程</span>
        <strong>第 {{ currentStep }} 步 / {{ steps.length }} · {{ currentStepMeta.label }}</strong>
      </div>
      <span>{{ progressPercent }}</span>
    </div>
    <div class="valuation-steps__progress" aria-hidden="true">
      <span :style="{ width: progressPercent }"></span>
    </div>
    <ol>
      <li
        v-for="step in steps"
        :key="step.number"
        :class="{
          'valuation-steps__item--active': step.number === currentStep,
          'valuation-steps__item--complete': step.number < currentStep,
        }"
        :aria-current="step.number === currentStep ? 'step' : undefined"
      >
        <button
          type="button"
          :data-testid="`valuation-step-${step.number}`"
          :disabled="!isAvailable(step.number)"
          :aria-label="`${step.number}. ${step.label}${issueCounts[step.number] ? `，${issueCounts[step.number]} 項待處理` : ''}`"
          @click="emit('navigate', step.number)"
        >
          <span class="valuation-steps__number" aria-hidden="true">{{ step.number }}</span>
          <span class="valuation-steps__label">{{ step.label }}</span>
          <span v-if="issueCounts[step.number]" class="valuation-steps__issue" aria-hidden="true">{{ issueCounts[step.number] }}</span>
        </button>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.valuation-steps {
  padding: 16px 18px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: var(--app-radius-md);
  background: rgba(255, 255, 255, 0.62);
  box-shadow: var(--app-shadow-soft);
}

.valuation-steps__summary {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
}

.valuation-steps__summary > div {
  display: grid;
  gap: 2px;
}

.valuation-steps__summary span {
  color: var(--app-muted);
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .1em;
}

.valuation-steps__summary strong {
  color: var(--app-ink);
  font-size: 12px;
}

.valuation-steps__progress {
  height: 4px;
  margin-bottom: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(46, 89, 132, .09);
}

.valuation-steps__progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--app-accent);
  transition: width 180ms ease;
}

.valuation-steps ol {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.valuation-steps li {
  min-width: 0;
  color: var(--app-muted);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
}

.valuation-steps button {
  display: flex;
  width: 100%;
  min-height: 44px;
  align-items: center;
  gap: 7px;
  padding: 7px 8px;
  border: 0;
  border-radius: 9px;
  color: inherit;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.valuation-steps button:hover:not(:disabled) {
  background: rgba(46, 89, 132, .07);
}

.valuation-steps button:disabled {
  cursor: not-allowed;
  opacity: .46;
}

.valuation-steps__label {
  min-width: 0;
}

.valuation-steps__issue {
  display: inline-grid;
  min-width: 20px;
  height: 20px;
  margin-left: auto;
  place-items: center;
  border-radius: 999px;
  color: #9a4b28;
  background: #fff0e7;
  font-size: 10px;
  font-weight: 900;
}

.valuation-steps__number {
  display: inline-grid;
  width: 25px;
  height: 25px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid var(--app-line);
  border-radius: 50%;
  color: var(--app-muted);
  background: var(--app-paper-strong);
}

.valuation-steps__item--active,
.valuation-steps__item--complete {
  color: var(--app-accent-deep);
}

.valuation-steps__item--active .valuation-steps__number {
  border-color: var(--app-accent);
  color: #fff;
  background: var(--app-accent);
}

.valuation-steps__item--complete .valuation-steps__number {
  border-color: rgba(59, 129, 102, 0.45);
  color: var(--app-green);
  background: rgba(59, 129, 102, 0.09);
}

@media (max-width: 760px) {
  .valuation-steps ol {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    row-gap: 12px;
  }
}
</style>
