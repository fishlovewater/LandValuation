<script setup lang="ts">
import { computed } from 'vue'
import {
  isKnownRisk,
  normalizedEnumValue,
  riskLabel,
} from '../../utils/enumLabels'

const props = withDefaults(
  defineProps<{
    risk?: string
    level?: string
    riskLevel?: string
  }>(),
  {
    risk: undefined,
    level: undefined,
    riskLevel: undefined,
  },
)

const rawRisk = computed(() => props.risk ?? props.riskLevel ?? props.level ?? '')
const known = computed(() => isKnownRisk(rawRisk.value))
const normalized = computed(() => normalizedEnumValue(rawRisk.value))
const displayLabel = computed(() => riskLabel(rawRisk.value))
const diagnosticLabel = computed(() =>
  known.value ? displayLabel.value : `${displayLabel.value}（${rawRisk.value || '空值'}）`,
)
const dataRisk = computed(() => (known.value ? normalized.value.toLowerCase() : 'unknown'))
</script>

<template>
  <span
    class="risk-badge"
    :class="`risk-badge--${dataRisk}`"
    :data-risk="dataRisk"
    :data-risk-value="rawRisk"
    :title="diagnosticLabel"
    role="status"
    :aria-label="diagnosticLabel"
  >
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        v-if="dataRisk === 'low'"
        d="M12 3.5 20 7v5.4c0 4.4-3.1 7.1-8 8.8-4.9-1.7-8-4.4-8-8.8V7l8-3.5Zm-3.5 8.7 2.2 2.2 4.9-5"
        fill="none"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="1.8"
      />
      <path
        v-else
        d="M12 3 21 20H3L12 3Zm0 5.3v5.4m0 3.1h.01"
        fill="none"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="1.8"
      />
    </svg>
    <span>{{ displayLabel }}</span>
  </span>
</template>

<style scoped>
.risk-badge {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid #c7d6e8;
  border-radius: var(--app-radius-pill);
  color: #2e5984;
  background: #edf4fb;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.35;
  white-space: nowrap;
}

.risk-badge svg { flex: 0 0 auto; }
.risk-badge--medium { border-color: #e0c98a; color: #7a5d14; background: #fff7df; }
.risk-badge--high,
.risk-badge--critical { border-color: #e8b3ac; color: #9b3f35; background: #fcecea; }
.risk-badge--unknown { border-color: #d7dbe3; color: var(--app-ink-soft); background: #f1f3f6; }
</style>
