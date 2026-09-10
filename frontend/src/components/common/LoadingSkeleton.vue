<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    rows?: number
    label?: string
  }>(),
  {
    rows: 3,
    label: '載入中',
  },
)

const rowCount = computed(() => Math.max(1, Math.floor(props.rows)))
</script>

<template>
  <div class="loading-skeleton" role="status" aria-busy="true" aria-live="polite" :aria-label="label">
    <span
      v-for="row in rowCount"
      :key="row"
      class="loading-skeleton__row"
      aria-hidden="true"
    />
  </div>
</template>

<style scoped>
.loading-skeleton {
  display: grid;
  gap: 12px;
  width: 100%;
  padding: 20px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
}

.loading-skeleton__row {
  display: block;
  width: 100%;
  height: 18px;
  border-radius: 6px;
  background: linear-gradient(90deg, #edf1f7 25%, #f8fafc 50%, #edf1f7 75%);
  background-size: 200% 100%;
  animation: loading-skeleton-shimmer 1.5s ease-in-out infinite;
}

@keyframes loading-skeleton-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .loading-skeleton__row { animation: none; }
}
</style>
