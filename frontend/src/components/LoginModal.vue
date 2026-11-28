<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick, useId } from 'vue'
import { useRouter } from 'vue-router'
import {
  User,
  ShieldCheck,
  Lock,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Send,
  Eye,
  EyeOff,
} from 'lucide-vue-next'
import { AdaptiveModal, MdButton } from '@/components/m3'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  modelValue: boolean
  defaultMode?: 'employee' | 'admin'
  employeeOnly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'success', userType: 'employee' | 'admin'): void
}>()

const router = useRouter()
const authStore = useAuthStore()
const formId = useId()

// 登录模式：'employee' | 'admin'
const loginMode = ref<'employee' | 'admin'>('employee')

// 表单字段
const account = ref('')
const verifyCode = ref('')
const password = ref('')
const showPassword = ref(false)
const codeInputRef = ref<HTMLInputElement | null>(null)

// 交互状态
const loading = ref(false)
const sendingCode = ref(false)
const countdown = ref(0)
const errorMsg = ref('')
const infoMsg = ref('')
let timer: ReturnType<typeof setInterval> | null = null

// 监听弹窗打开时重置状态
watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      if (props.employeeOnly) {
        loginMode.value = 'employee'
      } else if (props.defaultMode) {
        loginMode.value = props.defaultMode
      }
      resetForm()
    } else {
      clearCountdown()
    }
  }
)

function resetForm() {
  account.value = loginMode.value === 'admin' ? 'admin' : ''
  verifyCode.value = ''
  password.value = ''
  errorMsg.value = ''
  infoMsg.value = ''
}

function switchMode(mode: 'employee' | 'admin') {
  loginMode.value = mode
  resetForm()
}

// 智能感知：若在工号框输入了 admin，可自动切换提示
function onAccountInput() {
  errorMsg.value = ''
  infoMsg.value = ''
  if (!props.employeeOnly && loginMode.value === 'employee' && account.value.trim().toLowerCase() === 'admin') {
    infoMsg.value = '检测到管理员账号，可直接切换为管理员密码登录'
  }
}

// 清除倒计时
function clearCountdown() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  countdown.value = 0
}

// 启动倒计时
function startCountdown(sec: number = 60) {
  clearCountdown()
  countdown.value = sec
  timer = setInterval(() => {
    if (countdown.value > 1) {
      countdown.value -= 1
    } else {
      clearCountdown()
    }
  }, 1000)
}

onUnmounted(() => {
  clearCountdown()
})

// 发送验证码
async function handleSendCode() {
  const acc = account.value.trim()
  if (!acc) {
    errorMsg.value = '请输入员工工号'
    return
  }

  // 若输入了 admin，直接切到管理员模式
  if (acc.toLowerCase() === 'admin') {
    loginMode.value = 'admin'
    account.value = 'admin'
    infoMsg.value = '管理员账号无需验证码，请直接输入密码登录'
    return
  }

  sendingCode.value = true
  errorMsg.value = ''
  infoMsg.value = ''

  try {
    const res = await api.sendVerifyCode(acc) as { is_admin?: boolean; message?: string; cooldown?: number }
    if (res.is_admin) {
      loginMode.value = 'admin'
      account.value = acc
      infoMsg.value = res.message || '管理员账号无需验证码，请输入密码登录'
      return
    }

    startCountdown(res.cooldown || 60)
    infoMsg.value = res.message || '验证码已推送至您的小秘书客户端，5 分钟内有效'
    nextTick(() => {
      codeInputRef.value?.focus()
    })
  } catch (err: unknown) {
    const errorObj = err as { message?: string }
    errorMsg.value = errorObj.message || '获取验证码失败，请核对工号白名单'
  } finally {
    sendingCode.value = false
  }
}

