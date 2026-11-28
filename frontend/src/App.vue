<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'
import MdSnackbar from '@/components/m3/MdSnackbar.vue'

const themeStore = useThemeStore()

themeStore.initTheme()
</script>

<template>
  <router-view />
  <MdSnackbar />
</template>

<style>
/* App 顶级容器挂载 */
</style>
