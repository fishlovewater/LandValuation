<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { liquidGlass as vLiquidGlass } from '../../directives/liquidGlass'
import { useAuthStore } from '../../stores/auth.store'
import { authorizedModules } from './appModules'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    open?: boolean
  }>(),
  { open: false },
)

const emit = defineEmits<{
  close: []
}>()

const authStore = useAuthStore()
const isDesktop = ref(true)
const sidebar = ref<HTMLElement | null>(null)
let mediaQuery: MediaQueryList | null = null

const modules = computed(() => authorizedModules(authStore.permissions, authStore.roles))

function updateBreakpoint(event?: MediaQueryListEvent): void {
  if (event) {
    isDesktop.value = event.matches
  } else {
    isDesktop.value = mediaQuery?.matches ?? true
  }
}

function closeAfterNavigation(): void {
  if (!isDesktop.value) emit('close')
}

function focusableElements(): HTMLElement[] {
  return Array.from(
    sidebar.value?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? [],
  )
}

function focusFirstElement(): void {
  focusableElements()[0]?.focus()
}

function handleKeydown(event: KeyboardEvent): void {
  if (isDesktop.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab') return

  const elements = focusableElements()
  if (!elements.length) {
    event.preventDefault()
    sidebar.value?.focus()
    return
  }

  const first = elements[0]
  const last = elements[elements.length - 1]
  const active = document.activeElement
  if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  (open) => {
    if (open && !isDesktop.value) void nextTick(focusFirstElement)
  },
)

watch(isDesktop, (desktop) => {
  if (!desktop && props.open) void nextTick(focusFirstElement)
})

onMounted(() => {
  if (typeof window.matchMedia !== 'function') return
  mediaQuery = window.matchMedia('(min-width: 981px)')
  updateBreakpoint()
  mediaQuery.addEventListener?.('change', updateBreakpoint)
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener?.('change', updateBreakpoint)
})
</script>

<template>
  <aside
    v-if="isDesktop || props.open"
    ref="sidebar"
    v-liquid-glass
    data-lg
    class="app-sidebar lg"
    id="app-sidebar"
    :role="isDesktop ? undefined : 'dialog'"
    :aria-modal="isDesktop ? undefined : 'true'"
    :aria-labelledby="isDesktop ? undefined : 'app-sidebar-title'"
    aria-label="系統功能"
    @keydown="handleKeydown"
  >
    <div class="app-sidebar__intro">
      <span class="app-sidebar__eyebrow">WORKSPACE</span>
      <div class="app-sidebar__intro-row">
        <p id="app-sidebar-title">依權限開啟工作模組</p>
        <button
          v-if="!isDesktop"
          class="app-sidebar__close"
          type="button"
          aria-label="關閉功能選單"
          @click="emit('close')"
        >
          ×
        </button>
      </div>
    </div>

    <nav aria-label="系統功能">
      <ul class="app-sidebar__list">
        <li v-for="module in modules" :key="module.key">
          <RouterLink
            class="app-sidebar__link"
            :to="module.path"
            :aria-label="`${module.label}：${module.description}`"
            @click="closeAfterNavigation"
          >
            <component :is="module.icon" :size="19" weight="duotone" aria-hidden="true" />
            <span class="app-sidebar__link-copy">
              <strong>{{ module.label }}</strong>
              <small>{{ module.description }}</small>
            </span>
          </RouterLink>
        </li>
      </ul>
    </nav>

    <div class="app-sidebar__footnote">
      <span class="app-sidebar__status-dot" aria-hidden="true" />
      <span>已依目前帳號權限顯示</span>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: sticky;
  top: 24px;
  display: flex;
  flex: 0 0 252px;
  flex-direction: column;
  align-self: flex-start;
  min-height: calc(100vh - 48px);
  padding: 24px 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.75);
  background: rgba(255, 255, 255, 0.62);
}

.app-sidebar__intro {
  padding: 0 12px 20px;
  border-bottom: 1px solid rgba(95, 112, 143, 0.14);
}

.app-sidebar__eyebrow {
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.2em;
}

.app-sidebar__intro p {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 12px;
}

.app-sidebar__intro-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.app-sidebar__intro-row p {
  margin-bottom: 0;
}

.app-sidebar__close {
  display: grid;
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 10px;
  color: var(--app-ink-soft);
  background: transparent;
  cursor: pointer;
  font-size: 24px;
  line-height: 1;
}

.app-sidebar__close:hover {
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.app-sidebar__list {
  display: grid;
  gap: 7px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}

.app-sidebar__link {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 58px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: var(--app-radius-sm);
  color: var(--app-ink-soft);
  text-decoration: none;
  transition: color 150ms ease, background 150ms ease, border-color 150ms ease;
}

.app-sidebar__link:hover,
.app-sidebar__link.router-link-active {
  border-color: rgba(200, 91, 67, 0.15);
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.app-sidebar__link-copy {
  display: grid;
  gap: 3px;
}

.app-sidebar__link-copy strong {
  font-size: 13px;
  font-weight: 800;
}

.app-sidebar__link-copy small {
  color: var(--app-muted);
  font-size: 10px;
}

.app-sidebar__footnote {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: auto 12px 0;
  color: var(--app-muted);
  font-size: 10px;
  line-height: 1.5;
}

.app-sidebar__status-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--app-green);
  box-shadow: 0 0 0 4px rgba(59, 129, 102, 0.1);
}

@media (max-width: 980px) {
  .app-sidebar {
    position: fixed;
    z-index: 40;
    inset: 16px auto 16px 16px;
    width: min(304px, calc(100vw - 32px));
    min-height: 0;
    overflow: auto;
    box-shadow: var(--app-shadow);
  }
}
</style>
