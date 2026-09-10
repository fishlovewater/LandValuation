<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { liquidGlass as vLiquidGlass } from '../../directives/liquidGlass'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    type?: 'button' | 'submit' | 'reset'
    disabled?: boolean
    variant?: 'default' | 'accent'
    pill?: boolean
    icon?: boolean
    size?: 'default' | 'lg' | 'sm'
  }>(),
  {
    type: 'button',
    disabled: false,
    variant: 'default',
    pill: false,
    icon: false,
    size: 'default',
  },
)

const attrs = useAttrs()
const ariaDisabled = computed(() => {
  if (props.disabled) return 'true'
  const provided = attrs['aria-disabled']
  if (typeof provided === 'boolean') return provided ? 'true' : 'false'
  return provided === 'true' || provided === 'false' ? provided : undefined
})

const buttonClasses = computed(() => [
  'lg',
  'lg-btn',
  props.variant === 'accent' && 'lg-btn--accent',
  props.pill && 'lg-btn--pill',
  props.icon && 'lg-btn--icon',
  props.size !== 'default' && `lg-btn--${props.size}`,
])
</script>

<template>
  <button
    v-liquid-glass
    data-lg
    v-bind="$attrs"
    :class="buttonClasses"
    :type="type"
    :disabled="disabled"
    :aria-disabled="ariaDisabled"
  >
    <slot />
  </button>
</template>
