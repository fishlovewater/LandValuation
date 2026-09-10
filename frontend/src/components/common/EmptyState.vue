<script setup lang="ts">
withDefaults(defineProps<{ title?: string; message?: string }>(), {
  title: '沒有資料',
  message: '目前沒有符合條件的內容。',
})
</script>
<template><section class="state-card"><h2>{{ title }}</h2><p>{{ message }}</p><slot /></section></template>