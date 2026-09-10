<script setup lang="ts">
defineProps<{
  currentStep: 1 | 2 | 3 | 4 | 5 | 6
}>()

const steps = [
  { number: 1, label: '案件與文件' },
  { number: 2, label: '資料確認' },
  { number: 3, label: '伺服器計算' },
  { number: 4, label: '檢核結果' },
  { number: 5, label: '輸出預覽' },
  { number: 6, label: '送審' },
]

</script>

<template>
  <nav class="valuation-steps" aria-label="估價作業步驟">
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
        <span class="valuation-steps__number" aria-hidden="true">{{ step.number }}</span>
        <span>{{ step.label }}</span>
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

.valuation-steps ol {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.valuation-steps li {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  color: var(--app-muted);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
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
