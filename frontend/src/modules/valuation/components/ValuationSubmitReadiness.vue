<script setup lang="ts">
import {
  PhArrowRight as ArrowRight,
  PhCheck as Check,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'

export type SubmitReadinessState = 'done' | 'active' | 'pending' | 'blocked'
export type SubmitReadinessItem = {
  key: string
  title: string
  detail: string
  target: string
  state: SubmitReadinessState
}

const props = defineProps<{
  steps: SubmitReadinessItem[]
  currentStep: SubmitReadinessItem | null
  completedStepCount: number
  submitted: boolean
  readinessMessage: string
}>()

const emit = defineEmits<{
  select: [target: string]
}>()

function stateLabel(state: SubmitReadinessState): string {
  return ({
    done: '已完成',
    active: '下一步',
    pending: '待前置作業',
    blocked: '需修正',
  } as Record<SubmitReadinessState, string>)[state]
}

function displayTitle(item: SubmitReadinessItem): string {
  if (item.key === 'formal-validation') return '完成送審文件檢核'
  if (item.key === 'formal-pdf') return '產生正式送審 PDF'
  return item.title
}
</script>

<template>
  <section
    v-if="!props.submitted && props.currentStep"
    class="submit-next-action"
    data-testid="submit-next-action"
    :data-state="props.currentStep.state"
    aria-labelledby="submit-next-action-title"
  >
    <div class="submit-next-action__icon" aria-hidden="true">
      <WarningCircle v-if="props.currentStep.state === 'blocked'" :size="22" weight="duotone" />
      <ArrowRight v-else :size="20" weight="bold" />
    </div>
    <div class="submit-next-action__copy">
      <span>{{ props.currentStep.state === 'blocked' ? '目前需要先修正' : '目前下一步' }}</span>
      <strong id="submit-next-action-title">{{ displayTitle(props.currentStep) }}</strong>
      <small>{{ props.currentStep.detail }}</small>
    </div>
    <button type="button" @click="emit('select', props.currentStep.target)">
      <span>{{ props.currentStep.state === 'blocked' ? '前往修正' : '前往處理' }}</span>
      <ArrowRight :size="14" weight="bold" aria-hidden="true" />
    </button>
  </section>

  <section
    class="submit-readiness"
    data-testid="submit-readiness-steps"
    aria-labelledby="submit-readiness-title"
  >
    <div class="submit-readiness__heading">
      <div>
        <p>送審準備</p>
        <h2 id="submit-readiness-title">{{ props.completedStepCount }} / 4 已完成</h2>
      </div>
      <strong>{{ props.submitted ? '案件已送審' : props.readinessMessage }}</strong>
    </div>

    <div class="submit-readiness__steps">
      <article
        v-for="(item, index) in props.steps"
        :key="item.key"
        :data-state="item.state"
      >
        <div class="submit-readiness__index" aria-hidden="true">
          <Check v-if="item.state === 'done'" :size="13" weight="bold" />
          <span v-else>{{ index + 1 }}</span>
        </div>
        <div class="submit-readiness__copy">
          <span>{{ stateLabel(item.state) }}</span>
          <strong>{{ displayTitle(item) }}</strong>
          <small>{{ item.detail }}</small>
        </div>
        <button
          v-if="item.state !== 'done'"
          type="button"
          :disabled="item.state === 'pending' && item.key === 'submission'"
          @click="emit('select', item.target)"
        >
          <span>{{ item.state === 'blocked' ? '前往修正' : item.state === 'active' ? '前往處理' : '查看' }}</span>
          <ArrowRight :size="13" weight="bold" aria-hidden="true" />
        </button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.submit-next-action {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 15px 18px;
  border: 1px solid #bfd0e2;
  border-left: 5px solid #2e5984;
  border-radius: var(--app-radius-sm);
  background: #f4f8fc;
}

.submit-next-action[data-state="blocked"] {
  border-color: #edc8c0;
  border-left-color: #b84d3b;
  background: #fff5f3;
}

.submit-next-action__icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 9px;
  color: #2e5984;
  background: #e7f0f9;
}

.submit-next-action[data-state="blocked"] .submit-next-action__icon {
  color: #b84d3b;
  background: #ffe8e3;
}

.submit-next-action__copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.submit-next-action__copy > span {
  color: var(--app-muted);
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .1em;
}

.submit-next-action__copy strong {
  color: var(--app-ink);
  font-size: 14px;
}

.submit-next-action__copy small {
  color: var(--app-ink-soft);
  font-size: 11px;
  line-height: 1.55;
}

.submit-next-action > button,
.submit-readiness__steps button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 900;
}

.submit-next-action > button {
  min-height: 40px;
  padding: 8px 13px;
  border: 1px solid #2e5984;
  color: #fff;
  background: #2e5984;
  font-size: 11px;
}

.submit-next-action[data-state="blocked"] > button {
  border-color: #b84d3b;
  background: #b84d3b;
}

.submit-readiness {
  display: grid;
  gap: 14px;
  padding: 18px 20px;
  border: 1px solid #dce5ef;
  border-radius: var(--app-radius-md);
  background: #f8fbfe;
}

.submit-readiness__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.submit-readiness__heading p {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}

.submit-readiness__heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 22px;
}

.submit-readiness__heading > strong {
  max-width: 520px;
  color: var(--app-ink-soft);
  font-size: 12px;
  line-height: 1.6;
  text-align: right;
}

.submit-readiness__steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
}

.submit-readiness__steps article {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-content: start;
  gap: 9px;
  min-width: 0;
  padding: 12px;
  border: 1px solid #dde5ee;
  border-radius: 10px;
  background: #fff;
}

.submit-readiness__steps article[data-state="done"] {
  border-color: #cfe0d6;
  background: #f5faf7;
}

.submit-readiness__steps article[data-state="active"] {
  border-color: #bfd0e2;
  background: #f4f8fc;
}

.submit-readiness__steps article[data-state="blocked"] {
  border-color: #edc8c0;
  background: #fff5f3;
}

.submit-readiness__index {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 999px;
  color: #fff;
  background: #718397;
  font-size: 10px;
  font-weight: 900;
}

.submit-readiness__steps article[data-state="done"] .submit-readiness__index {
  background: var(--app-green);
}

.submit-readiness__steps article[data-state="active"] .submit-readiness__index {
  background: #2e5984;
}

.submit-readiness__steps article[data-state="blocked"] .submit-readiness__index {
  background: #b84d3b;
}

.submit-readiness__copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.submit-readiness__copy > span {
  color: var(--app-muted);
  font-size: 9px;
  font-weight: 900;
}

.submit-readiness__copy strong {
  color: var(--app-ink);
  font-size: 12px;
  line-height: 1.4;
}

.submit-readiness__copy small {
  color: var(--app-muted);
  font-size: 10px;
  line-height: 1.5;
}

.submit-readiness__steps button {
  grid-column: 1 / -1;
  justify-self: start;
  min-height: 34px;
  padding: 6px 10px;
  border: 1px solid #cbd8e5;
  color: #244d73;
  background: #fff;
  font-size: 10px;
}

.submit-readiness__steps button:disabled {
  cursor: not-allowed;
  opacity: .5;
}

@media (max-width: 900px) {
  .submit-readiness__steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .submit-next-action {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .submit-next-action__icon {
    display: none;
  }

  .submit-next-action > button {
    width: 100%;
  }

  .submit-readiness__heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .submit-readiness__heading > strong {
    text-align: left;
  }

  .submit-readiness__steps {
    grid-template-columns: 1fr;
  }
}
</style>
