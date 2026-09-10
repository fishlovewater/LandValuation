<script setup lang="ts">
import { riskLabel } from '../../utils/enumLabels'
const props = defineProps<{ level?: string }>()
</script>
<template><span class="badge risk-badge" :data-risk="level ?? 'NONE'" :aria-label="`風險等級：${riskLabel(props.level)}`"><span aria-hidden="true">◆</span> {{ riskLabel(props.level) }}</span></template>