// 统一登录提交
async function handleLogin() {
  const acc = account.value.trim()
  if (!acc) {
    errorMsg.value = loginMode.value === 'admin' ? '请输入管理员账号' : '请输入员工工号'
    return
  }

  if (loginMode.value === 'admin') {
    if (!password.value) {
      errorMsg.value = '请输入管理员密码'
      return
    }
  } else {
    if (!verifyCode.value.trim()) {
      errorMsg.value = '请输入 6 位动态验证码'
      return
    }
  }

  loading.value = true
  errorMsg.value = ''

  try {
    const payload: { account: string; password?: string; code?: string } = { account: acc }
    if (loginMode.value === 'admin') {
      payload.password = password.value
    } else {
      payload.code = verifyCode.value.trim()
    }

    const res = await api.unifiedLogin(payload) as { user_type: string; access_token: string; username?: string; emp_no?: string; name?: string }

    if (res.user_type === 'admin') {
      authStore.setAdminAuth(res.access_token, res.username || acc)
      emit('update:modelValue', false)
      emit('success', 'admin')
      router.push('/admin/dashboard')
    } else {
      authStore.setEmployeeAuth(res.access_token, res.emp_no || acc, res.name || '')
      emit('update:modelValue', false)
      emit('success', 'employee')
      // 登录后留在原业务位置：首页继续配置，工作台继续查看个人信息
    }
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
    :title="employeeOnly ? '小秘书登录' : '统一登录认证'"
    max-width="440px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="unified-login-modal">
      <!-- 极简模式切换 Pill -->
      <div v-if="!employeeOnly" class="mode-pill-group">
        <button
          type="button"
          class="mode-pill-btn"
          :class="{ active: loginMode === 'employee' }"
          @click="switchMode('employee')"
        >
          <User :size="15" />
          <span>工号登录</span>
        </button>
        <button
          type="button"
          class="mode-pill-btn"
          :class="{ active: loginMode === 'admin' }"
          @click="switchMode('admin')"
        >
          <Lock :size="15" />
          <span>管理员密码</span>
        </button>
      </div>

      <!-- 描述文案 -->
      <p class="modal-sub-tip">
        <template v-if="loginMode === 'employee'">
          输入行内工号（如 06700956），动态验证码将通过<b>小秘书即时消息</b>推送到您的客户端。
        </template>
        <template v-else>
          请输入管理员超级权限凭据进入运营支撑后台。
        </template>
      </p>

      <!-- 错误与状态提示条 -->
      <div v-if="errorMsg" class="feedback-banner error">
        <AlertCircle :size="16" class="feedback-icon" />
        <span class="feedback-text">{{ errorMsg }}</span>
      </div>
      <div v-if="infoMsg" class="feedback-banner info">
        <CheckCircle2 :size="16" class="feedback-icon" />
        <span class="feedback-text">{{ infoMsg }}</span>
      </div>

      <!-- 表单主体 -->
      <form :id="formId" class="login-form" @submit.prevent="handleLogin">
        <!-- 账号 / 工号输入框 -->
        <div class="input-field">
          <label class="input-label">
            {{ loginMode === 'admin' ? '管理员账号' : '行内员工工号' }}
          </label>
          <div class="input-wrapper">
            <User :size="18" class="field-icon" />
            <input
              v-model="account"
              type="text"
              class="m3-native-input"
              :placeholder="loginMode === 'admin' ? '默认账号: admin' : '请输入行内工号 (如 06700956 或 06701099)'"
              autocomplete="username"
              @input="onAccountInput"
            />
          </div>
        </div>

        <!-- 员工分支：6 位小秘书动态验证码 -->
        <div v-if="loginMode === 'employee'" class="input-field">
          <label class="input-label">小秘书动态验证码</label>
          <div class="input-wrapper verify-wrapper">
            <ShieldCheck :size="18" class="field-icon" />
            <input
              ref="codeInputRef"
              v-model="verifyCode"
              type="text"
              maxlength="6"
              class="m3-native-input code-input"
              placeholder="请输入 6 位验证码"
              autocomplete="one-time-code"
              @keyup.enter="handleLogin"
            />
            <button
              type="button"
              class="send-code-btn"
              :disabled="sendingCode || countdown > 0 || !account.trim()"
              @click="handleSendCode"
            >
              <Send v-if="!countdown && !sendingCode" :size="13" />
              <span>{{ countdown > 0 ? `${countdown}s 后重新获取` : sendingCode ? '发送中...' : '获取验证码' }}</span>
            </button>
          </div>
        </div>

        <!-- 管理员分支：管理员密码 -->
        <div v-else class="input-field">
          <label class="input-label">管理员密码</label>
          <div class="input-wrapper">
            <Lock :size="18" class="field-icon" />
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="m3-native-input"
              placeholder="请输入管理员密码"
              autocomplete="current-password"
              @keyup.enter="handleLogin"
            />
            <button
              type="button"
              class="pwd-toggle-btn"
              tabindex="-1"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" :size="16" />
              <Eye v-else :size="16" />
            </button>
          </div>
        </div>

      </form>

      <!-- 底部辅助切换 -->
      <div v-if="!employeeOnly" class="modal-footer-hint">
        <span v-if="loginMode === 'employee'">
          管理员维护请点击
          <button type="button" class="link-switch-btn" @click="switchMode('admin')">
            切换为管理员密码登录
          </button>
        </span>
        <span v-else>
          员工查验请点击
          <button type="button" class="link-switch-btn" @click="switchMode('employee')">
            返回员工工号验证
          </button>
        </span>
      </div>
    </div>
    <template #actions>
      <MdButton type="submit" :form="formId" :disabled="loading">
        {{ loading ? '正在验证…' : loginMode === 'admin' ? '进入管理后台' : '工号登录' }}
        <template #trailingIcon><ArrowRight :size="16" /></template>
      </MdButton>
    </template>
  </AdaptiveModal>
</template>

<style scoped>
.unified-login-modal {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 模式切换胶囊组 */
.mode-pill-group {
  display: flex;
  padding: 4px;
  background-color: var(--md-sys-color-surface-container);
  border-radius: 24px;
  gap: 4px;
}

.mode-pill-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  background: transparent;
  border: none;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.2, 0, 0, 1);
}

.mode-pill-btn.active {
  background: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  font-weight: 600;
  box-shadow: 0 1px 4px var(--md-sys-color-outline-variant);
}

.modal-sub-tip {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--md-sys-color-on-surface-variant);
}

