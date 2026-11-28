<script setup lang="ts">
import WorkbenchCore from '@/components/workbench/WorkbenchCore.vue'
import WorkbenchLogin from '@/components/workbench/WorkbenchLogin.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>

<template>
  <WorkbenchCore v-if="auth.isEmployeeLoggedIn" :key="auth.empToken" :embed="false" />
  <WorkbenchLogin v-else />
</template>
