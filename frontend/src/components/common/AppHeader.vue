<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  PhArrowsClockwise as ArrowsClockwise,
  PhList as List,
  PhMagnifyingGlass as MagnifyingGlass,
  PhSignOut as SignOut,
  PhSparkle as Sparkle,
  PhUserCircle as UserCircle,
} from '@phosphor-icons/vue'
import { isDemoQuickLoginEnabled } from '../../config/environment'
import { liquidGlass as vLiquidGlass } from '../../directives/liquidGlass'
import type { DemoLoginRole } from '../../modules/auth/auth.types'
import { homeFor } from '../../router/roleHomeMap'
import { hasHistoryRole } from '../../router/roleAccess'
import { useAuthStore } from '../../stores/auth.store'

defineOptions({ inheritAttrs: false })

const emit = defineEmits<{
  toggleSidebar: []
  openAssistant: []
}>()

withDefaults(
  defineProps<{
    sidebarOpen?: boolean
    assistantOpen?: boolean
  }>(),
  { sidebarOpen: false, assistantOpen: false },
)

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const searchTerm = ref('')
const searchOpen = ref(false)
const searchInput = ref<HTMLInputElement | null>(null)
const searchTrigger = ref<HTMLButtonElement | null>(null)
const userMenuOpen = ref(false)
const demoSwitchError = ref('')
const switchingDemoRole = ref<DemoLoginRole | null>(null)

const demoQuickLoginEnabled = isDemoQuickLoginEnabled(import.meta.env)
const demoRoles: ReadonlyArray<{ role: DemoLoginRole; stage: number; label: string; description: string }> = [
  { role: 'APPRAISER', stage: 1, label: '估價人員', description: '估價與送審' },
  { role: 'REVIEWER', stage: 2, label: '審查人員', description: '智慧審查' },
  { role: 'INSPECTOR', stage: 3, label: '案件查詢', description: '歷程追溯' },
]

const currentSubsystem = computed(() => {
  const subsystem = route.meta.subsystem
  return typeof subsystem === 'string' ? subsystem : '工作台'
})

const canSearchCases = computed(() => hasHistoryRole(authStore.roles))
const canUseAssistant = computed(() => authStore.permissions.includes('assistant.use'))
const displayName = computed(() => authStore.user?.displayName || '目前使用者')
const currentDemoRole = computed<DemoLoginRole | null>(() => {
  for (const item of demoRoles) {
    if (authStore.roles.includes(item.role)) return item.role
  }
  return null
})
const currentDemoRoleItem = computed(() => demoRoles.find((item) => item.role === currentDemoRole.value) ?? null)

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
  void nextTick(() => searchInput.value?.focus())
}

function closeSearch(): void {
  if (!searchOpen.value) return
  searchOpen.value = false
  void nextTick(() => searchTrigger.value?.focus())
}

function toggleUserMenu(): void {
  userMenuOpen.value = !userMenuOpen.value
}

function closeUserMenu(): void {
  userMenuOpen.value = false
  demoSwitchError.value = ''
}

async function switchDemoRole(role: DemoLoginRole): Promise<void> {
  if (!demoQuickLoginEnabled || authStore.isSubmitting || role === currentDemoRole.value) return
  demoSwitchError.value = ''
  switchingDemoRole.value = role
  try {
    await authStore.switchDemoRole(role)
    const destination = homeFor(authStore.user)
    closeUserMenu()
    await router.replace(destination)
  } catch {
    demoSwitchError.value = 'Demo 角色切換失敗，請重新登入後再試。'
  } finally {
    switchingDemoRole.value = null
  }
}

function logout(): void {
  closeUserMenu()
  authStore.logout()
  void router.replace({ path: '/' })
}
</script>

