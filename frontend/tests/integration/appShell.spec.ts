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
import { assistantApi } from '../../src/modules/assistant/assistant.api'

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
      { path: '/app/assistant', name: 'assistant', component: { template: '<div />' } },
      { path: '/app/profile', component: { template: '<div />' } },
    ],
  })
}

function setUser(user: AuthUser): void {
  useAuthStore().user = user
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
    expect(appraiserWrapper.get('[data-testid="case-search-trigger"]')).toBeTruthy()
    expect(appraiserWrapper.get('[data-testid="history-shortcut"]').attributes('aria-label')).toBe('案件紀錄')
    const assistantShortcut = appraiserWrapper.get('[data-testid="assistant-shortcut"]')
    expect(assistantShortcut.attributes('aria-controls')).toBe('global-assistant-drawer')
    expect(assistantShortcut.attributes('aria-expanded')).toBe('false')
    await assistantShortcut.trigger('click')
    expect(appraiserWrapper.emitted('openAssistant')).toHaveLength(1)

    appraiserWrapper.unmount()
    setUser(reviewer)
    const reviewerWrapper = mount(AppHeader, { global: { plugins: [router] } })
    expect(reviewerWrapper.get('[data-testid="case-search-trigger"]')).toBeTruthy()
    expect(reviewerWrapper.get('[data-testid="history-shortcut"]').exists()).toBe(true)
    expect(reviewerWrapper.find('[data-testid="assistant-shortcut"]').exists()).toBe(false)
  })

  it('keeps Demo account identity visible without exposing a subsystem role switcher', async () => {
    const router = shellRouter()
    await router.push('/app/valuation/dashboard')
    setUser(appraiser)

    const wrapper = mount(AppHeader, { global: { plugins: [router] } })
    expect(wrapper.get('[data-testid="demo-mode-badge"]').text()).toBe('示範')
    expect(wrapper.get('[data-testid="demo-role-stage"]').text()).toBe('估價人員')
    await wrapper.get('.app-header__user-trigger').trigger('click')

    expect(wrapper.find('[data-testid="demo-switch-appraiser"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="demo-switch-reviewer"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="demo-switch-inspector"]').exists()).toBe(false)
    expect(wrapper.get('.app-header__user-menu').text()).toContain('示範估價人員')
    expect(router.currentRoute.value.path).toBe('/app/valuation/dashboard')
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

  it('provides an accessible icon toolbar and a named main region without a persistent sidebar', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)
    const wrapper = mount(AppLayout, {
      global: { plugins: [router] },
      slots: { default: '<p>工作內容</p>' },
    })

    expect(wrapper.get('header').attributes('aria-label')).toBe('平台標頭')
    expect(wrapper.get('main').attributes('aria-label')).toBe('主要內容')
    expect(wrapper.find('#app-sidebar').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="開啟功能選單"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="case-search-trigger"]').attributes('aria-label')).toBe('搜尋案件')
    expect(wrapper.get('[data-testid="history-shortcut"]').attributes('aria-label')).toBe('案件紀錄')
    expect(wrapper.get('[data-testid="assistant-shortcut"]').attributes('aria-label')).toBe('開啟 AI 助手')
  })

  it('uses the verified role contract for History in the header actions', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(inspector)
    const inspectorSidebar = mount(AppSidebar, { global: { plugins: [router] } })
    const inspectorHeader = mount(AppHeader, { global: { plugins: [router] } })

    expect(inspectorSidebar.text()).toContain('案件歷程')
    expect(inspectorHeader.find('[data-testid="case-search-trigger"]').exists()).toBe(true)
    expect(inspectorHeader.find('[data-testid="history-shortcut"]').exists()).toBe(true)

    inspectorSidebar.unmount()
    inspectorHeader.unmount()
    setUser({ ...inspector, roles: ['SUPERVISOR'], permissions: ['case.read'] })
    const unauthorizedSidebar = mount(AppSidebar, { global: { plugins: [router] } })
    const unauthorizedHeader = mount(AppHeader, { global: { plugins: [router] } })

    expect(unauthorizedSidebar.text()).not.toContain('案件歷程')
    expect(unauthorizedHeader.find('[data-testid="case-search-trigger"]').exists()).toBe(false)
    expect(unauthorizedHeader.find('[data-testid="history-shortcut"]').exists()).toBe(false)
  })

  it('keeps the compact header actions available without restoring the removed sidebar', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)
    const wrapper = mount(AppLayout, {
      attachTo: document.body,
      global: { plugins: [router] },
      slots: { default: '<p>工作內容</p>' },
    })
    await flushPromises()

    expect(wrapper.find('#app-sidebar').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="開啟功能選單"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="case-search-trigger"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="history-shortcut"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="assistant-shortcut"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('opens the AI assistant as a non-modal floating window over the workspace', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser(appraiser)
    vi.spyOn(assistantApi, 'listKnowledgeConversations').mockResolvedValue([{
      conversation_id: 'shell-conversation-1',
      case_id: null,
      review_id: null,
      finding_id: null,
      workspace: null,
      title: '一般對話',
      provider: 'demo',
      model_id: 'demo-model',
      status: 'ACTIVE',
      created_at: '2026-09-12T02:00:00Z',
      updated_at: '2026-09-12T03:00:00Z',
    }])
    vi.spyOn(assistantApi, 'getKnowledgeConversationMessages').mockResolvedValue([])
    const wrapper = mount(AppLayout, {
      attachTo: document.body,
      global: { plugins: [router] },
      slots: { default: '<button id="workspace-action">工作區操作</button>' },
    })

    await wrapper.get('[data-testid="assistant-shortcut"]').trigger('click')
    await nextTick()

    const floating = document.querySelector<HTMLElement>('[data-testid="assistant-floating-window"]')
    expect(floating).not.toBeNull()
    expect(floating?.getAttribute('aria-modal')).toBeNull()
    expect(document.querySelector('.glass-drawer-backdrop')).toBeNull()
    expect(document.querySelector('#workspace-action')).not.toBeNull()

    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('loads account conversation history without exposing a manual assistant mode switch', async () => {
    const router = shellRouter()
    await router.push('/')
    setUser({ ...appraiser, permissions: [...appraiser.permissions, 'knowledge.read'] })
    vi.spyOn(assistantApi, 'listKnowledgeConversations').mockResolvedValue([{
      conversation_id: 'knowledge-conversation-1',
      title: '土地徵收估價規定',
      provider: 'demo',
      model_id: 'demo-model',
      status: 'ACTIVE',
      created_at: '2026-09-12T02:00:00Z',
      updated_at: '2026-09-12T03:00:00Z',
    }])
    vi.spyOn(assistantApi, 'getKnowledgeConversationMessages').mockResolvedValue([])

    const wrapper = mount(AppLayout, {
      attachTo: document.body,
      global: { plugins: [router] },
    })
    await wrapper.get('[data-testid="assistant-shortcut"]').trigger('click')
    await vi.waitFor(() => {
      expect(document.querySelector('[data-testid="assistant-floating-window"]')?.textContent)
        .toContain('依問題自動判斷資料來源')
    })

    expect(document.querySelector('[data-testid="assistant-mode-knowledge"]')).toBeNull()
    expect(document.querySelector('[data-testid="assistant-mode-case"]')).toBeNull()
    document.querySelector<HTMLButtonElement>('button[aria-label="歷史對話"]')?.click()
    await vi.waitFor(() => {
      expect(document.querySelector('#assistant-history-popover')?.textContent).toContain('土地徵收估價規定')
    })

    wrapper.unmount()
    document.body.innerHTML = ''
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
