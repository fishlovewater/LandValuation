import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import AppHeader from '../../src/components/common/AppHeader.vue'
import AppSidebar from '../../src/components/common/AppSidebar.vue'
import AppLayout from '../../src/layouts/AppLayout.vue'
import UnauthorizedView from '../../src/modules/auth/views/UnauthorizedView.vue'
import type { AuthUser } from '../../src/modules/auth/auth.types'
import { useAuthStore } from '../../src/stores/auth.store'
import { tokenService } from '../../src/api/http'

const appraiser: AuthUser = {
  id: 'user-appraiser',
  username: 'appraiser.demo',
  email: 'appraiser@example.test',
  displayName: '示範估價人員',
  roles: ['APPRAISER'],
  permissions: ['assistant.use', 'case.read', 'valuation.read', 'valuation.update'],
}

const reviewer: AuthUser = {
  id: 'user-reviewer',
  username: 'reviewer.demo',
  email: 'reviewer@example.test',
  displayName: '示範審查員',
  roles: ['REVIEWER'],
  permissions: ['case.read', 'review.execute'],
}

const inspector: AuthUser = {
  id: 'user-inspector',
  username: 'inspector.demo',
  email: 'inspector@example.test',
  displayName: '示範稽查人員',
  roles: ['INSPECTOR'],
  permissions: [],
}

function shellRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/app', component: { template: '<div />' } },
      { path: '/app/valuation/dashboard', component: { template: '<div />' } },
      { path: '/app/review/dashboard', component: { template: '<div />' } },
      { path: '/app/history/search', component: { template: '<div />' } },
      { path: '/app/assistant', component: { template: '<div />' } },
      { path: '/app/profile', component: { template: '<div />' } },
    ],
  })
}

function setUser(user: AuthUser): void {
  useAuthStore().user = user
}

function setMobileViewport(): void {
  vi.spyOn(window, 'matchMedia').mockReturnValue({
    matches: false,
    media: '(min-width: 981px)',
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  } as unknown as MediaQueryList)
}

