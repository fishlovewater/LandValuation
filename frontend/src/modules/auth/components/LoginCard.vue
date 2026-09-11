<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { isAxiosError } from 'axios'
import {
  PhClipboardText as ClipboardText,
  PhEye as Eye,
  PhEyeSlash as EyeSlash,
  PhLockKey as LockKey,
  PhMagnifyingGlass as MagnifyingGlass,
  PhMapPin as MapPin,
  PhSignIn as SignIn,
  PhSpinnerGap as SpinnerGap,
} from '@phosphor-icons/vue'
import { ForbiddenError } from '../../../api/http'
import GlassButton from '../../../components/glass/GlassButton.vue'
import GlassCard from '../../../components/glass/GlassCard.vue'
import GlassField from '../../../components/glass/GlassField.vue'
import { isDemoQuickLoginEnabled } from '../../../config/environment'
import { useAuthStore } from '../../../stores/auth.store'
import type { AuthUser, DemoLoginRole } from '../auth.types'

const emit = defineEmits<{
  loginSuccess: [user: AuthUser]
}>()

const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const passwordVisible = ref(false)
const usernameError = ref('')
const passwordError = ref('')
const formError = ref('')
const usernameContainer = ref<HTMLElement | null>(null)
const passwordContainer = ref<HTMLElement | null>(null)
let enterHandled = false

const demoQuickLoginEnabled = isDemoQuickLoginEnabled(import.meta.env)
const demoAccounts: Array<{
  role: DemoLoginRole
  stage: number
  label: string
  description: string
  icon: typeof MapPin
}> = [
  { role: 'APPRAISER', stage: 1, label: '估價人員', description: '文件辨識、估價計算與正式送審', icon: MapPin },
  { role: 'REVIEWER', stage: 2, label: '審查人員', description: '疑點判讀、證據確認與審查決定', icon: ClipboardText },
  { role: 'INSPECTOR', stage: 3, label: '案件查詢', description: '歷程、版本與完整追溯', icon: MagnifyingGlass },
]

const passwordType = computed(() => (passwordVisible.value ? 'text' : 'password'))
const passwordToggleLabel = computed(() => (passwordVisible.value ? '隱藏密碼' : '顯示密碼'))

function inputIn(container: HTMLElement | null): HTMLInputElement | null {
  return container?.querySelector<HTMLInputElement>('input') ?? null
}

function focusFirstInvalid(): void {
  const target = usernameError.value
    ? inputIn(usernameContainer.value)
    : inputIn(passwordContainer.value)
  target?.focus()
}

function focusUsername(): void {
  inputIn(usernameContainer.value)?.focus()
}

