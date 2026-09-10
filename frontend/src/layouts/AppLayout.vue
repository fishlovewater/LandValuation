<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { RouterView } from 'vue-router'
import AppHeader from '../components/common/AppHeader.vue'
import AppSidebar from '../components/common/AppSidebar.vue'
import AssistantQuickDrawer from '../modules/assistant/components/AssistantQuickDrawer.vue'

const sidebarOpen = ref(false)
const assistantOpen = ref(false)

function toggleSidebar(): void {
  sidebarOpen.value = !sidebarOpen.value
}

function closeSidebar(): void {
  if (!sidebarOpen.value) return
  sidebarOpen.value = false
  void nextTick(() => document.getElementById('app-sidebar-trigger')?.focus())
}

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
      :sidebar-open="sidebarOpen"
      :assistant-open="assistantOpen"
      @toggle-sidebar="toggleSidebar"
      @open-assistant="openAssistant"
    />

    <div class="app-layout__body">
      <button
        v-if="sidebarOpen"
        class="app-layout__backdrop"
        type="button"
        aria-label="關閉功能選單"
        @click="closeSidebar"
      />
      <AppSidebar :open="sidebarOpen" @close="closeSidebar" />

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
  padding: 16px 24px 24px;
  background:
    radial-gradient(circle at 5% 4%, rgba(229, 239, 249, 0.68), transparent 28rem),
    radial-gradient(circle at 96% 4%, rgba(247, 228, 216, 0.7), transparent 30rem),
    var(--app-paper);
}

.app-layout__body {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  max-width: 1440px;
  margin: 18px auto 0;
}

.app-layout__main {
  min-width: 0;
  flex: 1 1 auto;
  min-height: calc(100vh - 130px);
  border: 1px solid rgba(223, 229, 239, 0.86);
  border-radius: var(--app-radius-md);
  background: var(--app-paper-strong);
  box-shadow: var(--app-shadow-soft);
}

.app-layout__complex-work-guidance {
  display: none;
}

.app-layout__backdrop {
  display: none;
}

@media (max-width: 980px) {
  .app-layout {
    padding: 10px 16px 16px;
  }

  .app-layout__body {
    margin-top: 12px;
  }

  .app-layout__main {
    width: 100%;
  }

  .app-layout__backdrop {
    position: fixed;
    z-index: 35;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
    background: rgba(23, 34, 56, 0.24);
    cursor: default;
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
