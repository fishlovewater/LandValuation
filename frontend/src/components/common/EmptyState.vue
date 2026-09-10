<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description?: string
    actionLabel?: string
  }>(),
  {
    description: undefined,
    actionLabel: undefined,
  },
)

const emit = defineEmits<{
  action: []
}>()
</script>

<template>
  <section class="page-state page-state--empty" aria-live="polite">
    <div class="page-state__icon" aria-hidden="true">○</div>
    <h2>{{ title }}</h2>
    <p v-if="description">{{ description }}</p>
    <button
      v-if="actionLabel || $slots.action"
      class="page-state__action"
      type="button"
      @click="emit('action')"
    >
      <slot name="action">{{ actionLabel }}</slot>
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
  color: var(--app-blue);
  background: #e6eef7;
  font-size: 28px;
  line-height: 1;
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
