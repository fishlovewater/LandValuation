<script setup lang="ts">
defineProps<{
  eyebrow?: string
  title: string
  description?: string
}>()
</script>

<template>
  <header class="page-header">
    <p v-if="eyebrow" class="page-header__eyebrow">{{ eyebrow }}</p>
    <div class="page-header__row">
      <div>
        <h1>{{ title }}</h1>
        <p v-if="description" class="page-header__description">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="page-header__actions">
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<style scoped>
.page-header {
  padding: 26px 4px 18px;
}

.page-header__eyebrow {
  margin: 0 0 8px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.page-header__row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.page-header h1 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: clamp(28px, 3vw, 42px);
  font-weight: 600;
  letter-spacing: -0.06em;
  line-height: 1.2;
}

.page-header__description {
  max-width: 680px;
  margin: 10px 0 0;
  color: var(--app-ink-soft);
  font-size: 14px;
  line-height: 1.7;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

@media (max-width: 640px) {
  .page-header__row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