<template>
  <header v-liquid-glass data-lg class="app-header lg" aria-label="平台標頭">
    <div class="app-header__identity">
      <button
        id="app-sidebar-trigger"
        class="app-header__menu"
        type="button"
        aria-label="開啟功能選單"
        aria-controls="app-sidebar"
        :aria-expanded="sidebarOpen ? 'true' : 'false'"
        @click="emit('toggleSidebar')"
      >
        <List :size="21" weight="bold" aria-hidden="true" />
      </button>
      <RouterLink class="app-header__brand" to="/app" aria-label="估價審查中台工作台首頁">
        <span class="app-header__mark" aria-hidden="true">估</span>
        <span class="app-header__brand-copy">
          <span class="app-header__brand-title">
            <strong>估價審查中台</strong>
            <span v-if="demoQuickLoginEnabled" class="app-header__demo-badge" data-testid="demo-mode-badge">示範</span>
            <span v-if="demoQuickLoginEnabled && currentDemoRoleItem" class="app-header__demo-stage" data-testid="demo-role-stage">
              {{ currentDemoRoleItem.stage }} · {{ currentDemoRoleItem.label }}
            </span>
          </span>
          <small>{{ currentSubsystem }}</small>
        </span>
      </RouterLink>
    </div>

    <div class="app-header__actions">
      <button
        v-if="canSearchCases"
        ref="searchTrigger"
        class="app-header__search-trigger"
        data-testid="case-search-trigger"
        type="button"
        aria-label="開啟案件搜尋"
        aria-controls="case-search-popover"
        :aria-expanded="searchOpen ? 'true' : 'false'"
        @click="openSearch"
      >
        <MagnifyingGlass :size="18" aria-hidden="true" />
      </button>

      <form
        v-if="canSearchCases"
        class="app-header__search"
        data-testid="case-search"
        role="search"
        @submit.prevent="searchCases"
      >
        <MagnifyingGlass :size="18" aria-hidden="true" />
        <label class="sr-only" for="app-case-search">搜尋案件</label>
        <input
          id="app-case-search"
          v-model="searchTerm"
          type="search"
          placeholder="搜尋案件編號"
          autocomplete="off"
        />
        <button type="submit" aria-label="送出案件搜尋">搜尋</button>
      </form>

      <div
        v-if="searchOpen"
        id="case-search-popover"
        class="app-header__search-popover"
        role="dialog"
        aria-label="搜尋案件"
        @keydown.esc="closeSearch"
      >
        <form class="app-header__search-popover-form" role="search" @submit.prevent="searchCases">
          <label for="app-case-search-mobile">搜尋案件編號</label>
          <input
            id="app-case-search-mobile"
            ref="searchInput"
            v-model="searchTerm"
            type="search"
            placeholder="輸入案件編號"
            autocomplete="off"
          />
          <div class="app-header__search-popover-actions">
            <button type="submit">搜尋</button>
            <button type="button" aria-label="關閉案件搜尋" @click="closeSearch">關閉</button>
          </div>
        </form>
      </div>

      <button
        v-if="canUseAssistant"
        class="app-header__assistant"
        data-testid="assistant-shortcut"
        type="button"
        aria-label="開啟智能助理"
        aria-controls="global-assistant-drawer"
        :aria-expanded="assistantOpen ? 'true' : 'false'"
        @click="emit('openAssistant')"
      >
        <Sparkle :size="18" weight="duotone" aria-hidden="true" />
        <span>智能助理</span>
      </button>

      <div class="app-header__user" @keydown.esc="closeUserMenu">
        <button
          class="app-header__user-trigger"
          type="button"
          :aria-expanded="userMenuOpen ? 'true' : 'false'"
          aria-haspopup="menu"
          aria-label="開啟使用者選單"
          @click="toggleUserMenu"
        >
          <UserCircle :size="24" weight="duotone" aria-hidden="true" />
          <span>{{ displayName }}</span>
          <span class="app-header__chevron" aria-hidden="true">⌄</span>
        </button>
        <div v-if="userMenuOpen" class="app-header__user-menu" role="menu">
          <section v-if="demoQuickLoginEnabled" class="app-header__demo-switch" aria-label="Demo 角色切換">
            <div class="app-header__demo-switch-heading">
              <ArrowsClockwise :size="15" aria-hidden="true" />
              <span>Demo 角色切換</span>
            </div>
            <button
              v-for="item in demoRoles"
              :key="item.role"
              type="button"
              role="menuitem"
              :data-testid="`demo-switch-${item.role.toLowerCase()}`"
              :disabled="authStore.isSubmitting || item.role === currentDemoRole"
              @click="switchDemoRole(item.role)"
            >
              <span class="app-header__demo-role-copy">
                <b>{{ item.stage }}</b>
                <span>
                  <strong>{{ item.label }}</strong>
                  <small>{{ item.description }}</small>
                </span>
              </span>
              <small v-if="item.role === currentDemoRole" class="app-header__demo-state">目前</small>
              <small v-else-if="switchingDemoRole === item.role" class="app-header__demo-state">切換中…</small>
            </button>
            <p v-if="demoSwitchError" class="app-header__demo-switch-error" role="alert">{{ demoSwitchError }}</p>
          </section>
          <RouterLink to="/app/profile" role="menuitem" @click="closeUserMenu">帳號設定</RouterLink>
          <button type="button" role="menuitem" @click="logout">
            <SignOut :size="17" aria-hidden="true" />
            登出
          </button>
        </div>
      </div>
    </div>

  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  z-index: 30;
  top: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 72px;
  padding: 10px 14px 10px 18px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.7);
}

