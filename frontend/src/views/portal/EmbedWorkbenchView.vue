<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorkbenchCore from '@/components/workbench/WorkbenchCore.vue'
import WorkbenchLogin from '@/components/workbench/WorkbenchLogin.vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

const route = useRoute()
const auth = useAuthStore()
const theme = useThemeStore()
const previousTheme = theme.currentTheme

watch(() => route.query.theme, value => {
  theme.setTheme(value === 'light' || value === 'dark' ? value : previousTheme, false)
}, { immediate: true })
onBeforeUnmount(() => theme.setTheme(previousTheme, false))
</script>

<template>
  <main class="embed-workbench" aria-label="个人工作台">
    <WorkbenchCore v-if="auth.isEmployeeLoggedIn" :key="auth.empToken" :embed="true" />
    <WorkbenchLogin v-else :embed="true" />
  </main>
</template>

<style scoped>
.embed-workbench {
  min-height: 100dvh;
  padding: 12px;
  background: var(--md-sys-color-surface);
  color: var(--md-sys-color-on-surface);
}
</style>
