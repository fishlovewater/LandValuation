<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
}

watch(() => props.open, async (open) => {
  if (open) {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    panel.value?.querySelector<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]')?.focus()
  } else {
    opener?.focus()
    opener = null
  }
})
</script>

<template>
  <aside v-if="open" ref="panel" class="drawer" role="dialog" aria-modal="true" :aria-label="title" @keydown="onKeydown">
    <header><h2>{{ title }}</h2><button type="button" aria-label="關閉" @click="$emit('close')">×</button></header>
    <slot />
  </aside>
</template>
