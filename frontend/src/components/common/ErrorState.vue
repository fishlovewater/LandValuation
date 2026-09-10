<script setup lang="ts">
defineProps<{ message: string }>()
defineEmits<{ retry: [] }>()
</script>
<template><section class="state-card" role="alert"><h2>載入失敗</h2><p>{{ message }}</p><button class="text-button" type="button" @click="$emit('retry')">重試</button></section></template>