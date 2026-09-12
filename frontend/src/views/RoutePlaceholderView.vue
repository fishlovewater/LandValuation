<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../components/common/PageHeader.vue'

const route = useRoute()
const title = computed(() => (typeof route.meta.title === 'string' ? route.meta.title : '工作頁面'))
const subsystem = computed(() =>
  typeof route.meta.subsystem === 'string' ? route.meta.subsystem : '估價審查中台',
)
const description = computed(() =>
  typeof route.meta.description === 'string'
    ? route.meta.description
    : '此頁面將在下一階段接入已驗證的服務資料。',
)
</script>

<template>
  <section class="route-placeholder" aria-labelledby="route-placeholder-title">
    <PageHeader :eyebrow="subsystem" :title="title" :description="description" />
    <div class="route-placeholder__surface">
      <p class="route-placeholder__label">目前工作區</p>
      <h2 id="route-placeholder-title">功能邊界已就緒</h2>
      <p>這個入口只保留路由與權限邊界，不預先放入案件、統計或其他示範資料。</p>
    </div>
  </section>
</template>

<style scoped>
.route-placeholder {
  min-height: calc(100vh - 132px);
  padding: 0 26px 40px;
}

.route-placeholder__surface {
  max-width: 820px;
  margin: 20px auto 0;
  padding: 34px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-paper);
}

.route-placeholder__label {
  margin: 0 0 8px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

.route-placeholder h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: clamp(24px, 4vw, 36px);
  font-weight: 600;
  letter-spacing: -0.05em;
}

.route-placeholder__surface > p:last-child {
  max-width: 560px;
  margin: 12px 0 0;
  color: var(--app-ink-soft);
  font-size: 14px;
  line-height: 1.8;
}

@media (max-width: 640px) {
  .route-placeholder {
    padding-inline: 16px;
  }

  .route-placeholder__surface {
    padding: 24px;
  }
}
</style>
