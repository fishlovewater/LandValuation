<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import PageHeader from '../components/common/PageHeader.vue'
import { authorizedModules } from '../components/common/appModules'
import { liquidGlass as vLiquidGlass } from '../directives/liquidGlass'
import { useAuthStore } from '../stores/auth.store'
import { userRoleLabel } from '../utils/fieldLabels'

const authStore = useAuthStore()

const modules = computed(() => authorizedModules(authStore.permissions, authStore.roles))
const displayName = computed(() => authStore.user?.displayName || authStore.user?.username || '目前使用者')

</script>

<template>
  <section class="app-home" data-testid="app-home">
    <PageHeader
      eyebrow="工作台"
      title="工作台總覽"
      :description="`${displayName}，以下只顯示目前帳號可以使用的工作模組。`"
    />

    <section v-liquid-glass data-lg class="app-home__identity lg" aria-labelledby="workspace-user-title">
      <div>
        <span class="app-home__eyebrow">目前帳號</span>
        <h2 id="workspace-user-title">{{ displayName }}</h2>
        <p>{{ authStore.user?.email || authStore.user?.username || '已登入工作帳號' }}</p>
      </div>
      <div class="app-home__roles" aria-label="目前角色">
        <span v-for="role in authStore.roles" :key="role">{{ userRoleLabel(role) }}</span>
      </div>
    </section>

    <section class="app-home__modules" aria-labelledby="workspace-modules-title">
      <div class="app-home__section-heading">
        <div>
          <span class="app-home__eyebrow">可用功能</span>
          <h2 id="workspace-modules-title">開始工作</h2>
        </div>
        <span>{{ modules.length }} 個可用模組</span>
      </div>

      <div v-if="modules.length" class="app-home__grid">
        <RouterLink
          v-for="module in modules"
          :key="module.key"
          v-liquid-glass
          data-lg
          class="app-home__module lg"
          :to="module.path"
          :data-testid="`home-module-${module.key}`"
        >
          <span class="app-home__module-icon" aria-hidden="true">
            <component :is="module.icon" :size="24" weight="duotone" />
          </span>
          <span class="app-home__module-copy">
            <strong>{{ module.label }}</strong>
            <small>{{ module.description }}</small>
          </span>
          <span class="app-home__arrow" aria-hidden="true">→</span>
        </RouterLink>
      </div>
      <div v-else class="app-home__empty">
        <strong>目前帳號沒有可開啟的工作模組</strong>
        <p>請由系統管理者確認角色與權限設定。</p>
      </div>
    </section>
  </section>
</template>

<style scoped>
.app-home { padding:0 28px 34px; }
.app-home__identity { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-top:12px; padding:20px; border:1px solid rgba(255,255,255,.72); border-radius:var(--app-radius-md); background:rgba(255,255,255,.72); box-shadow:var(--app-shadow-soft); }
.app-home__eyebrow { color:var(--app-accent-deep); font-size:9px; font-weight:900; letter-spacing:.16em; }
.app-home__identity h2,
.app-home__section-heading h2 { margin:5px 0 0; color:var(--app-ink); font-family:var(--app-font-display); font-size:24px; }
.app-home__identity p { margin:7px 0 0; color:var(--app-muted); font-size:12px; }
.app-home__roles { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:7px; }
.app-home__roles span { padding:6px 9px; border:1px solid var(--app-line); border-radius:999px; color:var(--app-primary-deep); background:var(--app-primary-soft); font-size:10px; font-weight:900; }
.app-home__modules { margin-top:20px; }
.app-home__section-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom:12px; }
.app-home__section-heading > span { color:var(--app-muted); font-size:11px; font-weight:800; }
.app-home__grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }
.app-home__module { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:12px; min-height:98px; padding:16px; border:1px solid rgba(255,255,255,.76); border-radius:var(--app-radius-sm); color:inherit; background:rgba(255,255,255,.75); box-shadow:var(--app-shadow-soft); text-decoration:none; transition:transform 150ms ease,border-color 150ms ease,box-shadow 150ms ease; }
.app-home__module:hover { transform:translateY(-1px); border-color:rgba(200,91,67,.26); box-shadow:0 12px 28px rgba(43,62,83,.11); }
.app-home__module-icon { display:grid; width:46px; height:46px; place-items:center; border-radius:12px; color:var(--app-primary-deep); background:var(--app-primary-soft); }
.app-home__module-copy { display:grid; gap:4px; min-width:0; }
.app-home__module-copy strong { color:var(--app-ink); font-size:14px; }
.app-home__module-copy small { color:var(--app-muted); font-size:11px; line-height:1.5; }
.app-home__arrow { color:var(--app-primary); font-size:18px; font-weight:900; }
.app-home__empty { padding:24px; border:1px dashed var(--app-line); border-radius:var(--app-radius-sm); color:var(--app-ink-soft); background:var(--app-surface-muted); }
.app-home__empty p { margin:6px 0 0; color:var(--app-muted); font-size:12px; }
@media (max-width:640px) {
  .app-home { padding-inline:14px; }
  .app-home__identity,
  .app-home__section-heading { align-items:flex-start; flex-direction:column; }
  .app-home__roles { justify-content:flex-start; }
}
</style>