<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../auth.store'
import { homeFor } from '../../../router/guards'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const errorMessage = ref('')

async function submit() {
  loading.value = true
  errorMessage.value = ''
  try {
    await auth.login(username.value, password.value)
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/app/')
      ? route.query.redirect : auth.user ? homeFor(auth.user) : '/app/unauthorized'
    await router.push(redirect)
  } catch {
    errorMessage.value = '登入失敗，請確認帳號與密碼後再試一次。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <form class="login-card" @submit.prevent="submit">
    <div><span class="eyebrow">Reviewer Portal</span><h2>登入智慧審查</h2><p>使用已授權的審查帳號登入。</p></div>
    <label for="username">帳號</label>
    <input id="username" v-model="username" name="username" autocomplete="username" required :aria-invalid="Boolean(errorMessage)" :aria-describedby="errorMessage ? 'login-error' : undefined" />
    <label for="password">密碼</label>
    <div class="password-field"><input id="password" v-model="password" name="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" required :aria-invalid="Boolean(errorMessage)" :aria-describedby="errorMessage ? 'login-error' : undefined" /><button type="button" :aria-label="showPassword ? '隱藏密碼' : '顯示密碼'" @click="showPassword = !showPassword">{{ showPassword ? '隱藏' : '顯示' }}</button></div>
    <p v-if="errorMessage" id="login-error" class="form-error" role="alert">{{ errorMessage }}</p>
    <button class="primary-button" type="submit" :disabled="loading">{{ loading ? '登入中…' : '登入' }}</button>
  </form>
</template>