import { createRouter, createWebHistory } from 'vue-router'

import PublicLayout from '../layouts/PublicLayout.vue'
import AppLayout from '../layouts/AppLayout.vue'
import LoginView from '../modules/auth/views/LoginView.vue'
import UnauthorizedView from '../modules/auth/views/UnauthorizedView.vue'
import { useAuthStore } from '../modules/auth/auth.store'
import { evaluateRouteAccess } from './guards'

const ReviewDashboardPlaceholder = { template: '<section><h1>智慧審查</h1><p>案件工作台載入中。</p></section>' }

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: PublicLayout, children: [{ path: '', component: LoginView }] },
    {
      path: '/app', component: AppLayout, meta: { requiresAuth: true }, children: [
        { path: 'review/dashboard', component: ReviewDashboardPlaceholder, meta: { requiresAuth: true, permission: 'review.execute' } },
        { path: 'unauthorized', component: UnauthorizedView, meta: { requiresAuth: true } },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  return evaluateRouteAccess(
    { path: to.path, fullPath: to.fullPath, meta: { requiresAuth: Boolean(to.meta.requiresAuth), permission: to.meta.permission as string | undefined } },
    auth,
  )
})

export default router