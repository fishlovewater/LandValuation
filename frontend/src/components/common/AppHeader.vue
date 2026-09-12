<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  PhClockCounterClockwise as History,
  PhMagnifyingGlass as MagnifyingGlass,
  PhSignOut as SignOut,
  PhSparkle as Sparkle,
  PhUserCircle as UserCircle,
} from '@phosphor-icons/vue'
import { isDemoQuickLoginEnabled } from '../../config/environment'
import { hasHistoryRole } from '../../router/roleAccess'
import { useAuthStore } from '../../stores/auth.store'

defineOptions({ inheritAttrs: false })

const emit = defineEmits<{
  openAssistant: []
}>()

withDefaults(
  defineProps<{
    assistantOpen?: boolean
  }>(),
  { assistantOpen: false },
)

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const searchTerm = ref('')
const searchOpen = ref(false)
const searchInput = ref<HTMLInputElement | null>(null)
const searchTrigger = ref<HTMLButtonElement | null>(null)
const userMenuOpen = ref(false)

const demoQuickLoginEnabled = isDemoQuickLoginEnabled(import.meta.env)

const currentSubsystem = computed(() => {
  const subsystem = route.meta.subsystem
  return typeof subsystem === 'string' ? subsystem : '工作台'
})
const canSearchCases = computed(() => hasHistoryRole(authStore.roles))
const canUseAssistant = computed(() => authStore.permissions.includes('assistant.use'))
const displayName = computed(() => authStore.user?.displayName || '目前使用者')
const currentRoleLabel = computed(() => {
  if (authStore.roles.includes('APPRAISER')) return '估價人員'
  if (authStore.roles.includes('REVIEWER')) return '審查人員'
  if (authStore.roles.includes('INSPECTOR')) return '案件查詢'
  return currentSubsystem.value
})

function searchCases(): void {
  if (!canSearchCases.value) return
  const keyword = searchTerm.value.trim()
  closeSearch()
  void router.push({
    path: '/app/history/search',
    query: keyword ? { keyword } : undefined,
  })
}

function openSearch(): void {
  if (!canSearchCases.value) return
  searchOpen.value = true
  userMenuOpen.value = false
  void nextTick(() => searchInput.value?.focus())
}

function closeSearch(): void {
  if (!searchOpen.value) return
  searchOpen.value = false
  void nextTick(() => searchTrigger.value?.focus())
}

function toggleUserMenu(): void {
  searchOpen.value = false
  userMenuOpen.value = !userMenuOpen.value
}

function closeUserMenu(): void {
  userMenuOpen.value = false
}

function logout(): void {
  closeUserMenu()
  authStore.logout()
  void router.replace({ path: '/' })
}
</script>