function safeLoginError(error: unknown): string {
  if (error instanceof ForbiddenError) return '此帳號目前無法登入，請聯絡系統管理者。'
  const status = isAxiosError(error)
    ? error.response?.status
    : (error as { response?: { status?: number } } | null)?.response?.status
  if (status === 401) {
    const detail = isAxiosError(error)
      ? error.response?.data?.detail
      : (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail
    if (typeof detail === 'string' && (detail.includes('停用') || detail.toLowerCase().includes('disabled'))) {
      return '此帳號目前無法登入，請聯絡系統管理者。'
    }
    return '帳號或密碼不正確，請再試一次。'
  }
  return '目前無法連線至服務，請確認網路後再試。'
}

async function submit(): Promise<void> {
  if (authStore.isSubmitting) return
  usernameError.value = ''
  passwordError.value = ''
  formError.value = ''

  const cleanUsername = username.value.trim()
  if (!cleanUsername) usernameError.value = '請輸入帳號。'
  if (!password.value) passwordError.value = '請輸入密碼。'
  if (usernameError.value || passwordError.value) {
    await nextTick()
    focusFirstInvalid()
    return
  }

  try {
    await authStore.login({ username: cleanUsername, password: password.value })
    password.value = ''
    if (authStore.user) emit('loginSuccess', authStore.user)
  } catch (error: unknown) {
    password.value = ''
    formError.value = safeLoginError(error)
    await nextTick()
    inputIn(passwordContainer.value)?.focus()
  }
}

async function quickLogin(role: DemoLoginRole): Promise<void> {
  if (authStore.isSubmitting) return
  usernameError.value = ''
  passwordError.value = ''
  formError.value = ''
  try {
    await authStore.demoLogin(role)
    if (authStore.user) emit('loginSuccess', authStore.user)
  } catch (error: unknown) {
    formError.value = safeLoginError(error)
  }
}

function handleEnter(event: KeyboardEvent): void {
  event.preventDefault()
  if (enterHandled) return
  enterHandled = true
  void submit().finally(() => {
    window.setTimeout(() => {
      enterHandled = false
    }, 0)
  })
}

function handleSubmit(): void {
  if (enterHandled) return
  void submit()
}

defineExpose({ focusUsername })
</script>

<template>
  <GlassCard class="login-card" aria-labelledby="login-title">
    <div class="login-card__eyebrow">
      <span class="login-card__eyebrow-icon" aria-hidden="true"><LockKey :size="16" weight="bold" /></span>
      安全登入
    </div>
    <div class="login-card__heading">
      <h2 id="login-title">從你的工作台開始</h2>
      <p>使用已核准的帳號登入，接續估價與審查工作。</p>
    </div>

    <section v-if="demoQuickLoginEnabled" class="demo-login" aria-labelledby="demo-login-title">
      <div class="demo-login__heading">
        <div class="demo-login__title-row">
          <strong id="demo-login-title">Demo 快速登入</strong>
          <span class="demo-login__sequence">建議順序 1 → 2 → 3</span>
        </div>
        <span>展示時直接選擇角色，不需要輸入帳號密碼；完整展示依「估價 → 審查 → 歷程查詢」進行。</span>
      </div>
      <div class="demo-login__grid">
        <button
          v-for="account in demoAccounts"
          :key="account.role"
          class="demo-login__button"
          type="button"
          :data-testid="`demo-login-${account.role.toLowerCase()}`"
          :disabled="authStore.isSubmitting"
          @click="quickLogin(account.role)"
        >
          <span class="demo-login__stage" aria-hidden="true">{{ account.stage }}</span>
          <span class="demo-login__icon" aria-hidden="true">
            <component :is="account.icon" :size="19" weight="duotone" />
          </span>
          <span class="demo-login__copy">
            <strong>{{ account.label }}</strong>
            <small>{{ account.description }}</small>
          </span>
        </button>
      </div>
      <div class="demo-login__divider"><span>或使用帳號密碼</span></div>
    </section>

    <form class="login-form" novalidate @submit.prevent="handleSubmit">
      <div ref="usernameContainer">
        <GlassField
          id="login-username"
          v-model="username"
          label="帳號"
          surface="solid"
          name="username"
          autocomplete="username"
          :hint="usernameError || '請輸入你的工作帳號'"
          :invalid="Boolean(usernameError)"
          :aria-invalid="usernameError ? 'true' : 'false'"
          required
        />
      </div>

      <div ref="passwordContainer" class="login-form__password">
        <GlassField
          id="login-password"
          v-model="password"
          label="密碼"
          surface="solid"
          name="password"
          :type="passwordType"
          autocomplete="current-password"
          :hint="passwordError || '密碼僅用於本次登入驗證'"
          :invalid="Boolean(passwordError)"
          :aria-invalid="passwordError ? 'true' : 'false'"
          required
          @keydown.enter="handleEnter"
        />
        <button
          id="toggle-password"
          class="password-toggle"
          type="button"
          :aria-label="passwordToggleLabel"
          :title="passwordToggleLabel"
          @click="passwordVisible = !passwordVisible"
        >
          <EyeSlash v-if="passwordVisible" :size="20" aria-hidden="true" />
          <Eye v-else :size="20" aria-hidden="true" />
          <span class="sr-only">{{ passwordToggleLabel }}</span>
        </button>
      </div>

      <p v-if="formError" class="login-form__error" role="alert">{{ formError }}</p>

      <GlassButton
        class="login-submit"
        type="submit"
        variant="accent"
        size="lg"
        :disabled="authStore.isSubmitting"
        :aria-busy="authStore.isSubmitting ? 'true' : 'false'"
      >
        <SpinnerGap v-if="authStore.isSubmitting" class="login-submit__spinner" :size="19" aria-hidden="true" />
        <SignIn v-else :size="19" weight="bold" aria-hidden="true" />
        {{ authStore.isSubmitting ? '登入中…' : '登入工作台' }}
      </GlassButton>
    </form>

    <p class="login-card__note">登入後將依帳號權限開啟可用功能。</p>
  </GlassCard>
</template>
