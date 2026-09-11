<script setup lang="ts">
import { computed } from 'vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { useAuthStore } from '../../../stores/auth.store'

const authStore = useAuthStore()

const user = computed(() => authStore.user)

const roleLabels: Readonly<Record<string, string>> = {
  APPRAISER: '估價人員',
  REVIEWER: '審查人員',
  INSPECTOR: '案件查詢',
  ADMIN: '系統管理員',
  SYSTEM_ADMIN: '系統管理員',
  SUPERADMIN: '系統管理員',
}

const permissionLabels: Readonly<Record<string, string>> = {
  'assistant.use': '使用智能助理',
  'case.read': '查看案件',
  'case.create': '建立案件',
  'case.update': '修改案件',
  'valuation.read': '查看估價資料',
  'valuation.update': '修改估價資料',
  'valuation.submit_review': '送出審查',
  'document.upload': '上傳文件',
  'document.download': '下載文件',
  'review.execute': '執行審查',
  'review.decide': '做出審查決定',
  'knowledge.read': '查詢法規與知識文件',
}

function roleLabel(role: string): string {
  return roleLabels[role] ?? role
}

function permissionLabel(permission: string): string {
  return permissionLabels[permission] ?? '其他工作權限'
}
</script>

<template>
  <section class="profile-view" data-testid="profile-view">
    <PageHeader
      eyebrow="帳號資料"
      title="帳號與工作權限"
      description="查看目前帳號資料、角色與可使用的工作功能。"
    />

    <div class="profile-view__grid">
      <section v-liquid-glass data-lg class="profile-view__card lg" aria-labelledby="profile-account-title">
        <span class="profile-view__eyebrow">帳號</span>
        <h2 id="profile-account-title">帳號資料</h2>
        <dl>
          <div><dt>顯示名稱</dt><dd>{{ user?.displayName || '—' }}</dd></div>
          <div><dt>帳號</dt><dd>{{ user?.username || '—' }}</dd></div>
          <div><dt>電子郵件</dt><dd>{{ user?.email || '—' }}</dd></div>
        </dl>
      </section>

      <section v-liquid-glass data-lg class="profile-view__card lg" aria-labelledby="profile-role-title">
        <span class="profile-view__eyebrow">角色</span>
        <h2 id="profile-role-title">目前角色</h2>
        <div v-if="authStore.roles.length" class="profile-view__chips">
          <span v-for="role in authStore.roles" :key="role">{{ roleLabel(role) }}</span>
        </div>
        <p v-else class="profile-view__empty">目前沒有角色資料。</p>
      </section>
    </div>

    <section v-liquid-glass data-lg class="profile-view__card profile-view__permissions lg" aria-labelledby="profile-permissions-title">
      <div class="profile-view__heading">
        <div>
          <span class="profile-view__eyebrow">可使用功能</span>
          <h2 id="profile-permissions-title">工作權限</h2>
        </div>
        <span>{{ authStore.permissions.length }} 項</span>
      </div>
      <ul v-if="authStore.permissions.length">
        <li v-for="permission in authStore.permissions" :key="permission">
          <strong>{{ permissionLabel(permission) }}</strong>
        </li>
      </ul>
      <p v-else class="profile-view__empty">目前帳號沒有額外工作權限。</p>
    </section>
  </section>
</template>

<style scoped>
.profile-view { padding:0 28px 34px; }
.profile-view__grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:12px; }
.profile-view__card { padding:20px; border:1px solid rgba(255,255,255,.74); border-radius:var(--app-radius-sm); background:rgba(255,255,255,.74); box-shadow:var(--app-shadow-soft); }
.profile-view__eyebrow { color:var(--app-accent-deep); font-size:9px; font-weight:900; letter-spacing:.16em; }
.profile-view__card h2 { margin:5px 0 14px; color:var(--app-ink); font-family:var(--app-font-display); font-size:21px; }
.profile-view__card dl { display:grid; gap:10px; margin:0; }
.profile-view__card dl div { display:grid; gap:3px; padding-bottom:9px; border-bottom:1px solid var(--app-line); }
.profile-view__card dl div:last-child { padding-bottom:0; border-bottom:0; }
.profile-view__card dt { color:var(--app-muted); font-size:10px; font-weight:800; }
.profile-view__card dd { margin:0; overflow-wrap:anywhere; color:var(--app-ink); font-size:13px; font-weight:800; }
.profile-view__chips { display:flex; flex-wrap:wrap; gap:7px; }
.profile-view__chips span { padding:7px 10px; border:1px solid var(--app-line); border-radius:999px; color:var(--app-primary-deep); background:var(--app-primary-soft); font-size:11px; font-weight:900; }
.profile-view__permissions { margin-top:12px; }
.profile-view__heading { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; }
.profile-view__heading > span { color:var(--app-muted); font-size:11px; font-weight:800; }
.profile-view__permissions ul { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px; margin:0; padding:0; list-style:none; }
.profile-view__permissions li { display:grid; gap:5px; padding:12px; border:1px solid var(--app-line); border-radius:9px; background:var(--app-surface-muted); }
.profile-view__permissions strong { color:var(--app-ink); font-size:11px; }
.profile-view__permissions code { overflow-wrap:anywhere; color:var(--app-muted); font-size:10px; }
.profile-view__empty { margin:0; color:var(--app-muted); font-size:12px; line-height:1.6; }
@media (max-width:720px) {
  .profile-view { padding-inline:14px; }
  .profile-view__grid { grid-template-columns:1fr; }
  .profile-view__heading { align-items:flex-start; flex-direction:column; }
}
</style>