.modal-sub-tip b {
  color: var(--md-sys-color-on-surface);
  font-weight: 600;
}

/* 状态反馈 Banner */
.feedback-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.feedback-banner.error {
  background-color: var(--md-sys-color-error-container);
  color: var(--md-sys-color-on-error-container);
}

.feedback-banner.info {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.feedback-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.feedback-text {
  flex: 1;
  word-break: break-all;
}

/* 表单主体 */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.input-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  background-color: var(--md-sys-color-surface-container-lowest);
  border: 1px solid var(--md-sys-color-outline-variant);
  border-radius: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-wrapper:focus-within {
  border-color: var(--md-sys-color-on-surface);
  box-shadow: 0 0 0 2px var(--md-sys-color-outline-variant);
}

.field-icon {
  position: absolute;
  left: 14px;
  color: var(--md-sys-color-on-surface-variant);
  pointer-events: none;
}

.m3-native-input {
  width: 100%;
  padding: 12px 14px 12px 42px;
  font-family: inherit;
  font-size: 14px;
  color: var(--md-sys-color-on-surface);
  background: transparent;
  border: none;
  outline: none;
}

.m3-native-input::placeholder {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 13px;
}

/* 验证码输入框及按钮 */
.verify-wrapper {
  padding-right: 6px;
}

.code-input {
  letter-spacing: 2px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.send-code-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface);
  background-color: var(--md-sys-color-surface-container);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-code-btn:hover:not(:disabled) {
  background-color: var(--md-sys-color-surface-container-high);
}

.send-code-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  color: var(--md-sys-color-on-surface-variant);
}

.pwd-toggle-btn {
  padding: 8px 12px;
  background: transparent;
  border: none;
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pwd-toggle-btn:hover {
  color: var(--md-sys-color-on-surface);
}

/* 登录主按钮：实心墨黑胶囊 */




/* 底部辅助链接 */
.modal-footer-hint {
  text-align: center;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  padding-top: 4px;
}

.link-switch-btn {
  background: transparent;
  border: none;
  color: var(--md-sys-color-on-surface);
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
  padding: 0 2px;
  font-size: 12px;
}

.link-switch-btn:hover {
  color: var(--md-sys-color-primary);
}
</style>
