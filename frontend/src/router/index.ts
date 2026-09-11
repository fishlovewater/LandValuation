import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
  type RouterHistory,
} from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'
import AuthLandingView from '../modules/auth/views/AuthLandingView.vue'
import UnauthorizedView from '../modules/auth/views/UnauthorizedView.vue'
import { reviewRoutes } from '../modules/review/review.routes'
import { valuationRoutes } from '../modules/valuation/valuation.routes'
import { historyRoutes } from '../modules/history/history.routes'
import { assistantRoutes } from '../modules/assistant/assistant.routes'
import { authGuard, type PermissionRouteMeta } from './guards'

declare module 'vue-router' {
  interface RouteMeta extends PermissionRouteMeta {
    title?: string
    description?: string
    subsystem?: string
  }
}

const lazyAppHome = () => import('../views/AppHomeView.vue')
const lazyProfile = () => import('../modules/auth/views/ProfileView.vue')
const lazyPublicInfo = () => import('../modules/auth/views/PublicInfoView.vue')

export const routes: readonly RouteRecordRaw[] = [
  {
    path: '/',
    name: 'public-home',
    component: AuthLandingView,
    meta: {
      guestOnly: true,
      title: '登入工作台',
    },
  },
  {
    path: '/register',
    name: 'register',
    component: lazyPublicInfo,
    meta: {
      guestOnly: true,
      title: '申請工作帳號',
      description: '帳號申請流程將由系統管理者另行核發。',
    },
  },
  {
    path: '/forgot-password',
    name: 'forgot-password',
    component: lazyPublicInfo,
    meta: {
      guestOnly: true,
      title: '找回登入方式',
      description: '請聯絡系統管理者協助確認帳號與登入方式。',
    },
  },
  {
    path: '/privacy',
    name: 'privacy',
    component: lazyPublicInfo,
    meta: {
      title: '資料使用說明',
      description: '平台只在已授權的工作範圍中使用案件資料。',
    },
  },
  {
    path: '/app',
    name: 'app',
    component: AppLayout,
    meta: {
      requiresAuth: true,
      title: '工作台',
    },
    children: [
      {
        path: '',
        name: 'app-home',
        component: lazyAppHome,
        meta: {
          requiresAuth: true,
          title: '工作台總覽',
          subsystem: '工作台',
          description: '依目前帳號可用的模組接續工作。',
        },
      },
      {
        path: 'profile',
        name: 'app-profile',
        component: lazyProfile,
        meta: {
          requiresAuth: true,
          title: '帳號設定',
          subsystem: '帳號',
          description: '檢視目前登入帳號與工作權限。',
        },
      },
      {
        path: 'unauthorized',
        name: 'app-unauthorized',
        component: UnauthorizedView,
        meta: {
          requiresAuth: true,
          title: '權限不足',
          subsystem: '權限管理',
        },
      },
      ...valuationRoutes,
      ...reviewRoutes,
      ...historyRoutes,
      ...assistantRoutes,
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

export function createAppRouter(history: RouterHistory = createWebHistory()): ReturnType<typeof createRouter> {
  const router = createRouter({
    history,
    routes: [...routes],
    scrollBehavior: () => ({ top: 0 }),
  })
  router.beforeEach(authGuard)
  return router
}

export const router = createAppRouter()

export default router
