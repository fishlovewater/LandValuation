<script setup lang="ts">
withDefaults(defineProps<{ lines?: number }>(), { lines: 4 })
</script>
<template><div class="loading-skeleton" role="status" aria-label="載入中"><span v-for="line in lines" :key="line" /></div></template>