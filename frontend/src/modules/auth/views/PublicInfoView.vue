<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PublicLayout from '../../../layouts/PublicLayout.vue'

const route = useRoute()
const title = computed(() => (typeof route.meta.title === 'string' ? route.meta.title : '平台資訊'))
const description = computed(() =>
  typeof route.meta.description === 'string' ? route.meta.description : '這個入口尚未開放。',
)
</script>

<template>
  <PublicLayout>
    <section class="public-info public-container" aria-labelledby="public-info-title">
      <p class="eyebrow">估價審查中台</p>
      <h1 id="public-info-title">{{ title }}</h1>
      <p>{{ description }}</p>
    </section>
  </PublicLayout>
</template>

<style scoped>
.public-info {
  min-height: 60vh;
  padding-top: 96px;
}

.public-info h1 {
  max-width: 660px;
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: clamp(36px, 6vw, 66px);
  font-weight: 600;
  letter-spacing: -0.07em;
}

.public-info > p:last-child {
  max-width: 540px;
  margin: 20px 0 0;
  color: var(--app-ink-soft);
  font-size: 16px;
  line-height: 1.8;
}
</style>
