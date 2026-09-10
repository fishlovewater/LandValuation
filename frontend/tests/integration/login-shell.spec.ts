import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LoginView from '../../src/modules/auth/views/LoginView.vue'
import AppSidebar from '../../src/components/common/AppSidebar.vue'
import { useAuthStore } from '../../src/modules/auth/auth.store'

describe('login and app shell', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('submits accessible credentials and exposes password visibility control', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'login').mockResolvedValue()
    const wrapper = mount(LoginView, { global: { stubs: { RouterLink: true } } })
    await wrapper.get('#username').setValue('reviewer')
    await wrapper.get('#password').setValue('secret')
    expect(wrapper.get('#username').attributes('autocomplete')).toBe('username')
    expect(wrapper.get('#password').attributes('autocomplete')).toBe('current-password')
    await wrapper.get('form').trigger('submit')
    expect(store.login).toHaveBeenCalledWith('reviewer', 'secret')
  })

  it('shows Review navigation only to users with review.execute', () => {
    const allowed = mount(AppSidebar, { props: { permissions: ['review.execute'] }, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    const denied = mount(AppSidebar, { props: { permissions: [] }, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(allowed.text()).toContain('智慧審查')
    expect(denied.text()).not.toContain('智慧審查')
  })
})