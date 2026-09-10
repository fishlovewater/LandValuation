<script setup lang="ts">
import { computed } from 'vue'
import {
  isKnownStatus,
  normalizedEnumValue,
  statusLabel,
} from '../../utils/enumLabels'

const props = defineProps<{
  status: string
}>()

const normalized = computed(() => normalizedEnumValue(props.status))
const known = computed(() => isKnownStatus(props.status))
const displayLabel = computed(() => statusLabel(props.status))
const diagnosticLabel = computed(() =>
  known.value ? displayLabel.value : `${displayLabel.value}（${props.status || '空值'}）`,
)
const dataStatus = computed(() => (known.value ? normalized.value.toLowerCase() : 'unknown'))
</script>

<template>
  <span
    class="status-badge"
    :class="{ 'status-badge--unknown': !known }"
    :data-status="dataStatus"
    :data-status-value="props.status"
    :data-status-code="dataStatus"
    :title="diagnosticLabel"
    role="status"
    :aria-label="diagnosticLabel"
  >
    {{ displayLabel }}
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
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

.status-badge--unknown {
  border-color: #d7dbe3;
  color: var(--app-ink-soft);
  background: #f1f3f6;
}
</style>
