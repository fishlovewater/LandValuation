<script setup lang="ts">
defineProps<{ displayName: string }>()
defineEmits<{ logout: [] }>()
</script>
<template>
  <header class="app-header">
    <div><strong>土地估價智慧審查</strong></div>
    <div class="header-actions"><span>{{ displayName }}</span><button class="text-button" type="button" @click="$emit('logout')">登出</button></div>
  </header>
</template>