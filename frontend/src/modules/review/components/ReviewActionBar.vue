<script setup lang="ts">
defineProps<{ starting?: boolean; canStart?: boolean; canComplete?: boolean }>()
defineEmits<{ start: []; complete: [] }>()
</script>
<template>
  <div class="review-action-bar">
    <button v-if="canStart" class="primary-button" type="button" :disabled="starting" @click="$emit('start')">{{ starting ? '啟動中…' : '啟動智慧審查' }}</button>
    <button v-if="canComplete" class="text-button" type="button" @click="$emit('complete')">完成審查</button>
  </div>
</template>