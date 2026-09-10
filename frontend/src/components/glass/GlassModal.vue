<script setup lang="ts">
defineProps<{ open: boolean; title: string }>()
defineEmits<{ close: [] }>()
</script>
<template><div v-if="open" class="overlay" @click.self="$emit('close')"><section class="modal-card" role="dialog" aria-modal="true" :aria-label="title"><header><h2>{{ title }}</h2><button type="button" aria-label="關閉" @click="$emit('close')">×</button></header><slot /></section></div></template>