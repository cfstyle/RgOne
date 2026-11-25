<script setup lang="ts">
import { ref } from 'vue'
import {
  ShieldCheck,
  Check,
  Copy,
  AlertCircle,
  ArrowRight,
  Sparkles,
} from 'lucide-vue-next'
import { AdaptiveModal, MdButton } from '@/components/m3'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'success'): void
}>()

const authStore = useAuthStore()

const step = ref<1 | 2 | 3>(1) // 1: 查工号, 2: 核验全名, 3: 成功展示 Key
const empNo = ref('')
const fullName = ref('')
const maskedName = ref('')
const department = ref('')
const issuedKey = ref('')
const copied = ref(false)

const loading = ref(false)
const errorMsg = ref('')

function resetModal() {
  step.value = 1
  empNo.value = ''
  fullName.value = ''
  maskedName.value = ''
  department.value = ''
  issuedKey.value = ''
  errorMsg.value = ''
  copied.value = false
}

function handleClose() {
  emit('update:modelValue', false)
  setTimeout(resetModal, 300)
}

// 步骤 1：仅查工号，获取脱敏信息
async function handleLookup() {
  if (!empNo.value.trim()) {
    errorMsg.value = '请输入员工工号'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.lookupEmployee(empNo.value.trim()) as { masked_name: string; department: string }
    maskedName.value = res.masked_name
    department.value = res.department
    step.value = 2
  } catch (err: unknown) {
    const errorObj = err as { message?: string }
    errorMsg.value = errorObj.message || '工号不存在，请联系管理员导入'
  } finally {
    loading.value = false
  }
}

// 步骤 2：提交完整姓名双向匹配，自动签发专属 Key
async function handleVerify() {
  if (!fullName.value.trim()) {
    errorMsg.value = '请输入完整真实姓名'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.verifyEmployee(empNo.value.trim(), fullName.value.trim()) as { access_token: string; emp_no: string; name: string }
    authStore.setEmployeeAuth(res.access_token, res.emp_no, res.name)

    // 获取明文 Key
    const tokenDetail = await api.getMyToken() as { api_key: string }
    issuedKey.value = tokenDetail.api_key
    step.value = 3
    emit('success')
  } catch (err: unknown) {
    const errorObj = err as { message?: string }
    errorMsg.value = errorObj.message || '核验未通过，请检查姓名是否输入正确'
  } finally {
    loading.value = false
  }
}

async function handleCopyKey() {
  if (!issuedKey.value) return
  await navigator.clipboard.writeText(issuedKey.value)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}
</script>

<template>
  <AdaptiveModal
    :model-value="modelValue"
    title="员工工号身份核验与 Key 申领"
    max-width="500px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="verify-modal-content">
      <!-- 顶部指示徽章 -->
      <div class="verify-steps-indicator">
        <div class="step-dot" :class="{ active: step === 1, done: step > 1 }">1. 查验工号</div>
        <div class="step-divider" />
        <div class="step-dot" :class="{ active: step === 2, done: step > 2 }">2. 姓名匹配</div>
        <div class="step-divider" />
        <div class="step-dot" :class="{ active: step === 3 }">3. 专属 Key</div>
      </div>

      <!-- 错误提示 Banner -->
      <div v-if="errorMsg" class="error-banner">
        <AlertCircle :size="18" />
        <span>{{ errorMsg }}</span>
      </div>

      <!-- 步骤 1：仅输工号 -->
      <div v-if="step === 1" class="step-pane">
        <p class="step-tip">
          请输入您的行内工号。系统仅进行脱敏比对，无需输入任何密码，绝不泄露个人全名。
        </p>
        <div class="input-field">
          <label class="input-label">员工工号 (Emp ID)</label>
          <input
            v-model="empNo"
            type="text"
            class="m3-native-input"
            placeholder="例如：06700956"
            autofocus
            @keyup.enter="handleLookup"
          />
        </div>
        <div class="step-actions">
          <MdButton variant="text" @click="handleClose">取消</MdButton>
          <MdButton variant="filled" :disabled="loading" @click="handleLookup">
            {{ loading ? '查询中...' : '下一步' }}
            <ArrowRight :size="16" style="margin-left: 6px" />
          </MdButton>
        </div>
      </div>

      <!-- 步骤 2：姓名双向精准匹配 -->
      <div v-else-if="step === 2" class="step-pane">
        <div class="match-info-card">
          <div class="info-row">
            <span class="info-k">工号：</span>
            <span class="info-v">{{ empNo }}</span>
          </div>
          <div class="info-row">
            <span class="info-k">所在部门：</span>
            <span class="info-v">{{ department }}</span>
          </div>
          <div class="info-row">
            <span class="info-k">系统脱敏姓名：</span>
            <span class="info-v highlight">{{ maskedName }}</span>
          </div>
        </div>

        <p class="step-tip" style="margin-top: 12px">
          为防止他人冒领，请在下方输入您的<strong>完整真实姓名</strong>以完成双向精准匹配：
        </p>

        <div class="input-field">
          <label class="input-label">完整姓名</label>
          <input
            v-model="fullName"
            type="text"
            class="m3-native-input"
            placeholder="请输入完整姓名进行比对"
            autofocus
            @keyup.enter="handleVerify"
          />
        </div>

        <div class="step-actions">
          <MdButton variant="text" @click="step = 1">返回修改工号</MdButton>
          <MdButton variant="filled" :disabled="loading" @click="handleVerify">
            {{ loading ? '核验签发中...' : '确认核验并签发' }}
            <ShieldCheck :size="16" style="margin-left: 6px" />
          </MdButton>
        </div>
      </div>

      <!-- 步骤 3：成功签发展示 Key -->
      <div v-else-if="step === 3" class="step-pane success-pane">
        <div class="success-icon-badge">
          <Sparkles :size="32" />
        </div>
        <h3 class="success-title">专属 API Key 签发成功！</h3>
        <p class="success-subtitle">
          欢迎 <strong>{{ fullName }}</strong>（{{ department }}）已为您分配专属无限额度 Token。
        </p>

        <div class="key-display-box">
          <span class="key-text">{{ issuedKey }}</span>
          <button class="copy-btn md-state-layer" @click="handleCopyKey">
            <Check v-if="copied" :size="16" style="color: var(--md-sys-color-primary)" />
            <Copy v-else :size="16" />
            <span>{{ copied ? '已复制' : '复制' }}</span>
          </button>
        </div>

        <p class="key-hint">
          可在首页第 3 步一键填入 DeepSeek Harness 客户端，或进入「我的工作台」查看用量趋势。
        </p>

        <div class="step-actions center">
          <MdButton variant="filled" @click="handleClose"> 完成 </MdButton>
        </div>
      </div>
    </div>
  </AdaptiveModal>
