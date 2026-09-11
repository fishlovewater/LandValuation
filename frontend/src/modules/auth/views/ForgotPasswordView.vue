<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { authApi } from '../auth.api'

const route = useRoute()
const account = ref('')
const token = ref(typeof route.query.token === 'string' ? route.query.token : '')
const newPassword = ref('')
const confirmPassword = ref('')
const busy = ref(false)
const message = ref('')
const error = ref('')

async function requestReset(): Promise<void> {
  if (busy.value) return
  busy.value = true
  message.value = ''
  error.value = ''
  try {
    const result = await authApi.requestPasswordReset(account.value.trim())
    message.value = result.message
    if (result.debug_token) {
      token.value = result.debug_token
      message.value += ' 測試環境已自動填入一次性驗證碼。'
    }
  } catch {
    error.value = '密碼重設要求暫時無法送出，請稍後再試。'
  } finally {
    busy.value = false
  }
}

async function confirmReset(): Promise<void> {
  if (busy.value) return
  error.value = ''
  message.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = '兩次輸入的新密碼不一致。'
    return
  }
  busy.value = true
  try {
    const result = await authApi.confirmPasswordReset(token.value.trim(), newPassword.value)
    message.value = result.message
    newPassword.value = ''
    confirmPassword.value = ''
  } catch {
    error.value = '這組一次性驗證碼無效、已使用或已過期，請重新申請。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="auth-self-service">
    <section class="auth-self-service__panel">
      <RouterLink class="auth-self-service__back" to="/">← 返回登入</RouterLink>
      <p class="auth-self-service__eyebrow">密碼重設</p>
      <h1>重設登入密碼</h1>
      <p class="auth-self-service__intro">先以帳號或電子郵件申請一次性驗證碼。為保護帳號安全，系統不會透露該帳號是否存在；驗證碼使用後立即失效。</p>

      <form data-testid="password-reset-request-form" @submit.prevent="requestReset">
        <label>帳號或電子郵件<input v-model="account" required maxlength="320" autocomplete="username"></label>
        <button type="submit" :disabled="busy">{{ busy ? '處理中…' : '建立密碼重設要求' }}</button>
      </form>

      <hr>
      <h2>使用一次性驗證碼設定新密碼</h2>
      <p class="auth-self-service__hint">驗證碼會透過系統設定的通知方式提供；請勿將驗證碼交給他人。</p>
      <form data-testid="password-reset-confirm-form" @submit.prevent="confirmReset">
        <label>一次性驗證碼<input v-model="token" required minlength="32" maxlength="256" autocomplete="one-time-code"></label>
        <label>新密碼<input v-model="newPassword" required type="password" minlength="12" maxlength="256" autocomplete="new-password"></label>
        <label>再次輸入新密碼<input v-model="confirmPassword" required type="password" minlength="12" maxlength="256" autocomplete="new-password"></label>
        <button type="submit" :disabled="busy">{{ busy ? '處理中…' : '更新密碼' }}</button>
      </form>
      <p v-if="error" class="auth-self-service__message is-error" role="alert">{{ error }}</p>
      <p v-if="message" class="auth-self-service__message is-success" role="status">{{ message }}</p>
    </section>
  </main>
</template>

<style scoped>
.auth-self-service { min-height:100vh; display:grid; place-items:center; padding:32px 18px; background:linear-gradient(145deg,#eef4f9,#f8fafc); }
.auth-self-service__panel { width:min(720px,100%); padding:32px; border:1px solid #d7e1ec; border-radius:18px; background:#fff; box-shadow:0 18px 48px rgba(20,47,78,.10); }
.auth-self-service__back { color:#345879; font-size:13px; font-weight:800; text-decoration:none; }
.auth-self-service__eyebrow { margin:28px 0 6px; color:#2d6798; font-size:11px; font-weight:900; letter-spacing:.14em; }
h1,h2 { color:#17283d; } h1{margin:0;font-size:30px} h2{font-size:18px;margin:0 0 8px}
.auth-self-service__intro,.auth-self-service__hint { color:#60738a; line-height:1.7; }
form { display:grid; gap:14px; margin-top:22px; }
label { display:grid; gap:7px; color:#344860; font-size:12px; font-weight:800; }
input { width:100%; box-sizing:border-box; border:1px solid #b9cadb; border-radius:9px; padding:11px 12px; color:#1f2f46; background:#fff; font:inherit; font-weight:600; }
input:focus { outline:3px solid rgba(41,105,161,.13); border-color:#2969a1; }
button { min-height:46px; border:0; border-radius:9px; color:#fff; background:#1f639f; font-weight:900; cursor:pointer; }
button:disabled { opacity:.55; cursor:not-allowed; }
hr { margin:30px 0; border:0; border-top:1px solid #dfe6ee; }
.auth-self-service__message { margin:14px 0 0; padding:11px 12px; border-radius:8px; font-size:12px; }
.auth-self-service__message.is-error { color:#922f2b; background:#fff0ef; }
.auth-self-service__message.is-success { color:#236a4c; background:#edf8f2; }
@media (max-width:640px){.auth-self-service__panel{padding:22px}}
</style>
