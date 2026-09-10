<script setup lang="ts">
import { useAuthStore } from '../modules/auth/auth.store'
import AppHeader from '../components/common/AppHeader.vue'
import AppSidebar from '../components/common/AppSidebar.vue'

const auth = useAuthStore()
</script>

<template>
  <div class="app-layout">
    <AppSidebar :permissions="auth.user?.permissions ?? []" />
    <div class="app-main">
      <AppHeader :display-name="auth.user?.displayName ?? ''" @logout="auth.clearSession()" />
      <main class="page-content"><RouterView /></main>
    </div>
  </div>
</template>