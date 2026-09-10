import type { RouteRecordRaw } from 'vue-router'

const lazyDashboard = () => import('./views/ValuationDashboardView.vue')
const lazyPrepare = () => import('./views/ValuationPrepareView.vue')
const lazySubmit = () => import('./views/ValuationSubmitView.vue')

export const valuationRoutes: readonly RouteRecordRaw[] = [
  {
    path: 'valuation/dashboard',
    name: 'valuation-dashboard',
    component: lazyDashboard,
    meta: {
      requiresAuth: true,
      permissions: ['case.read', 'valuation.read'],
      title: '估價作業',
      subsystem: '估價作業',
      description: '查看目前可用的估價案件與下一個作業動作。',
    },
  },
  {
    path: 'valuation/cases/:caseId/prepare',
    name: 'valuation-prepare',
    component: lazyPrepare,
    meta: {
      requiresAuth: true,
      permissions: ['case.read', 'valuation.read', 'valuation.update', 'document.download'],
      title: '準備估價資料',
      subsystem: '估價作業',
      description: '確認案件來源與可由 API 支援的正式估價欄位。',
    },
  },
  {
    path: 'valuation/cases/:caseId/submit',
    name: 'valuation-submit',
    component: lazySubmit,
    meta: {
      requiresAuth: true,
      permissions: ['case.read', 'valuation.read', 'valuation.submit_review', 'valuation.update', 'document.download'],
      title: '送審確認',
      subsystem: '估價作業',
      description: '查看伺服器檢核與輸出狀態，送出一次正式審查。',
    },
  },
]
