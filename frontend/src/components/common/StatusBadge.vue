<script setup lang="ts">
import { statusLabel } from '../../utils/enumLabels'
defineProps<{ status: string }>()
</script>
<template><span class="badge">{{ statusLabel(status) }}</span></template>