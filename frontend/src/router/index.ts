import { createRouter, createWebHistory } from 'vue-router'

import PublicLayout from '../layouts/PublicLayout.vue'
import AppLayout from '../layouts/AppLayout.vue'
import LoginView from '../modules/auth/views/LoginView.vue'
import UnauthorizedView from '../modules/auth/views/UnauthorizedView.vue'
import { useAuthStore } from '../modules/auth/auth.store'
import { evaluateRouteAccess } from './guards'
import { reviewRoutes } from '../modules/review/review.routes'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: PublicLayout, children: [{ path: '', component: LoginView }] },
    {
      path: '/app', component: AppLayout, meta: { requiresAuth: true }, children: [
        ...reviewRoutes,
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