<template>
  <header class="app-header" aria-label="平台標頭">
    <RouterLink class="app-header__brand" to="/app" aria-label="估價審查中台工作台首頁">
      <span class="app-header__mark" aria-hidden="true">估</span>
      <span class="app-header__brand-copy">
        <span class="app-header__brand-title">
          <strong>土地徵收補償市價查估系統</strong>
          <span v-if="demoQuickLoginEnabled" class="app-header__demo-badge" data-testid="demo-mode-badge">示範</span>
          <span v-if="demoQuickLoginEnabled" class="app-header__demo-stage" data-testid="demo-role-stage">
            {{ currentRoleLabel }}
          </span>
        </span>
        <small>{{ currentSubsystem }}</small>
      </span>
    </RouterLink>

    <div class="app-header__actions" @keydown.esc="searchOpen ? closeSearch() : closeUserMenu()">
      <button
        v-if="canSearchCases"
        ref="searchTrigger"
        class="app-header__icon-button"
        data-testid="case-search-trigger"
        type="button"
        title="搜尋"
        aria-label="搜尋案件"
        aria-controls="case-search-popover"
        :aria-expanded="searchOpen ? 'true' : 'false'"
        @click="openSearch"
      >
        <MagnifyingGlass :size="20" weight="bold" aria-hidden="true" />
      </button>

      <RouterLink
        v-if="canSearchCases"
        class="app-header__icon-button"
        data-testid="history-shortcut"
        to="/app/history/search"
        title="案件紀錄"
        aria-label="案件紀錄"
      >
        <History :size="20" weight="bold" aria-hidden="true" />
      </RouterLink>

      <button
        v-if="canUseAssistant"
        class="app-header__icon-button app-header__icon-button--assistant"
        data-testid="assistant-shortcut"
        type="button"
        title="AI 助手"
        aria-label="開啟 AI 助手"
        aria-controls="global-assistant-drawer"
        :aria-expanded="assistantOpen ? 'true' : 'false'"
        @click="emit('openAssistant')"
      >
        <Sparkle :size="20" weight="fill" aria-hidden="true" />
      </button>

      <div class="app-header__user">
        <button
          class="app-header__icon-button app-header__user-trigger"
          type="button"
          title="帳號"
          :aria-expanded="userMenuOpen ? 'true' : 'false'"
          aria-haspopup="menu"
          aria-label="開啟使用者選單"
          @click="toggleUserMenu"
        >
          <UserCircle :size="23" weight="bold" aria-hidden="true" />
        </button>

        <div v-if="userMenuOpen" class="app-header__user-menu" role="menu">
          <div class="app-header__account-summary">
            <strong>{{ displayName }}</strong>
            <small>{{ currentRoleLabel }}</small>
          </div>

          <RouterLink to="/app/profile" role="menuitem" @click="closeUserMenu">帳號設定</RouterLink>
          <button type="button" role="menuitem" @click="logout">
            <SignOut :size="17" aria-hidden="true" />
            登出
          </button>
        </div>
      </div>

      <div
        v-if="searchOpen"
        id="case-search-popover"
        class="app-header__search-popover"
        role="dialog"
        aria-label="搜尋案件"
      >
        <form class="app-header__search-popover-form" role="search" @submit.prevent="searchCases">
          <label for="app-case-search">搜尋案件</label>
          <div class="app-header__search-field">
            <MagnifyingGlass :size="18" aria-hidden="true" />
            <input
              id="app-case-search"
              ref="searchInput"
              v-model="searchTerm"
              type="search"
              placeholder="案件編號、案件名稱或關鍵字"
              autocomplete="off"
            />
          </div>
          <div class="app-header__search-popover-actions">
            <button type="button" @click="closeSearch">取消</button>
            <button type="submit">搜尋</button>
          </div>
        </form>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  z-index: 30;
  top: 12px;
  display: flex;
  width: min(1760px, 100%);
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin: 0 auto;
  padding: 7px 9px 7px 14px;
  border: 1px solid #183f6b;
  border-radius: 12px;
  background: var(--app-primary-deep);
  box-shadow: 0 8px 22px rgba(18, 59, 104, .16);
}

.app-header__brand,
.app-header__brand-title,
.app-header__actions,
.app-header__icon-button {
  display: flex;
  align-items: center;
}

.app-header__brand {
  min-width: 0;
  gap: 10px;
  color: #fff;
  text-decoration: none;
}

.app-header__mark {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  place-items: center;
  border-radius: 9px;
  color: #fff;
  background: var(--app-highlight);
  font-family: var(--app-font-display);
  font-size: 16px;
  font-weight: 800;
}

.app-header__brand-copy {
  display: grid;
  min-width: 0;
  gap: 1px;
}

.app-header__brand-title {
  min-width: 0;
  gap: 7px;
}

