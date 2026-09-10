<script setup lang="ts">
import { PhArrowRight as ArrowRight } from '@phosphor-icons/vue'
import { useRoute, useRouter } from 'vue-router'
import GlassButton from '../components/glass/GlassButton.vue'
import { liquidGlass as vLiquidGlass } from '../directives/liquidGlass'

const emit = defineEmits<{
  focusLogin: []
}>()

const route = useRoute()
const router = useRouter()

async function focusLogin(): Promise<void> {
  if (route?.path && route.path !== '/' && router) {
    await router.push({ path: '/', hash: '#login' })
    return
  }
  emit('focusLogin')
}
</script>

<template>
  <div class="public-layout">
    <header class="public-header">
      <div class="public-container">
        <nav v-liquid-glass data-lg class="lg lg-navbar public-nav" aria-label="主要導覽">
          <a class="lg-navbar__brand public-brand" href="#top" aria-label="估價審查中台首頁">
            <span class="public-brand__mark" aria-hidden="true">估</span>
            <span>估價審查中台</span>
          </a>
          <div class="lg-navbar__spacer" />
          <a class="lg-navbar__link" href="#capabilities">工作範圍</a>
          <a class="lg-navbar__link" href="#process">作業流程</a>
          <GlassButton
            class="public-nav__cta"
            variant="accent"
            pill
            size="sm"
            aria-label="前往登入"
            @click="focusLogin"
          >
            立即登入
            <ArrowRight :size="16" weight="bold" aria-hidden="true" />
          </GlassButton>
        </nav>
      </div>
    </header>

    <main id="top" class="public-main">
      <slot />
    </main>

    <footer class="public-footer">
      <div class="public-container public-footer__inner">
        <span>估價審查中台</span>
        <span>讓依據清楚，讓審查更有把握。</span>
      </div>
    </footer>
  </div>
</template>
