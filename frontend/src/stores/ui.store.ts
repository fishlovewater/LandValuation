import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useUiStore = defineStore('ui', () => {
  const message = ref<string | null>(null)
  function notify(value: string) { message.value = value }
  function clear() { message.value = null }
  return { message, notify, clear }
})