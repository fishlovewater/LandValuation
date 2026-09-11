<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { authApi } from '../auth.api'
import type { DemoLoginRole } from '../auth.types'

const form = reactive({
  displayName: '',
  username: '',
  email: '',
  role: 'APPRAISER' as DemoLoginRole,
  reason: '',
})
const busy = ref(false)
const error = ref('')
const success = ref('')

async function submit(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    const result = await authApi.requestAccount({
      username: form.username.trim(),
      email: form.email.trim(),
      display_name: form.displayName.trim(),
      requested_role: form.role,
      reason: form.reason.trim() || null,
    })
    success.value = `${result.message} 申請編號：${result.request_id}`
  } catch {
    error.value = '帳號申請送出失敗；請確認欄位內容，或稍後再試。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="auth-self-service">
    <section class="auth-self-service__panel">
      <RouterLink class="auth-self-service__back" to="/">← 返回登入</RouterLink>
      <p class="auth-self-service__eyebrow">工作帳號申請</p>
      <h1>申請工作帳號</h1>
      <p class="auth-self-service__intro">工作帳號不會自動建立。送出後由系統管理者審核角色與工作範圍，避免未授權人員取得案件資料。</p>

      <form data-testid="registration-request-form" @submit.prevent="submit">
        <label>姓名 / 顯示名稱<input v-model="form.displayName" required maxlength="200" autocomplete="name"></label>
        <label>希望使用的帳號<input v-model="form.username" required minlength="3" maxlength="100" pattern="[A-Za-z0-9._-]+" autocomplete="username"></label>
        <label>電子郵件<input v-model="form.email" required type="email" maxlength="320" autocomplete="email"></label>
        <label>申請角色
          <select v-model="form.role">
            <option value="APPRAISER">估價人員</option>
            <option value="REVIEWER">審查人員</option>
            <option value="INSPECTOR">案件查詢人員</option>
          </select>
        </label>
        <label class="is-wide">用途說明（選填）<textarea v-model="form.reason" maxlength="1000" rows="4" placeholder="例如：負責土地徵收補償市價查估案件"></textarea></label>
        <p v-if="error" class="auth-self-service__message is-error" role="alert">{{ error }}</p>
        <p v-if="success" class="auth-self-service__message is-success" role="status">{{ success }}</p>
        <button type="submit" :disabled="busy">{{ busy ? '送出中…' : '送出帳號申請' }}</button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.auth-self-service { min-height:100vh; display:grid; place-items:center; padding:32px 18px; background:linear-gradient(145deg,#eef4f9,#f8fafc); }
.auth-self-service__panel { width:min(760px,100%); padding:32px; border:1px solid #d7e1ec; border-radius:18px; background:#fff; box-shadow:0 18px 48px rgba(20,47,78,.10); }
.auth-self-service__back { color:#345879; font-size:13px; font-weight:800; text-decoration:none; }
.auth-self-service__eyebrow { margin:28px 0 6px; color:#2d6798; font-size:11px; font-weight:900; letter-spacing:.14em; }
h1 { margin:0; color:#17283d; font-size:30px; }
.auth-self-service__intro { color:#60738a; line-height:1.7; }
form { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin-top:24px; }
label { display:grid; gap:7px; color:#344860; font-size:12px; font-weight:800; }
label.is-wide,.auth-self-service__message,button { grid-column:1/-1; }
input,select,textarea { width:100%; box-sizing:border-box; border:1px solid #b9cadb; border-radius:9px; padding:11px 12px; color:#1f2f46; background:#fff; font:inherit; font-weight:600; }
input:focus,select:focus,textarea:focus { outline:3px solid rgba(41,105,161,.13); border-color:#2969a1; }
button { min-height:46px; border:0; border-radius:9px; color:#fff; background:#1f639f; font-weight:900; cursor:pointer; }
button:disabled { opacity:.55; cursor:not-allowed; }
.auth-self-service__message { margin:0; padding:11px 12px; border-radius:8px; font-size:12px; }
.auth-self-service__message.is-error { color:#922f2b; background:#fff0ef; }
.auth-self-service__message.is-success { color:#236a4c; background:#edf8f2; }
@media (max-width:640px){.auth-self-service__panel{padding:22px}form{grid-template-columns:1fr}.is-wide,.auth-self-service__message,button{grid-column:auto}}
</style>