describe('shared application shell', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    tokenService.clear()
    vi.restoreAllMocks()
  })

  it('shows only modules authorized by the current user permissions', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)

    const wrapper = mount(AppSidebar, {
      global: { plugins: [router] },
    })

    expect(wrapper.text()).toContain('估價作業')
    expect(wrapper.text()).toContain('案件歷程')
    expect(wrapper.text()).not.toContain('智能助理')
    expect(wrapper.text()).not.toContain('審查工作台')
  })

  it('does not expose the valuation workspace to reviewer or inspector roles even when they can read valuation evidence', async () => {
    const router = shellRouter()
    await router.push('/')

    setUser({ ...reviewer, permissions: [...reviewer.permissions, 'valuation.read'] })
    const reviewerWrapper = mount(AppSidebar, { global: { plugins: [router] } })
    expect(reviewerWrapper.text()).toContain('審查工作台')
    expect(reviewerWrapper.text()).not.toContain('估價作業')
    reviewerWrapper.unmount()

    setUser({ ...inspector, permissions: ['valuation.read'] })
    const inspectorWrapper = mount(AppSidebar, { global: { plugins: [router] } })
    expect(inspectorWrapper.text()).toContain('案件歷程')
    expect(inspectorWrapper.text()).not.toContain('估價作業')
    inspectorWrapper.unmount()
  })

  it('renders authorized search and AI actions without leaking them to a reviewer', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)
    const appraiserWrapper = mount(AppHeader, { global: { plugins: [router] } })
    expect(appraiserWrapper.get('[data-testid="case-search"]')).toBeTruthy()
    const assistantShortcut = appraiserWrapper.get('[data-testid="assistant-shortcut"]')
    expect(assistantShortcut.attributes('aria-controls')).toBe('global-assistant-drawer')
    expect(assistantShortcut.attributes('aria-expanded')).toBe('false')
    await assistantShortcut.trigger('click')
    expect(appraiserWrapper.emitted('openAssistant')).toHaveLength(1)

    appraiserWrapper.unmount()
    setUser(reviewer)
    const reviewerWrapper = mount(AppHeader, { global: { plugins: [router] } })
    expect(reviewerWrapper.get('[data-testid="case-search"]')).toBeTruthy()
    expect(reviewerWrapper.find('[data-testid="assistant-shortcut"]').exists()).toBe(false)
  })

  it('switches Demo roles from the user menu and lands on the selected workspace', async () => {
    const router = shellRouter()
    await router.push('/app/valuation/dashboard')
    setUser(appraiser)
    const authStore = useAuthStore()
    vi.spyOn(authStore, 'switchDemoRole').mockImplementation(async (role) => {
      authStore.user = role === 'REVIEWER' ? reviewer : role === 'INSPECTOR' ? inspector : appraiser
    })

    const wrapper = mount(AppHeader, { global: { plugins: [router] } })
    expect(wrapper.get('[data-testid="demo-mode-badge"]').text()).toBe('DEMO')
    await wrapper.get('.app-header__user-trigger').trigger('click')

    expect(wrapper.get('[data-testid="demo-switch-appraiser"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="demo-switch-reviewer"]').trigger('click')
    await flushPromises()

    expect(authStore.switchDemoRole).toHaveBeenCalledWith('REVIEWER')
    expect(router.currentRoute.value.path).toBe('/app/review/dashboard')
    expect(authStore.roles).toEqual(['REVIEWER'])
    expect(wrapper.find('.app-header__user-menu').exists()).toBe(false)
  })

  it('keeps case search interactive on mobile with an accessible popover', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)
    const wrapper = mount(AppHeader, {
      attachTo: document.body,
      global: { plugins: [router] },
    })

    const trigger = wrapper.get('[data-testid="case-search-trigger"]')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(trigger.attributes('aria-controls')).toBe('case-search-popover')
    expect(trigger.attributes('type')).toBe('button')

    await trigger.trigger('click')
    await nextTick()
    const popover = wrapper.get('#case-search-popover')
    const input = popover.get('input[type="search"]')
    expect(popover.attributes('role')).toBe('dialog')
    expect(document.activeElement).toBe(input.element)
    expect(input.attributes('type')).toBe('search')

    await input.setValue('HIST-001')
    await input.trigger('keydown', { key: 'Escape' })
    await nextTick()
    expect(wrapper.find('#case-search-popover').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)

    await trigger.trigger('click')
    await nextTick()
    await wrapper.get('#case-search-popover input[type="search"]').setValue('HIST-001')
    await wrapper.get('#case-search-popover form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/app/history/search')
    expect(router.currentRoute.value.query.keyword).toBe('HIST-001')
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('provides an accessible navigation frame and a named main region', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)
    const wrapper = mount(AppLayout, {
      global: { plugins: [router] },
      slots: { default: '<p>工作內容</p>' },
    })

    expect(wrapper.get('header').attributes('aria-label')).toBe('平台標頭')
    expect(wrapper.get('nav').attributes('aria-label')).toBe('系統功能')
    expect(wrapper.get('main').attributes('aria-label')).toBe('主要內容')
    expect(wrapper.get('button[aria-label="開啟功能選單"]').attributes('type')).toBe('button')
  })

  it('uses the verified role contract for History in the sidebar and search action', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(inspector)
    const inspectorSidebar = mount(AppSidebar, { global: { plugins: [router] } })
    const inspectorHeader = mount(AppHeader, { global: { plugins: [router] } })

    expect(inspectorSidebar.text()).toContain('案件歷程')
    expect(inspectorHeader.find('[data-testid="case-search"]').exists()).toBe(true)

    inspectorSidebar.unmount()
    inspectorHeader.unmount()
    setUser({ ...inspector, roles: ['SUPERVISOR'], permissions: ['case.read'] })
    const unauthorizedSidebar = mount(AppSidebar, { global: { plugins: [router] } })
    const unauthorizedHeader = mount(AppHeader, { global: { plugins: [router] } })

    expect(unauthorizedSidebar.text()).not.toContain('案件歷程')
    expect(unauthorizedHeader.find('[data-testid="case-search"]').exists()).toBe(false)
  })

  it('exposes a mobile drawer, traps focus, closes on Escape, and restores trigger focus', async () => {
    setMobileViewport()
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)
    const wrapper = mount(AppLayout, {
      attachTo: document.body,
      global: { plugins: [router] },
      slots: { default: '<p>工作內容</p>' },
    })
    await flushPromises()

    const trigger = wrapper.get('button[aria-label="開啟功能選單"]')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(trigger.attributes('aria-controls')).toBe('app-sidebar')

    await trigger.trigger('click')
    await flushPromises()
    const drawer = wrapper.get('#app-sidebar')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(drawer.attributes('role')).toBe('dialog')
    expect(drawer.attributes('aria-modal')).toBe('true')
    expect(drawer.get('nav').attributes('aria-label')).toBe('系統功能')

    const closeButton = drawer.get('button[aria-label="關閉功能選單"]')
    const links = drawer.findAll('a[href]')
    expect(document.activeElement).toBe(closeButton.element)

    links.at(-1)!.element.focus()
    await drawer.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(closeButton.element)

    closeButton.element.focus()
    await drawer.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(links.at(-1)!.element)

    await drawer.trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(wrapper.find('#app-sidebar').exists()).toBe(false)
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('gives an unknown role a logout action instead of a protected-route loop', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/app/unauthorized', component: UnauthorizedView },
      ],
    })
    await router.push('/app/unauthorized')
    setUser({ ...appraiser, roles: ['UNRECOGNIZED'], permissions: [] })
    tokenService.set('unknown-role-token', 1800)
    const wrapper = mount(UnauthorizedView, { global: { plugins: [router] } })

    expect(wrapper.get('button[aria-label="返回登入"]').text()).toContain('返回登入')
    await wrapper.get('button[aria-label="返回登入"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/')
    expect(useAuthStore().user).toBeNull()
    expect(tokenService.get()).toBeNull()
  })
})
