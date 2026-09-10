import type { RouteRecordRaw } from 'vue-router'

const lazyAssistant = () => import('./views/AssistantView.vue')

const assistantMeta = {
  requiresAuth: true,
  permission: 'assistant.use',
  title: '智能助理',
  subsystem: '智能助理',
  description: '在授權的估價案件脈絡中使用輔助問答。',
}

export const assistantRoutes: readonly RouteRecordRaw[] = [
  {
    path: 'assistant/new',
    name: 'assistant-new',
    component: lazyAssistant,
    meta: assistantMeta,
  },
  {
    path: 'assistant',
    name: 'assistant',
    component: lazyAssistant,
    meta: assistantMeta,
  },
  {
    path: 'assistant/sessions/:sessionId',
    name: 'assistant-session',
    component: lazyAssistant,
    meta: assistantMeta,
  },
]
