<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useRouter } from 'vue-router'
import PageHeader from '../../../components/common/PageHeader.vue'
import { useAuthStore } from '../../../stores/auth.store'
import { homeFor } from '../../../router/roleHomeMap'

const authStore = useAuthStore()
const router = useRouter()
const safeHome = computed(() => homeFor(authStore.user))
const isUnknownRole = computed(() => safeHome.value === '/app/unauthorized')

function returnToLogin(): void {
  authStore.logout()
  void router.replace('/')
}
</script>

<template>
  <section class="unauthorized-view" aria-labelledby="unauthorized-title">
    <PageHeader eyebrow="ACCESS CONTROL" title="目前無法開啟這個功能" description="你的帳號尚未被授予此工作模組的權限。若你認為這是錯誤，請向系統管理者確認。" />
    <div class="unauthorized-view__card">
      <span class="unauthorized-view__code" aria-hidden="true">403</span>
      <div>
        <h2 id="unauthorized-title">權限不足</h2>
        <p>頁面內容不會在瀏覽器中載入，請從目前帳號可用的工作模組繼續。</p>
        <RouterLink v-if="!isUnknownRole" class="unauthorized-view__link" :to="safeHome">回到可用工作台</RouterLink>
        <button
          v-else
          class="unauthorized-view__link"
          type="button"
          aria-label="返回登入"
          @click="returnToLogin"
        >
          返回登入
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.unauthorized-view {
  min-height: calc(100vh - 132px);
  padding: 0 26px 40px;
}

.unauthorized-view__card {
  display: flex;
  align-items: center;
  gap: 24px;
  max-width: 700px;
  margin: 40px auto 0;
  padding: 30px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-paper);
}

.unauthorized-view__code {
  color: var(--app-accent);
  font-family: var(--app-font-display);
  font-size: clamp(44px, 8vw, 82px);
  font-weight: 600;
  line-height: 1;
}

.unauthorized-view h2 {
  margin: 0;
  color: var(--app-ink);
  font-size: 20px;
}

.unauthorized-view p {
  margin: 10px 0 0;
  color: var(--app-ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.unauthorized-view__link {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  margin-top: 18px;
  padding: 0 16px;
  border-radius: var(--app-radius-pill);
  color: #fff8f2;
  background: var(--app-accent);
  border: 0;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  font-weight: 800;
  text-decoration: none;
}

@media (max-width: 640px) {
  .unauthorized-view {
    padding-inline: 16px;
  }

  .unauthorized-view__card {
    align-items: flex-start;
    flex-direction: column;
    margin-top: 16px;
    padding: 22px;
  }
}
</style>
