<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, User, AlertCircle, ArrowRight } from 'lucide-vue-next'
import { AdaptiveModal, MdButton } from '@/components/m3'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()

const router = useRouter()
const authStore = useAuthStore()

const username = ref('admin')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  if (!username.value.trim() || !password.value.trim()) {
    errorMsg.value = '请输入管理员账号与密码'
    return
  }

  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.adminLogin(username.value.trim(), password.value) as { access_token: string; username?: string }
    authStore.setAdminAuth(res.access_token, res.username || username.value)
    emit('update:modelValue', false)
    router.push('/admin/dashboard')
  } catch (err: unknown) {
    const errorObj = err as { message?: string }
    errorMsg.value = errorObj.message || '登录失败，请核对凭证'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AdaptiveModal
    :model-value="modelValue"
    title="管理后台身份验证"
    max-width="420px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="admin-login-modal">
      <p class="admin-tip">
        请输入超级管理员凭据以进入管理后台。初次登录默认账号为 <code>admin</code>。
      </p>

      <div v-if="errorMsg" class="error-banner">
        <AlertCircle :size="16" />
        <span>{{ errorMsg }}</span>
      </div>

      <div class="input-field">
        <label class="input-label">管理员账号</label>
        <div class="input-wrapper">
          <User :size="18" class="field-icon" />
          <input
            v-model="username"
            type="text"
            class="m3-native-input"
            placeholder="输入管理员账号"
            @keyup.enter="handleLogin"
          />
        </div>
      </div>

      <div class="input-field">
        <label class="input-label">管理员密码</label>
        <div class="input-wrapper">
          <Lock :size="18" class="field-icon" />
          <input
            v-model="password"
            type="password"
            class="m3-native-input"
            placeholder="输入管理员密码"
            autofocus
            @keyup.enter="handleLogin"
          />
        </div>
      </div>

      <div class="modal-actions">
        <MdButton variant="text" @click="emit('update:modelValue', false)">取消</MdButton>
        <MdButton variant="filled" :disabled="loading" @click="handleLogin">
          {{ loading ? '验证中...' : '登录后台' }}
          <ArrowRight :size="16" style="margin-left: 6px" />
        </MdButton>
      </div>
    </div>
  </AdaptiveModal>
</template>

<style scoped>
.admin-login-modal {
  padding: 8px 4px 16px;
}

.admin-tip {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.5;
  margin-bottom: 16px;
}

.admin-tip code {
  background-color: var(--md-sys-color-surface-container-high);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background-color: var(--md-sys-color-error-container);
  color: var(--md-sys-color-on-error-container);
  border-radius: var(--md-sys-shape-corner-small);
  margin-bottom: 16px;
  font-size: 13px;
}

.input-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.input-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.field-icon {
  position: absolute;
  left: 12px;
  color: var(--md-sys-color-outline);
  pointer-events: none;
}

.m3-native-input {
  width: 100%;
  padding: 11px 14px 11px 38px;
  border-radius: var(--md-sys-shape-corner-small);
  border: 1px solid var(--md-sys-color-outline);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.m3-native-input:focus {
  border-color: var(--md-sys-color-primary);
  border-width: 2px;
  padding: 10px 13px 10px 37px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}
</style>
