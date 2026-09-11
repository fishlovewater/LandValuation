<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { PhX as X } from '@phosphor-icons/vue'
import { liquidGlass as vLiquidGlass } from '../../directives/liquidGlass'

const props = withDefaults(
  defineProps<{
    open?: boolean
    title: string
    width?: string
  }>(),
  { open: false, width: '460px' },
)

const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null

function focusable(): HTMLElement[] {
  return Array.from(
    panel.value?.querySelectorAll<HTMLElement>(
      'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
    ) ?? [],
  )
}

function close(): void {
  emit('close')
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab') return
  const items = focusable()
  if (!items.length) {
    event.preventDefault()
    panel.value?.focus()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      document.documentElement.classList.add('drawer-open')
      void nextTick(() => focusable()[0]?.focus())
    } else {
      document.documentElement.classList.remove('drawer-open')
      void nextTick(() => previousFocus?.focus())
    }
  },
)

onBeforeUnmount(() => document.documentElement.classList.remove('drawer-open'))
</script>

<template>
  <Teleport to="body">
    <Transition name="glass-drawer">
      <div v-if="open" class="glass-drawer-layer">
        <button class="glass-drawer-backdrop" type="button" aria-label="關閉側邊面板" @click="close" />
        <aside
          id="global-assistant-drawer"
          ref="panel"
          v-liquid-glass
          data-lg
          class="glass-drawer lg"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          :style="{ '--drawer-width': width }"
          tabindex="-1"
          @keydown="onKeydown"
        >
          <header class="glass-drawer__header">
            <div>
              <span class="glass-drawer__eyebrow">智能助理</span>
              <h2>{{ title }}</h2>
            </div>
            <button class="glass-drawer__close" type="button" aria-label="關閉" @click="close">
              <X :size="20" weight="bold" aria-hidden="true" />
            </button>
          </header>
          <div class="glass-drawer__body"><slot /></div>
          <footer v-if="$slots.footer" class="glass-drawer__footer"><slot name="footer" /></footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.glass-drawer-layer {
  position: fixed;
  z-index: 90;
  inset: 0;
}

.glass-drawer-backdrop {
  position: absolute;
  inset: 0;
  width: 100%;
  border: 0;
  background: rgba(25, 39, 63, 0.18);
  backdrop-filter: blur(2px);
}

.glass-drawer {
  position: absolute;
  top: 12px;
  right: 12px;
  bottom: 12px;
  display: flex;
  width: min(var(--drawer-width), calc(100vw - 24px));
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.8);
  border-radius: 24px;
  background: rgba(248, 251, 255, .76);
  box-shadow: 0 24px 70px rgba(31, 48, 78, .22);
}

.glass-drawer__header,
.glass-drawer__footer {
  flex: 0 0 auto;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(95,112,143,.14);
}

.glass-drawer__footer {
  border-top: 1px solid rgba(95,112,143,.14);
  border-bottom: 0;
}

.glass-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.glass-drawer__header h2 {
  margin: 4px 0 0;
  color: var(--app-ink);
  font-size: 20px;
}

.glass-drawer__eyebrow {
  color: var(--app-accent-deep);
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .18em;
}

.glass-drawer__close {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border: 1px solid var(--app-line);
  border-radius: 50%;
  color: var(--app-ink-soft);
  background: rgba(255,255,255,.66);
  cursor: pointer;
}

.glass-drawer__body {
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding: 18px 20px;
}

.glass-drawer-enter-active,
.glass-drawer-leave-active { transition: opacity .18s ease; }
.glass-drawer-enter-active .glass-drawer,
.glass-drawer-leave-active .glass-drawer { transition: transform .22s ease, opacity .18s ease; }
.glass-drawer-enter-from,
.glass-drawer-leave-to { opacity: 0; }
.glass-drawer-enter-from .glass-drawer,
.glass-drawer-leave-to .glass-drawer { transform: translateX(28px); opacity: 0; }

@media (max-width: 640px) {
  .glass-drawer { top: 6px; right: 6px; bottom: 6px; width: calc(100vw - 12px); border-radius: 18px; }
  .glass-drawer__body { padding: 14px; }
}
</style>