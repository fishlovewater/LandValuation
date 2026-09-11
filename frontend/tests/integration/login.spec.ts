import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { authApi } from '../../src/modules/auth/auth.api'
import LoginCard from '../../src/modules/auth/components/LoginCard.vue'
import AuthLandingView from '../../src/modules/auth/views/AuthLandingView.vue'
import { ForbiddenError, tokenService } from '../../src/api/http'
import { createAppRouter } from '../../src/router'

function mountLogin() {
  window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
  return mount(LoginCard, {
    global: { plugins: [createPinia()] },
  })
}

describe('LoginCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    tokenService.clear()
  })

  it('requires both visible fields before sending a request', async () => {
    const login = vi.spyOn(authApi, 'login')
    const wrapper = mountLogin()

    await wrapper.get('form').trigger('submit')

    expect(login).not.toHaveBeenCalled()
    expect(wrapper.get('#login-username').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#login-password').attributes('aria-invalid')).toBe('true')
    expect(wrapper.text()).toContain('請輸入帳號')
    expect(wrapper.text()).toContain('請輸入密碼')
  })

  it('offers three one-click development Demo roles without requiring credentials', async () => {
    const demoLogin = vi.spyOn(authApi, 'demoLogin').mockResolvedValue({
      access_token: 'demo-role-token',
      token_type: 'bearer',
      expires_in: 600,
    })
    vi.spyOn(authApi, 'me').mockResolvedValue({
      id: 'user-appraiser',
      username: 'valuation_demo',
      email: 'valuation@example.test',
      displayName: '示範估價人員',
      roles: ['APPRAISER'],
      permissions: ['valuation.read'],
    })
    const passwordLogin = vi.spyOn(authApi, 'login')
    const wrapper = mountLogin()

    expect(wrapper.findAll('[data-testid^="demo-login-"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('展示時直接選擇角色，不需要輸入帳號密碼')

    await wrapper.get('[data-testid="demo-login-appraiser"]').trigger('click')
    await flushPromises()

    expect(demoLogin).toHaveBeenCalledOnce()
    expect(demoLogin).toHaveBeenCalledWith('APPRAISER')
    expect(passwordLogin).not.toHaveBeenCalled()
    expect(wrapper.emitted('loginSuccess')?.[0]?.[0]).toMatchObject({
      username: 'valuation_demo',
      roles: ['APPRAISER'],
    })
  })

  it('preserves the username and clears the password after incorrect credentials', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue({ response: { status: 401 } })
    const wrapper = mountLogin()
    const username = wrapper.get('#login-username')
    const password = wrapper.get('#login-password')

    await username.setValue('appraiser.demo')
    await password.setValue('wrong-secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect((username.element as HTMLInputElement).value).toBe('appraiser.demo')
    expect((password.element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('帳號或密碼不正確')
    expect(wrapper.text()).not.toContain('wrong-secret')
  })

  it('uses safe messages for disabled accounts and network failures', async () => {
    const login = vi.spyOn(authApi, 'login')
    const wrapper = mountLogin()

    login.mockRejectedValueOnce({ response: { status: 401, data: { detail: '使用者不存在或已停用' } } })
    await wrapper.get('#login-username').setValue('disabled.demo')
    await wrapper.get('#login-password').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('此帳號目前無法登入')
    expect(wrapper.text()).not.toContain('使用者不存在或已停用')

    login.mockRejectedValueOnce(new ForbiddenError())
    await wrapper.get('#login-password').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('此帳號目前無法登入')

    login.mockRejectedValueOnce(new Error('ECONNREFUSED backend-secret'))
    await wrapper.get('#login-password').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('目前無法連線至服務')
    expect(wrapper.text()).not.toContain('ECONNREFUSED')
    expect(wrapper.text()).not.toContain('backend-secret')
  })

  it('shows loading state and prevents a second submit', async () => {
    let resolveLogin: () => void = () => undefined
    const login = vi.spyOn(authApi, 'login').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLogin = () => resolve({ access_token: 'token', token_type: 'bearer', expires_in: 600 })
        }),
    )
    vi.spyOn(authApi, 'me').mockResolvedValue({
      id: 'user-001',
      username: 'appraiser.demo',
      email: 'appraiser@example.test',
      displayName: '示範估價人員',
      roles: ['APPRAISER'],
      permissions: ['valuation.read'],
    })
    const wrapper = mountLogin()
    await wrapper.get('#login-username').setValue('appraiser.demo')
    await wrapper.get('#login-password').setValue('secret')

    const form = wrapper.get('form')
    await form.trigger('submit')
    await form.trigger('submit')

    expect(login).toHaveBeenCalledTimes(1)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('登入中')

    resolveLogin()
    await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('supports labelled autocomplete fields, password visibility, and Enter submission', async () => {
    const login = vi.spyOn(authApi, 'login').mockResolvedValue({
      access_token: 'token',
      token_type: 'bearer',
      expires_in: 600,
    })
    vi.spyOn(authApi, 'me').mockResolvedValue({
      id: 'user-001',
      username: 'reviewer.demo',
      email: 'reviewer@example.test',
      displayName: '示範審查員',
      roles: ['REVIEWER'],
      permissions: ['review.execute'],
    })
    const wrapper = mountLogin()
    const username = wrapper.get('#login-username')
    const password = wrapper.get('#login-password')

    expect(username.attributes('autocomplete')).toBe('username')
    expect(password.attributes('autocomplete')).toBe('current-password')
    expect(wrapper.get('label[for="login-username"]').text()).toContain('帳號')
    expect(wrapper.get('label[for="login-password"]').text()).toContain('密碼')
    expect(wrapper.get('[aria-label="顯示密碼"]').exists()).toBe(true)

    await wrapper.get('#toggle-password').trigger('click')
    expect(password.attributes('type')).toBe('text')
    expect(wrapper.get('[aria-label="隱藏密碼"]').exists()).toBe(true)

    await username.setValue('reviewer.demo')
    await password.setValue('secret')
    await password.trigger('keydown', { key: 'Enter' })
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(login).toHaveBeenCalledWith({ username: 'reviewer.demo', password: 'secret' })
    expect(login).toHaveBeenCalledTimes(1)
  })

  it('renders the public fold content and focuses the username after the hero action', async () => {
    window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
    const wrapper = mount(AuthLandingView, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    })

    expect(wrapper.findAll('.value-card')).toHaveLength(4)
    expect(wrapper.findAll('.process-step')).toHaveLength(3)
    await wrapper.get('.hero__actions button').trigger('click')
    await nextTick()

    expect(document.activeElement?.id).toBe('login-username')
    wrapper.unmount()
  })

  it.each(['/register', '/forgot-password', '/privacy'])(
    'routes the public %s login CTA to the login form and focuses the username',
    async (path) => {
      window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
      const router = createAppRouter(createMemoryHistory())
      await router.push(path)
      await router.isReady()
      const wrapper = mount(RouterView, {
        attachTo: document.body,
        global: { plugins: [router, createPinia()] },
      })
      await flushPromises()

      await wrapper.get('.public-nav__cta').trigger('click')
      await flushPromises()

      expect(router.currentRoute.value.path).toBe('/')
      expect(document.activeElement?.id).toBe('login-username')
      wrapper.unmount()
      document.body.innerHTML = ''
    },
  )

  it('ignores an external login redirect and uses the authenticated role home', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: AuthLandingView },
        { path: '/app/valuation/dashboard', component: { template: '<div />' } },
      ],
    })
    await router.push({ path: '/', query: { redirect: 'https://attacker.example/steal' } })
    const wrapper = mount(RouterView, {
      attachTo: document.body,
      global: { plugins: [router, createPinia()] },
    })
    vi.spyOn(authApi, 'login').mockResolvedValue({
      access_token: 'redirect-test-token',
      token_type: 'bearer',
      expires_in: 1800,
    })
    vi.spyOn(authApi, 'me').mockResolvedValue({
      id: 'user-appraiser',
      username: 'appraiser.demo',
      email: 'appraiser@example.test',
      displayName: '示範估價人員',
      roles: ['APPRAISER'],
      permissions: ['valuation.read'],
    })

    await wrapper.get('#login-username').setValue('appraiser.demo')
    await wrapper.get('#login-password').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/app/valuation/dashboard')
    expect(router.currentRoute.value.fullPath).not.toContain('attacker.example')
    wrapper.unmount()
    document.body.innerHTML = ''
  })
})
