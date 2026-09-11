<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, useAttrs, ref, watch } from 'vue'
import { liquidGlass as vLiquidGlass } from '../../directives/liquidGlass'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    open?: boolean
    title?: string
    labelledby?: string
    describedby?: string
    initialFocus?: string
    closeOnEscape?: boolean
    role?: 'dialog' | 'alertdialog'
    id?: string
  }>(),
  {
    open: false,
    closeOnEscape: true,
    role: 'dialog',
  },
)

const emit = defineEmits<{
  close: []
}>()

const attrs = useAttrs()
const panel = ref<HTMLDivElement | null>(null)
let nextModalId = 0
const fallbackId = `glass-modal-${++nextModalId}`
const modalId = computed(() => props.id || fallbackId)
const titleId = computed(() => `${modalId.value}-title`)
const trigger = ref<HTMLElement | null>(null)

const labelledBy = computed(() => {
  if (props.labelledby) return props.labelledby
  if (props.title) return titleId.value
  return typeof attrs['aria-labelledby'] === 'string' ? attrs['aria-labelledby'] : undefined
})
const describedBy = computed(() => {
  if (props.describedby) return props.describedby
  return typeof attrs['aria-describedby'] === 'string' ? attrs['aria-describedby'] : undefined
})
const ariaLabel = computed(() => {
  if (props.title || labelledBy.value) return undefined
  return typeof attrs['aria-label'] === 'string' ? attrs['aria-label'] : '對話框'
})

function focusableElements(): HTMLElement[] {
  const root = panel.value
  if (!root) return []
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute('hidden'))
}

function focusInitialElement() {
  if (!props.open || !panel.value) return
  const requested = props.initialFocus ? panel.value.querySelector<HTMLElement>(props.initialFocus) : null
  const target = requested || focusableElements()[0] || panel.value
  target.focus()
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape' && props.closeOnEscape) {
    event.preventDefault()
    event.stopImmediatePropagation()
    emit('close')
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopImmediatePropagation()
    return
  }
  if (event.key !== 'Tab') return

  const focusables = focusableElements()
  if (!focusables.length) {
    event.preventDefault()
    panel.value?.focus()
    return
  }

  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement
  if (!panel.value?.contains(active)) {
    event.preventDefault()
    first.focus()
  } else if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

function requestClose() {
  emit('close')
}

watch(
  () => props.open,
  (open, wasOpen) => {
    if (open) {
      const active = document.activeElement
      if (active instanceof HTMLElement && !panel.value?.contains(active)) trigger.value = active
      document.addEventListener('keydown', handleKeydown, true)
      void nextTick(focusInitialElement)
    } else if (wasOpen) {
      document.removeEventListener('keydown', handleKeydown, true)
      const restore = trigger.value
      trigger.value = null
      void nextTick(() => {
        if (restore?.isConnected) restore.focus()
      })
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown, true)
  const restore = trigger.value
  if (restore?.isConnected) restore.focus()
})
</script>

<template>
  <div
    v-show="open"
    :id="modalId"
    class="lg-modal"
    :class="{ 'is-open': open }"
    :aria-hidden="open ? 'false' : 'true'"
  >
    <div class="lg-modal__overlay" data-lg-close @click.stop="requestClose" />
    <div
      ref="panel"
      v-liquid-glass
      data-lg
      v-bind="attrs"
      class="lg-modal__panel lg"
      :role="role"
      aria-modal="true"
      :aria-labelledby="labelledBy"
      :aria-describedby="describedBy"
      :aria-label="ariaLabel"
      tabindex="-1"
      @click.stop
    >
      <header v-if="title || $slots.close" class="lg-modal__header">
        <h2 v-if="title" :id="titleId" class="lg-modal__title">{{ title }}</h2>
        <button
          type="button"
          class="lg-modal__close"
          data-lg-close
          aria-label="關閉"
          @click.stop="requestClose"
        >
          <slot name="close"><span aria-hidden="true">×</span></slot>
        </button>
      </header>
      <div class="lg-modal__body"><slot /></div>
      <footer v-if="$slots.footer" class="lg-modal__footer"><slot name="footer" /></footer>
    </div>
  </div>
</template>

<style scoped>
.lg-modal__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.lg-modal__title {
  min-width: 0;
  margin: 0;
}

.lg-modal__close {
  display: inline-grid;
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  padding: 0;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 999px;
  color: var(--app-ink-soft, #475569);
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 24px;
  font-weight: 400;
  line-height: 1;
}

.lg-modal__close:hover {
  border-color: var(--app-line, rgba(71, 85, 105, .2));
  background: rgba(71, 85, 105, .07);
}

.lg-modal__close:focus-visible {
  outline: 3px solid rgba(46, 89, 132, .18);
  outline-offset: 2px;
}
</style>
