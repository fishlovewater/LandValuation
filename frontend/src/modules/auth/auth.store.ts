import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { setUnauthorizedHandler } from '../../api/http'
import { clearAccessToken, readAccessToken, writeAccessToken } from '../../utils/storage'
import { authApi } from './auth.api'
import type { AuthUser } from './auth.types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const initialized = ref(false)
  const isAuthenticated = computed(() => Boolean(readAccessToken() && user.value))

  function clearSession(): void {
    clearAccessToken()
    user.value = null
    initialized.value = true
  }

  setUnauthorizedHandler(clearSession)

  async function login(username: string, password: string): Promise<void> {
    const token = await authApi.login(username, password)
    writeAccessToken(token.accessToken)
    try {
      user.value = await authApi.me()
      initialized.value = true
    } catch (error) {
      clearSession()
      throw error
    }
  }

  async function restore(): Promise<void> {
    if (initialized.value) return
    if (!readAccessToken()) {
      initialized.value = true
      return
    }
    try {
      user.value = await authApi.me()
    } catch {
      clearSession()
    } finally {
      initialized.value = true
    }
  }

  return { user, initialized, isAuthenticated, login, restore, clearSession }
})