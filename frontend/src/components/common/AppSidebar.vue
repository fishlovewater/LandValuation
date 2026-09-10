<script setup lang="ts">
defineProps<{ permissions: string[] }>()
</script>
<template>
  <aside class="app-sidebar">
    <div class="sidebar-brand">LVA</div>
    <nav aria-label="主要導覽">
      <RouterLink v-if="permissions.includes('review.execute')" to="/app/review/dashboard">智慧審查</RouterLink>
    </nav>
  </aside>
</template>