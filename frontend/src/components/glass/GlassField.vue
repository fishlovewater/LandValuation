<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { liquidGlass as vLiquidGlass } from '../../directives/liquidGlass'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    id?: string
    label: string
    hint?: string
    modelValue?: string | number
    as?: 'input' | 'textarea'
    type?: string
    rows?: number
    disabled?: boolean
    readonly?: boolean
    required?: boolean
    invalid?: boolean
    surface?: 'glass' | 'solid'
  }>(),
  {
    as: 'input',
    type: 'text',
    rows: 3,
    disabled: false,
    readonly: false,
    required: false,
    invalid: false,
    surface: 'glass',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  input: [event: Event]
  change: [event: Event]
}>()

const attrs = useAttrs()
let nextFieldId = 0
const fallbackId = `glass-field-${++nextFieldId}`
const inputId = computed(() => props.id || fallbackId)
const hintId = computed(() => `${inputId.value}-hint`)
const describedBy = computed(() => {
  const external = typeof attrs['aria-describedby'] === 'string' ? attrs['aria-describedby'] : ''
  return [props.hint ? hintId.value : '', external].filter(Boolean).join(' ') || undefined
})
const ariaInvalid = computed(() => {
  if (props.invalid) return 'true'
  return typeof attrs['aria-invalid'] === 'string' ? attrs['aria-invalid'] : undefined
})
const fieldClasses = computed(() => [
  'lg-field',
  props.as === 'textarea' && 'lg-field--area',
  props.invalid && 'lg-field--error',
  props.disabled && 'lg-field--disabled',
])

function handleInput(event: Event) {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement
  emit('update:modelValue', target.value)
  emit('input', event)
}

function handleChange(event: Event) {
  emit('change', event)
}
</script>

<template>
  <div :class="fieldClasses">
    <div
      v-liquid-glass="surface === 'glass'"
      :data-lg="surface === 'glass' ? '' : undefined"
      :class="[
        'lg-field__box',
        surface === 'glass' && 'lg',
        surface === 'solid' && 'lg-field__box--solid',
      ]"
    >
      <component
        :is="as"
        v-bind="attrs"
        :id="inputId"
        class="lg-field__input"
        :type="as === 'input' ? type : undefined"
        :rows="as === 'textarea' ? rows : undefined"
        :value="modelValue"
        placeholder=" "
        :disabled="disabled"
        :readonly="readonly"
        :required="required"
        :aria-invalid="ariaInvalid"
        :aria-describedby="describedBy"
        @input="handleInput"
        @change="handleChange"
      />
      <label class="lg-field__label" :for="inputId">{{ label }}</label>
    </div>
    <span v-if="hint" :id="hintId" class="lg-field__hint">{{ hint }}</span>
  </div>
</template>
