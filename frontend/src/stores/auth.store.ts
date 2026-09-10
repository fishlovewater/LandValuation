import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'
import { registerUnauthorizedHandler, tokenService } from '../api/http'
import { authApi } from '../modules/auth/auth.api'
import type { AuthUser, LoginCredentials } from '../modules/auth/auth.types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const isSubmitting = ref(false)
  const isAuthenticated = computed(() => user.value !== null)
  const roles = computed(() => user.value?.roles ?? [])
  const permissions = computed(() => user.value?.permissions ?? [])
  let restorePromise: Promise<boolean> | null = null
  let restoreToken: string | null = null
  let restoreGeneration: number | null = null
  let authenticatedToken: string | null = null
  let sessionGeneration = 0

  function invalidatePendingSession(): void {
    sessionGeneration += 1
    restorePromise = null
    restoreToken = null
    restoreGeneration = null
    authenticatedToken = null
  }

  function clearSession(): void {
    invalidatePendingSession()
    tokenService.clear()
    user.value = null
  }

  const disposeUnauthorizedHandler = registerUnauthorizedHandler(clearSession)
  onScopeDispose(disposeUnauthorizedHandler)

  async function login(credentials: LoginCredentials): Promise<void> {
    if (isSubmitting.value) return
    isSubmitting.value = true
    invalidatePendingSession()
    tokenService.clear()
    user.value = null
    const requestGeneration = sessionGeneration
    try {
      const token = await authApi.login(credentials)
      if (sessionGeneration !== requestGeneration) return
      tokenService.set(token.access_token, token.expires_in)
      const accessToken = tokenService.get()
      if (!accessToken) throw new Error('登入憑證已失效')
      const currentUser = await authApi.me()
      if (sessionGeneration !== requestGeneration || tokenService.get() !== accessToken) return
      user.value = currentUser
      authenticatedToken = accessToken
    } catch (error: unknown) {
      if (sessionGeneration === requestGeneration) clearSession()
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  function logout(): void {
    clearSession()
  }

  async function restoreSession(): Promise<boolean> {
    const token = tokenService.get()
    if (!token) {
      clearSession()
      return false
    }

    if (user.value && authenticatedToken === token) return true
    if (user.value && authenticatedToken !== token) {
      invalidatePendingSession()
      user.value = null
    }

    if (restorePromise && restoreToken === token && restoreGeneration === sessionGeneration) {
      return restorePromise
    }

    const requestGeneration = sessionGeneration
    const requestToken = token
    let request: Promise<boolean>

    request = Promise.resolve()
      .then(() => authApi.me())
      .then((currentUser) => {
        if (sessionGeneration !== requestGeneration || tokenService.get() !== requestToken) return false
        user.value = currentUser
        authenticatedToken = requestToken
        return true
      })
      .catch(() => {
        if (sessionGeneration === requestGeneration && tokenService.get() === requestToken) clearSession()
        return false
      })
      .finally(() => {
        if (restorePromise === request) {
          restorePromise = null
          restoreToken = null
          restoreGeneration = null
        }
      })

    restorePromise = request
    restoreToken = requestToken
    restoreGeneration = requestGeneration
    return request
  }

  return {
    user,
    isSubmitting,
    isAuthenticated,
    roles,
    permissions,
    login,
    logout,
    restoreSession,
  }
})
