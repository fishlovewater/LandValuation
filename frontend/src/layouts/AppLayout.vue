<script setup lang="ts">
import { ref } from 'vue'
import { RouterView } from 'vue-router'
import AppHeader from '../components/common/AppHeader.vue'
import AssistantQuickDrawer from '../modules/assistant/components/AssistantQuickDrawer.vue'

const assistantOpen = ref(false)

function openAssistant(): void {
  assistantOpen.value = true
}

function closeAssistant(): void {
  assistantOpen.value = false
}
</script>

<template>
  <div class="app-layout">
    <AppHeader
      :assistant-open="assistantOpen"
      @open-assistant="openAssistant"
    />

    <div class="app-layout__body">
      <main class="app-layout__main" aria-label="主要內容">
        <p class="app-layout__complex-work-guidance" data-testid="complex-work-guidance">
          複雜 PDF 比較與長表單編輯，建議使用桌面螢幕完成。
        </p>
        <RouterView />
        <slot />
      </main>
    </div>
    <AssistantQuickDrawer :open="assistantOpen" @close="closeAssistant" />
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  padding: 12px 20px 24px;
  background: var(--app-paper);
}

.app-layout__body {
  width: 100%;
  max-width: 1760px;
  margin: 12px auto 0;
}

.app-layout__main {
  width: 100%;
  min-width: 0;
  min-height: calc(100vh - 130px);
  border: 1px solid rgba(216, 224, 234, 0.9);
  border-radius: 12px;
  background: #fff;
}

.app-layout__complex-work-guidance {
  display: none;
}

@media (max-width: 980px) {
  .app-layout {
    padding: 10px 16px 16px;
  }

  .app-layout__main {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .app-layout {
    padding-inline: 10px;
  }

  .app-layout__main {
    border-radius: var(--app-radius-sm);
  }

  .app-layout__complex-work-guidance {
    display: block;
    margin: 14px 14px 0;
    padding: 10px 12px;
    border: 1px solid #ead7ca;
    border-radius: 9px;
    color: var(--app-accent-deep);
    background: #fff8f3;
    font-size: 12px;
    line-height: 1.6;
  }
}
</style>
