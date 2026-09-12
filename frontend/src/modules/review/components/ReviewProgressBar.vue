<script setup lang="ts">
interface ReviewProgressStep {
  key: string
  label: string
  state: 'done' | 'active' | 'upcoming'
}

defineProps<{
  steps: ReviewProgressStep[]
}>()
</script>

<template>
  <nav class="review-progress" aria-label="審查流程" data-testid="review-progress">
    <ol>
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        :class="`is-${step.state}`"
        :aria-current="step.state === 'active' ? 'step' : undefined"
        :data-workflow-step="step.key"
      >
        <span class="review-progress__marker" aria-hidden="true">
          <span v-if="step.state === 'done'">✓</span>
          <span v-else>{{ index + 1 }}</span>
        </span>
        <span class="review-progress__label">{{ step.label }}</span>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.review-progress {
  margin-top: 12px;
  padding: 14px 16px;
  overflow-x: auto;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
}

.review-progress ol {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(112px, 1fr);
  min-width: max-content;
  margin: 0;
  padding: 0;
  list-style: none;
}

.review-progress li {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 7px;
  min-width: 112px;
  padding-inline: 8px;
  color: var(--app-muted);
  text-align: center;
}

.review-progress li::before,
.review-progress li::after {
  position: absolute;
  top: 15px;
  height: 2px;
  background: #e4e9ee;
  content: '';
}

.review-progress li::before { left: 0; width: calc(50% - 18px); }
.review-progress li::after { right: 0; width: calc(50% - 18px); }
.review-progress li:first-child::before,
.review-progress li:last-child::after { display: none; }
.review-progress li.is-done::before,
.review-progress li.is-done::after,
.review-progress li.is-active::before { background: var(--app-green); }

.review-progress__marker {
  position: relative;
  z-index: 1;
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border: 2px solid #dbe2e8;
  border-radius: 999px;
  color: var(--app-muted);
  background: #fff;
  font-size: 11px;
  font-weight: 900;
}

.review-progress li.is-done .review-progress__marker {
  border-color: var(--app-green);
  color: #fff;
  background: var(--app-green);
}

.review-progress li.is-active .review-progress__marker {
  border-color: var(--app-accent);
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
  box-shadow: 0 0 0 4px rgba(200, 91, 67, .10);
}

.review-progress__label {
  max-width: 132px;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.4;
}

.review-progress li.is-done .review-progress__label { color: var(--app-ink-soft); }
.review-progress li.is-active .review-progress__label { color: var(--app-accent-deep); }

@media (max-width: 640px) {
  .review-progress { padding-inline: 10px; }
  .review-progress ol { grid-auto-columns: 102px; }
  .review-progress li { min-width: 102px; padding-inline: 4px; }
  .review-progress__label { font-size: 10px; }
}
</style>
