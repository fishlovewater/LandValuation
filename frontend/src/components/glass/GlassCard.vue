<script setup lang="ts">
import { liquidGlass as vLiquidGlass } from '../../directives/liquidGlass'

defineOptions({ inheritAttrs: false })
</script>

<template>
  <div v-liquid-glass data-lg v-bind="$attrs" class="lg lg-card">
    <h4 v-if="$slots.title" class="lg-card__title"><slot name="title" /></h4>
    <p v-if="$slots.meta" class="lg-card__meta"><slot name="meta" /></p>
    <slot />
  </div>
</template>
