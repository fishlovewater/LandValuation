<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    title?: string
    message?: string
    retryLabel?: string
  }>(),
  {
    title: '載入失敗',
    message: '目前無法載入資料，請稍後再試。',
    retryLabel: '重新載入',
  },
)

const emit = defineEmits<{
  retry: []
}>()

const safeMessage = computed(() => props.message?.trim() || '目前無法載入資料，請稍後再試。')
</script>

<template>
  <section class="page-state page-state--error" role="alert" aria-live="assertive">
    <div class="page-state__icon" aria-hidden="true">!</div>
    <h2>{{ title }}</h2>
    <p>{{ safeMessage }}</p>
    <button class="page-state__action" type="button" @click="emit('retry')">
      {{ retryLabel }}
    </button>
  </section>
</template>

<style scoped>
.page-state {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 48px 24px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
  text-align: center;
}

.page-state__icon {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 50%;
  color: #ac3c37;
  background: #f9e5e2;
  font-size: 24px;
  font-weight: 800;
}

.page-state h2,
.page-state p { margin: 0; }

.page-state h2 {
  color: var(--app-ink);
  font-size: 18px;
}

.page-state p {
  max-width: 520px;
  color: var(--app-ink-soft);
  font-size: 14px;
  line-height: 1.65;
}

.page-state__action {
  min-width: 112px;
  min-height: 44px;
  margin-top: 6px;
  padding: 8px 18px;
  border: 1px solid var(--app-accent);
  border-radius: var(--app-radius-pill);
  color: #fff8f2;
  background: var(--app-accent);
  cursor: pointer;
  font-weight: 700;
}

.page-state__action:hover { background: var(--app-accent-deep); }
</style>