.app-header__brand-title strong {
  overflow: hidden;
  font-size: 13px;
  letter-spacing: .02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-header__brand-copy > small {
  color: rgba(255,255,255,.68);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .12em;
}

.app-header__demo-badge,
.app-header__demo-stage {
  flex: 0 0 auto;
  padding: 2px 6px;
  border: 1px solid rgba(255,255,255,.2);
  border-radius: 999px;
  color: rgba(255,255,255,.9);
  background: rgba(255,255,255,.08);
  font-size: 8px;
  font-weight: 900;
  white-space: nowrap;
}

.app-header__actions {
  position: relative;
  flex: 0 0 auto;
  gap: 4px;
}

.app-header__icon-button {
  width: 42px;
  height: 42px;
  justify-content: center;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 9px;
  color: rgba(255,255,255,.88);
  background: transparent;
  cursor: pointer;
  text-decoration: none;
  transition: background 130ms ease, border-color 130ms ease, color 130ms ease;
}

.app-header__icon-button:hover,
.app-header__icon-button:focus-visible,
.app-header__icon-button.router-link-active {
  border-color: rgba(255,255,255,.15);
  outline: 0;
  color: #fff;
  background: rgba(255,255,255,.12);
}

.app-header__icon-button--assistant {
  color: #ffe2a8;
}

.app-header__user {
  position: relative;
}

.app-header__search-popover {
  position: absolute;
  z-index: 45;
  top: calc(100% + 10px);
  right: 132px;
  width: min(380px, calc(100vw - 32px));
  padding: 14px;
  border: 1px solid var(--app-line);
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(29, 49, 73, .18);
}

.app-header__search-popover-form {
  display: grid;
  gap: 10px;
}

.app-header__search-popover-form > label {
  color: var(--app-ink);
  font-size: 12px;
  font-weight: 900;
}

.app-header__search-field {
  display: flex;
  min-height: 44px;
  align-items: center;
  gap: 8px;
  padding: 0 11px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  color: var(--app-muted);
  background: #f8fafc;
}

.app-header__search-field:focus-within {
  border-color: #2e5984;
  box-shadow: 0 0 0 3px rgba(46,89,132,.1);
}

.app-header__search-field input {
  width: 100%;
  min-width: 0;
  min-height: 42px;
  padding: 0;
  border: 0;
  outline: 0;
  color: var(--app-ink);
  background: transparent;
  font: inherit;
  font-size: 12px;
}

.app-header__search-popover-actions {
  display: flex;
  justify-content: flex-end;
  gap: 7px;
}

.app-header__search-popover-actions button {
  min-height: 38px;
  padding: 0 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: #fff;
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

.app-header__search-popover-actions button[type='submit'] {
  border-color: #2e5984;
  color: #fff;
  background: #2e5984;
}

.app-header__user-menu {
  position: absolute;
  z-index: 45;
  top: calc(100% + 10px);
  right: 0;
  display: grid;
  min-width: 230px;
  padding: 7px;
  border: 1px solid var(--app-line);
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(29, 49, 73, .18);
}

.app-header__account-summary {
  display: grid;
  gap: 2px;
  margin: 2px 3px 6px;
  padding: 9px 10px 10px;
  border-bottom: 1px solid var(--app-line);
}

.app-header__account-summary strong {
  color: var(--app-ink);
  font-size: 12px;
}

.app-header__account-summary small {
  color: var(--app-muted);
  font-size: 9px;
}

.app-header__user-menu a,
.app-header__user-menu button {
  display: flex;
  width: 100%;
  min-height: 40px;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 800;
  text-align: left;
  text-decoration: none;
}

.app-header__user-menu a:hover,
.app-header__user-menu button:hover {
  color: #244d73;
  background: #eef4fa;
}

@media (max-width: 720px) {
  .app-header {
    top: 8px;
    min-height: 54px;
    padding: 6px 7px 6px 10px;
  }

  .app-header__brand-title strong {
    max-width: 46vw;
    font-size: 11px;
  }

  .app-header__brand-copy > small,
  .app-header__demo-stage {
    display: none;
  }

  .app-header__actions {
    gap: 1px;
  }

  .app-header__icon-button {
    width: 38px;
    height: 38px;
  }

  .app-header__search-popover {
    position: fixed;
    top: 70px;
    right: 12px;
    left: 12px;
    width: auto;
  }
}
</style>
