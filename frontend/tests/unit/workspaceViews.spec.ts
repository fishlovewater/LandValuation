import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppHomeView from '../../src/views/AppHomeView.vue'
import ProfileView from '../../src/modules/auth/views/ProfileView.vue'
import { useAuthStore } from '../../src/stores/auth.store'
import type { AuthUser } from '../../src/modules/auth/auth.types'

const appraiser: AuthUser = {
  id: 'user-appraiser',
  username: 'valuation_demo',
  email: 'valuation@example.test',
  displayName: '示範估價人員',
  roles: ['APPRAISER'],
  permissions: ['assistant.use', 'case.read', 'valuation.read', 'valuation.update'],
}

const reviewer: AuthUser = {
  id: 'user-reviewer',
  username: 'review_demo',
  email: 'review@example.test',
  displayName: '示範審查人員',
  roles: ['REVIEWER'],
  permissions: ['case.read', 'review.execute'],
}

function router() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/app/valuation/dashboard', component: { template: '<div />' } },
      { path: '/app/review/dashboard', component: { template: '<div />' } },
      { path: '/app/history/search', component: { template: '<div />' } },
    ],
  })
}

describe('workspace views', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('shows only role-authorized work modules on the app home', async () => {
    const appRouter = router()
    await appRouter.push('/')
    useAuthStore().user = appraiser

    const wrapper = mount(AppHomeView, { global: { plugins: [appRouter] } })

    expect(wrapper.text()).toContain('示範估價人員')
    expect(wrapper.find('[data-testid="home-module-valuation"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="home-module-history"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="home-module-review"]').exists()).toBe(false)
  })

  it('shows the current account, role, and readable work permissions on profile', async () => {
    const appRouter = router()
    await appRouter.push('/')
    useAuthStore().user = reviewer

    const wrapper = mount(ProfileView, { global: { plugins: [appRouter] } })

    expect(wrapper.text()).toContain('示範審查人員')
    expect(wrapper.text()).toContain('review_demo')
    expect(wrapper.text()).toContain('審查人員')
    expect(wrapper.text()).toContain('執行審查')
    expect(wrapper.text()).not.toContain('review.execute')
  })
})
