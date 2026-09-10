<script setup lang="ts">
defineProps<{ starting?: boolean; canStart?: boolean; canComplete?: boolean; canCorrect?: boolean }>()
defineEmits<{ start: []; complete: []; correct: [] }>()
</script>
<template>
  <div class="review-action-bar">
    <button v-if="canStart" class="primary-button" type="button" :disabled="starting" @click="$emit('start')">{{ starting ? '啟動中…' : '啟動智慧審查' }}</button>
    <button v-if="canCorrect" class="text-button" type="button" @click="$emit('correct')">送出補正通知</button>
    <button v-if="canComplete" class="text-button" type="button" @click="$emit('complete')">完成審查</button>
  </div>
</template>