<script setup lang="ts">
import { ref } from 'vue'
import { UserCheck } from 'lucide-vue-next'
import LoginModal from '@/components/LoginModal.vue'
import { MdButton, MdCard } from '@/components/m3'

defineProps<{ embed?: boolean }>()
const open = ref(false)
</script>

<template>
  <MdCard variant="tonal" class="workbench-login">
    <h1>个人工作台</h1>
    <p>通过小秘书验证工号后，即可查看用量和使用个人快捷方式。</p>
    <MdButton @click="open = true">
      <template #icon><UserCheck :size="18" /></template>
      小秘书登录
    </MdButton>
    <LoginModal v-model="open" default-mode="employee" :employee-only="embed" />
  </MdCard>
</template>

<style scoped>
.workbench-login h1 { margin-bottom: 8px; font-size: 1.25rem; }
.workbench-login p { margin-bottom: 14px; }
</style>
