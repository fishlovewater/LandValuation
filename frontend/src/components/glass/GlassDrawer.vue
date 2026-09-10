<script setup lang="ts">
defineProps<{ open: boolean; title: string }>()
defineEmits<{ close: [] }>()
</script>
<template><aside v-if="open" class="drawer" role="dialog" :aria-label="title"><header><h2>{{ title }}</h2><button type="button" aria-label="關閉" @click="$emit('close')">×</button></header><slot /></aside></template>