.app-header__identity,
.app-header__actions,
.app-header__brand,
.app-header__assistant,
.app-header__user-trigger {
  display: flex;
  align-items: center;
}

.app-header__identity {
  min-width: 0;
  gap: 10px;
}

.app-header__menu {
  display: none;
  width: 44px;
  height: 44px;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 12px;
  color: var(--app-ink-soft);
  background: transparent;
  cursor: pointer;
}

.app-header__menu:hover {
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.app-header__brand {
  gap: 11px;
  min-height: 44px;
  color: var(--app-ink);
  text-decoration: none;
}

.app-header__mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 11px;
  color: #fff8f2;
  background: var(--app-accent);
  font-family: var(--app-font-display);
  font-size: 17px;
}

.app-header__brand-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.app-header__brand-title {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.app-header__brand-copy strong {
  overflow: hidden;
  font-size: 14px;
  letter-spacing: 0.04em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-header__demo-badge {
  flex: 0 0 auto;
  padding: 2px 6px;
  border: 1px solid rgba(255, 209, 156, .72);
  border-radius: 999px;
  color: #fff2df;
  background: rgba(255, 209, 156, .13);
  font-size: 8px;
  font-weight: 900;
  letter-spacing: .12em;
}

.app-header__demo-stage {
  flex: 0 0 auto;
  padding: 3px 7px;
  border: 1px solid rgba(255,255,255,.18);
  border-radius: 999px;
  color: rgba(255,255,255,.9);
  background: rgba(255,255,255,.09);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .02em;
  white-space: nowrap;
}

.app-header__brand-copy small {
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

.app-header__actions {
  position: relative;
  gap: 10px;
  min-width: 0;
}

.app-header__search-trigger {
  display: none;
  width: 44px;
  min-height: 44px;
  place-items: center;
  padding: 0;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-pill);
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
  cursor: pointer;
}

.app-header__search-trigger:hover,
.app-header__search-trigger:focus-visible {
  border-color: var(--app-accent);
  color: var(--app-accent-deep);
  outline: 0;
  box-shadow: 0 0 0 2px var(--app-accent-soft);
}

.app-header__search {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: min(320px, 32vw);
  min-height: 44px;
  padding: 3px 4px 3px 12px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-pill);
  color: var(--app-muted);
  background: var(--app-paper-strong);
}

.app-header__search:focus-within {
  border-color: var(--app-accent);
  box-shadow: 0 0 0 2px var(--app-accent-soft);
}

.app-header__search-popover {
  position: absolute;
  z-index: 45;
  top: calc(100% + 8px);
  right: 0;
  width: min(320px, calc(100vw - 32px));
  padding: 14px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
  box-shadow: var(--app-shadow-soft);
}

.app-header__search-popover-form {
  display: grid;
  gap: 9px;
}

.app-header__search-popover-form label {
  color: var(--app-ink-soft);
  font-size: 12px;
  font-weight: 800;
}

.app-header__search-popover-form input {
  width: 100%;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
  color: var(--app-ink);
  background: var(--app-paper);
  font-size: 13px;
}

.app-header__search-popover-form input:focus {
  border-color: var(--app-accent);
  outline: 0;
  box-shadow: 0 0 0 2px var(--app-accent-soft);
}

.app-header__search-popover-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.app-header__search-popover-actions button {
  min-height: 44px;
  padding: 0 13px;
  border: 0;
  border-radius: var(--app-radius-pill);
  color: #fff8f2;
  background: var(--app-accent);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}

.app-header__search-popover-actions button[type='button'] {
  color: var(--app-ink-soft);
  background: var(--app-accent-soft);
}

.app-header__search input {
  width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: 0;
  border: 0;
  outline: 0;
  color: var(--app-ink);
  background: transparent;
  font-size: 12px;
}

.app-header__search button,
.app-header__user-menu button {
  min-height: 44px;
  padding: 0 13px;
  border: 0;
  border-radius: var(--app-radius-pill);
  color: #fff8f2;
  background: var(--app-accent);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}

.app-header__assistant {
  gap: 6px;
  min-height: 44px;
  padding: 0 13px;
  border: 0;
  border-radius: var(--app-radius-pill);
  color: var(--app-blue);
  background: #e9f0f8;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  text-decoration: none;
  white-space: nowrap;
}

.app-header__assistant:hover {
  color: var(--app-ink);
}

.app-header__user {
  position: relative;
}

.app-header__user-trigger {
  gap: 7px;
  min-height: 44px;
  padding: 0 7px 0 10px;
  border: 0;
  border-radius: var(--app-radius-pill);
  color: var(--app-ink-soft);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.app-header__user-trigger:hover {
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.app-header__chevron {
  margin-left: 2px;
  color: var(--app-muted);
  font-size: 16px;
}

.app-header__user-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  display: grid;
  min-width: 210px;
  padding: 7px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
  box-shadow: var(--app-shadow-soft);
}

.app-header__demo-switch {
  display: grid;
  gap: 3px;
  margin-bottom: 5px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--app-line);
}

.app-header__demo-switch-heading {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px 4px;
  color: var(--app-muted);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .06em;
}

.app-header__demo-switch button {
  justify-content: space-between;
  gap: 12px;
  min-height: 54px;
}

.app-header__demo-role-copy {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.app-header__demo-role-copy > b {
  display: inline-grid;
  width: 24px;
  height: 24px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 999px;
  color: var(--app-primary-deep);
  background: var(--app-primary-soft);
  font-size: 10px;
}

.app-header__demo-role-copy > span {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.app-header__demo-role-copy strong {
  color: inherit;
  font-size: 11px;
}

.app-header__demo-role-copy small {
  color: var(--app-muted);
  font-size: 9px;
  font-weight: 700;
}

.app-header__demo-switch button:disabled {
  cursor: default;
  opacity: 1;
  color: var(--app-primary-deep);
  background: var(--app-primary-soft);
}

.app-header__demo-state {
  color: var(--app-muted);
  font-size: 9px;
  font-weight: 800;
}

.app-header__demo-switch-error {
  margin: 4px 9px 2px;
  color: #a44334;
  font-size: 10px;
  line-height: 1.4;
}

.app-header__user-menu a,
.app-header__user-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 44px;
  padding: 0 11px;
  border-radius: 9px;
  color: var(--app-ink-soft);
  background: transparent;
  text-decoration: none;
  text-align: left;
}

.app-header__user-menu a:hover,
.app-header__user-menu button:hover {
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

/* Authenticated shell uses a solid government-service header instead of glass. */
.app-header {
  border-color: var(--app-primary-deep);
  background: var(--app-primary-deep) !important;
  box-shadow: 0 8px 24px rgba(18, 59, 104, .18) !important;
}
.app-header__brand,
.app-header__brand-copy strong,
.app-header__menu,
.app-header__user-trigger { color: #fff; }
.app-header__brand-copy small { color: #ffd19c; }
.app-header__mark { color: #fff; background: var(--app-highlight); }
.app-header__menu:hover,
.app-header__user-trigger:hover { color: #fff; background: rgba(255,255,255,.12); }
.app-header__assistant { color: #fff; background: rgba(255,255,255,.13); }
.app-header__assistant:hover { color: #fff; background: rgba(255,255,255,.2); }
.app-header__search { border-color: rgba(255,255,255,.2); background: #fff; }
.app-header__search-trigger { border-color: rgba(255,255,255,.25); color: #fff; background: rgba(255,255,255,.12); }
.app-header__chevron { color: rgba(255,255,255,.68); }

@media (max-width: 980px) {
  .app-header {
    top: 10px;
  }

  .app-header__menu {
    display: grid;
  }
}

@media (max-width: 700px) {
  .app-header {
    align-items: stretch;
    padding: 8px 9px;
  }

  .app-header__actions {
    gap: 4px;
  }

  .app-header__search {
    display: none;
  }

  .app-header__search-trigger {
    display: grid;
  }

  .app-header__assistant span,
  .app-header__user-trigger span {
    display: none;
  }

  .app-header__demo-stage {
    display: none;
  }

  .app-header__assistant,
  .app-header__user-trigger {
    width: 44px;
    justify-content: center;
    padding: 0;
  }
}
</style>
