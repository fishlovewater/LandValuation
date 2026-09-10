<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  PhArrowDown as ArrowDown,
  PhArrowRight as ArrowRight,
  PhCheck as Check,
  PhChartLineUp as ChartLineUp,
  PhFileText as FileText,
  PhShieldCheck as ShieldCheck,
  PhSparkle as Sparkle,
} from '@phosphor-icons/vue'
import PublicLayout from '../../../layouts/PublicLayout.vue'
import GlassButton from '../../../components/glass/GlassButton.vue'
import GlassCard from '../../../components/glass/GlassCard.vue'
import LoginCard from '../components/LoginCard.vue'
import type { AuthUser } from '../auth.types'
import { homeFor } from '../../../router/roleHomeMap'
import { safeAppRedirect } from '../../../router/redirects'

const loginCard = ref<InstanceType<typeof LoginCard> | null>(null)
const successMessage = ref('')
const router = useRouter()
const route = useRoute()

function focusLogin(): void {
  const loginSection = document.getElementById('login')
  if (loginSection && typeof loginSection.scrollIntoView === 'function') {
    loginSection.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  loginCard.value?.focusUsername()
}

function handleLoginSuccess(user: AuthUser): void {
  successMessage.value = `歡迎回來，${user.displayName}。`
  const destination = safeAppRedirect(route?.query.redirect) ?? homeFor(user)
  if (router) void router.replace(destination)
}

function focusLoginFromHash(): void {
  if (route?.hash === '#login') void nextTick(focusLogin)
}

onMounted(focusLoginFromHash)
watch(() => route?.hash, focusLoginFromHash)
</script>

<template>
  <PublicLayout @focus-login="focusLogin">
    <section class="hero public-container" aria-labelledby="hero-title">
      <div class="hero__copy">
        <p class="eyebrow"><span class="eyebrow__dot" aria-hidden="true" />土地估價審查工作台</p>
        <h1 id="hero-title">讓每一次估價，<em>都有可追溯的依據。</em></h1>
        <p class="hero__lead">
          把估價資料、審查判斷與案件脈絡放在同一條清楚的工作線上，讓團隊更快看懂、更穩定交付。
        </p>
        <div class="hero__actions">
          <GlassButton variant="accent" pill size="lg" @click="focusLogin">
            開始使用
            <ArrowRight :size="18" weight="bold" aria-hidden="true" />
          </GlassButton>
          <a class="hero__text-link" href="#process">
            了解作業方式
            <ArrowDown :size="16" weight="bold" aria-hidden="true" />
          </a>
        </div>
        <div class="hero__proof" aria-label="平台重點">
          <span><Check :size="15" weight="bold" aria-hidden="true" />證據有脈絡</span>
          <span><Check :size="15" weight="bold" aria-hidden="true" />判斷可說明</span>
          <span><Check :size="15" weight="bold" aria-hidden="true" />流程可協作</span>
        </div>
      </div>

      <section id="login" class="hero__login" aria-label="登入區域">
        <LoginCard ref="loginCard" @login-success="handleLoginSuccess" />
        <p v-if="successMessage" class="login-success" role="status">{{ successMessage }}</p>
      </section>
    </section>

    <section id="capabilities" class="capabilities public-container" aria-labelledby="capabilities-title">
      <div class="section-heading">
        <p class="eyebrow">一個入口，四段工作脈絡</p>
        <h2 id="capabilities-title">每個角色，都看見下一個清楚的動作。</h2>
      </div>
      <div class="value-grid">
        <GlassCard class="value-card">
          <span class="value-card__icon value-card__icon--orange" aria-hidden="true"><ChartLineUp :size="22" weight="duotone" /></span>
          <p class="value-card__label">估價作業</p>
          <h3>從資料到正式採用值</h3>
          <p>沿著表單、計算與驗證結果，保留每一步的判斷依據。</p>
        </GlassCard>
        <GlassCard class="value-card">
          <span class="value-card__icon value-card__icon--blue" aria-hidden="true"><Sparkle :size="22" weight="duotone" /></span>
          <p class="value-card__label">智能助理</p>
          <h3>在需要時補上脈絡</h3>
          <p>把問題留在案件上下文中，協助你找到可核對的資訊。</p>
        </GlassCard>
        <GlassCard class="value-card">
          <span class="value-card__icon value-card__icon--green" aria-hidden="true"><ShieldCheck :size="22" weight="duotone" /></span>
          <p class="value-card__label">審查工作台</p>
          <h3>先看風險，再做決定</h3>
          <p>集中呈現發現、證據與回覆，讓審查結論更容易被理解。</p>
        </GlassCard>
        <GlassCard class="value-card">
          <span class="value-card__icon value-card__icon--violet" aria-hidden="true"><FileText :size="22" weight="duotone" /></span>
          <p class="value-card__label">案件歷程</p>
          <h3>需要回看時，找得到來龍去脈</h3>
          <p>用一致的案件視角回顧文件、狀態與完成結果。</p>
        </GlassCard>
      </div>
    </section>

    <section id="process" class="process public-container" aria-labelledby="process-title">
      <div class="section-heading section-heading--center">
        <p class="eyebrow">三步，完成一次有依據的交付</p>
        <h2 id="process-title">把複雜工作，整理成團隊都能接住的節奏。</h2>
      </div>
      <div class="process__steps">
        <article class="process-step">
          <span class="process-step__number">01</span>
          <h3>整理</h3>
          <p>在同一個案件脈絡中備妥資料與必要文件。</p>
        </article>
        <article class="process-step">
          <span class="process-step__number">02</span>
          <h3>檢核</h3>
          <p>用驗證與審查發現，快速聚焦需要說明的地方。</p>
        </article>
        <article class="process-step">
          <span class="process-step__number">03</span>
          <h3>交付</h3>
          <p>留下清楚結論與完整歷程，讓下一位夥伴接續工作。</p>
        </article>
      </div>
    </section>
  </PublicLayout>
</template>
