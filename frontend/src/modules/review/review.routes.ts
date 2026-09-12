import type { RouteRecordRaw } from 'vue-router'
import { REVIEW_ROLES } from '../../router/roleAccess'

const lazyDashboard = () => import('./views/ReviewDashboardView.vue')
const lazyWorkbench = () => import('./views/ReviewWorkbenchView.vue')
const lazyResult = () => import('./views/ReviewResultView.vue')

export const reviewRoutes: readonly RouteRecordRaw[] = [
  {
    path: 'review/dashboard',
    name: 'review-dashboard',
    component: lazyDashboard,
    meta: {
      requiresAuth: true,
      roles: [...REVIEW_ROLES],
      permission: 'review.execute',
      title: '審查工作台',
      subsystem: '審查工作台',
      description: '依案件風險與審查狀態接續工作。',
    },
  },
  {
    path: 'review/workbench/:reviewId?',
    name: 'review-workbench',
    component: lazyWorkbench,
    meta: {
      requiresAuth: true,
      roles: [...REVIEW_ROLES],
      permission: 'review.execute',
      title: '案件審查',
      subsystem: '審查工作台',
      description: '在同一筆審查案件中查看證據、疑點與決定。',
    },
  },
  {
    path: 'review/result/:reviewId?',
    name: 'review-result',
    component: lazyResult,
    meta: {
      requiresAuth: true,
      roles: [...REVIEW_ROLES],
      permission: 'review.execute',
      title: '審查結果',
      subsystem: '審查工作台',
      description: '查看目前可用的審查輸出與歷程。',
    },
  },
]