</template>

<style scoped>
.verify-modal-content {
  padding: 8px 4px 16px;
}

.verify-steps-indicator {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding: 8px 12px;
  background-color: var(--md-sys-color-surface-container);
  border-radius: var(--md-sys-shape-corner-medium);
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.step-dot {
  font-weight: 500;
  transition: color 0.2s;
}

.step-dot.active {
  color: var(--md-sys-color-primary);
  font-weight: 700;
}

.step-dot.done {
  color: var(--md-sys-color-outline);
}

.step-divider {
  flex: 1;
  height: 1px;
  background-color: var(--md-sys-color-outline-variant);
  margin: 0 10px;
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
  font-size: 14px;
}

.step-tip {
  font-size: 14px;
  line-height: 1.6;
  color: var(--md-sys-color-on-surface-variant);
  margin-bottom: 16px;
}

.input-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 20px;
}

.input-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.m3-native-input {
  width: 100%;
  padding: 12px 14px;
  border-radius: var(--md-sys-shape-corner-small);
  border: 1px solid var(--md-sys-color-outline);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 15px;
  outline: none;
  transition: border-color 0.2s;
}

.m3-native-input:focus {
  border-color: var(--md-sys-color-primary);
  border-width: 2px;
  padding: 11px 13px;
}

.match-info-card {
  padding: 12px 16px;
  background-color: var(--md-sys-color-surface-container);
  border-radius: var(--md-sys-shape-corner-small);
  font-size: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-row {
  display: flex;
  align-items: center;
}

.info-k {
  width: 120px;
  color: var(--md-sys-color-on-surface-variant);
}

.info-v {
  font-weight: 500;
  color: var(--md-sys-color-on-surface);
}

.info-v.highlight {
  font-size: 16px;
  color: var(--md-sys-color-primary);
  font-weight: 700;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.step-actions.center {
  justify-content: center;
}

.success-pane {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 12px 0;
}

.success-icon-badge {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-primary-container);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.success-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 6px;
}

.success-subtitle {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
  margin-bottom: 16px;
}

.key-display-box {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background-color: var(--md-sys-color-surface-container-high);
  border: 1px solid var(--md-sys-color-outline-variant);
  border-radius: var(--md-sys-shape-corner-small);
  margin-bottom: 10px;
}

.key-text {
  font-family: monospace;
  font-size: 14px;
  color: var(--md-sys-color-primary);
  word-break: break-all;
  text-align: left;
}

.copy-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background-color: var(--md-sys-color-surface-container-highest);
  color: var(--md-sys-color-on-surface);
  border-radius: var(--md-sys-shape-corner-small);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  margin-left: 10px;
}

.key-hint {
  font-size: 13px;
  color: var(--md-sys-color-outline);
  margin-bottom: 16px;
}
</style>
