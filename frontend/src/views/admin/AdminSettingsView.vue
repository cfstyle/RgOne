<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Server,
  Sliders,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Save,
  MessageSquare,
} from 'lucide-vue-next'
import { api } from '@/api'

interface SystemSettingsForm {
  new_api_base_url: string
  new_api_user_id: string
  new_api_access_token: string
  default_provider_id: string
  default_provider_name: string
  default_agent_model: string
  xiaomishu_api: string
  xiaomishu_send_user: string
  xiaomishu_source: string
}

interface TestGatewayResult {
  success?: boolean
  message?: string
  status?: string
}

const form = ref<SystemSettingsForm>({
  new_api_base_url: 'http://30.20.4.144:3001',
  new_api_user_id: '1',
  new_api_access_token: '',
  default_provider_id: 'new-api-1',
  default_provider_name: '行内大模型平台',
  default_agent_model: 'DeepSeek-V4-Flash-0731-INT8',
  xiaomishu_api: '',
  xiaomishu_send_user: '',
  xiaomishu_source: '金融市场部RPA',
})

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<TestGatewayResult | null>(null)
const saveSuccess = ref(false)

async function loadSettings() {
  loading.value = true
  try {
    const res = await api.getAdminSettings() as { data?: Partial<SystemSettingsForm> }
    const d = res.data || {}
    if (d.new_api_base_url) form.value.new_api_base_url = d.new_api_base_url
    if (d.new_api_user_id) form.value.new_api_user_id = d.new_api_user_id
    if (d.new_api_access_token) form.value.new_api_access_token = d.new_api_access_token
    if (d.default_provider_id) form.value.default_provider_id = d.default_provider_id
    if (d.default_provider_name) form.value.default_provider_name = d.default_provider_name
    if (d.default_agent_model) form.value.default_agent_model = d.default_agent_model
    if (d.xiaomishu_api) form.value.xiaomishu_api = d.xiaomishu_api
    if (d.xiaomishu_send_user) form.value.xiaomishu_send_user = d.xiaomishu_send_user
    if (d.xiaomishu_source) form.value.xiaomishu_source = d.xiaomishu_source
  } catch (e) {
    console.error('加载系统设置失败', e)
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  saveSuccess.value = false
  try {
    await api.updateAdminSettings(form.value as unknown as Record<string, unknown>)
    saveSuccess.value = true
    setTimeout(() => {
      saveSuccess.value = false
    }, 3000)
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '保存设置失败')
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const res = await api.testGateway({
      base_url: form.value.new_api_base_url,
      access_token: form.value.new_api_access_token,
      user_id: form.value.new_api_user_id ? Number(form.value.new_api_user_id) : 1,
    }) as TestGatewayResult
    testResult.value = res
  } catch (e: unknown) {
    const err = e as { message?: string }
    testResult.value = { success: false, message: err.message || '连通测试失败' }
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="admin-settings-view">
    <div class="page-top-bar">
      <div>
        <h2 class="page-title">系统与 new-api 网关配置</h2>
        <p class="page-desc">配置统一算力网关的内网端点、管理员服务访问令牌及客户端默认参数</p>
      </div>

      <div class="top-actions">
        <button class="test-btn md-state-layer" :disabled="testing" @click="handleTest">
          <RefreshCw :size="15" :class="{ rotating: testing }" />
          <span>{{ testing ? '测试中...' : '测试网关连通性' }}</span>
        </button>
        <button class="save-btn md-state-layer" :disabled="saving" @click="handleSave">
          <Save :size="15" />
          <span>{{ saving ? '保存中...' : '保存配置' }}</span>
        </button>
      </div>
    </div>

    <!-- 成功/反馈条 -->
    <div v-if="saveSuccess" class="notice-bar success">
      <CheckCircle2 :size="16" />
      <span>配置已成功更新并持久化至系统数据库！</span>
    </div>

    <div v-if="testResult" class="notice-bar" :class="testResult.success ? 'success' : 'error'">
      <component :is="testResult.success ? CheckCircle2 : AlertCircle" :size="16" />
      <span>{{ testResult.message }}</span>
    </div>

    <div class="settings-card-grid">
      <!-- Card 1: 网关对接配置 -->
      <div class="settings-card studio-elevated-card">
        <div class="card-header">
          <div class="icon-avatar">
            <Server :size="18" />
          </div>
          <div>
            <h3 class="card-title">new-api 聚合网关对接</h3>
            <span class="card-sub">用于自动化签发员工 Token、拉取可用模型与同步消费日志</span>
          </div>
        </div>

        <div class="card-body">
          <div class="f-item">
            <label class="f-label">网关 Base URL*</label>
            <input
              v-model="form.new_api_base_url"
              type="text"
              class="m3-input"
              placeholder="例如：http://30.20.4.144:3001"
            />
            <span class="f-hint">系统将自动拼接 /v1 或 /api 路由进行通信</span>
          </div>

          <div class="f-item">
            <label class="f-label">Service User ID (服务账号用户ID)*</label>
            <input
              v-model="form.new_api_user_id"
              type="text"
              class="m3-input"
              placeholder="例如：1"
            />
            <span class="f-hint">new-api 中具有创建 Token 权限的管理员账号数字 ID</span>
          </div>

          <div class="f-item">
            <label class="f-label">系统访问令牌 (Access Token)*</label>
            <input
              v-model="form.new_api_access_token"
              type="password"
              class="m3-input"
              placeholder="在 new-api 个人设置 -> 系统访问令牌中生成"
            />
            <span class="f-hint">入库将使用 Fernet 对称算法加密存储，避免明文泄露</span>
          </div>
        </div>
      </div>

      <!-- Card 2: 客户端引导默认值 -->
      <div class="settings-card studio-elevated-card">
        <div class="card-header">
          <div class="icon-avatar">
            <Sliders :size="18" />
          </div>
          <div>
            <h3 class="card-title">DeepSeek Harness 客户端默认配置</h3>
            <span class="card-sub">动态生成 cordis.patch.yml 补丁及首页步骤三界面复制的内容</span>
          </div>
        </div>

        <div class="card-body">
          <div class="f-item">
            <label class="f-label">默认 Provider ID*</label>
            <input
              v-model="form.default_provider_id"
              type="text"
              class="m3-input"
              placeholder="例如：new-api-1"
            />
            <span class="f-hint">客户端内部识别模型供应商的唯一英文标识</span>
          </div>

          <div class="f-item">
            <label class="f-label">供应商展示名称 (Display Name)*</label>
            <input
              v-model="form.default_provider_name"
              type="text"
              class="m3-input"
              placeholder="例如：行内大模型平台"
            />
            <span class="f-hint">展示在员工客户端模型列表分组上的中文名称</span>
          </div>

          <div class="f-item">
            <label class="f-label">默认 Agent 编程/推理模型*</label>
            <input
              v-model="form.default_agent_model"
              type="text"
              class="m3-input"
              placeholder="例如：DeepSeek-V4-Flash-0731-INT8"
            />
            <span class="f-hint">员工首次接入时自动预置为默认对话与编程的主力模型</span>
          </div>
        </div>
      </div>

      <!-- Card 3: 小秘书动态验证码与消息推送 -->
      <div class="settings-card studio-elevated-card">
        <div class="card-header">
          <div class="icon-avatar">
            <MessageSquare :size="18" />
          </div>
          <div>
            <h3 class="card-title">小秘书消息网关与动态验证码</h3>
            <span class="card-sub">员工工号登录时用于推送 6 位一次性登录动态验证码 (OTP)</span>
          </div>
        </div>

        <div class="card-body">
          <div class="f-item">
            <label class="f-label">小秘书推送接口 URL (XIAOMISHU_API)</label>
            <input
              v-model="form.xiaomishu_api"
              type="text"
              class="m3-input"
              placeholder="例如：http://30.20.x.x:8080/api/message/send"
            />
            <span class="f-hint">留空时系统将以开发/离线模拟模式运行（控制台打印验证码并在前端提供仿真提示）</span>
          </div>

          <div class="f-item">
            <label class="f-label">推送消息来源标识 (XIAOMISHU_SOURCE)</label>
            <input
              v-model="form.xiaomishu_source"
              type="text"
              class="m3-input"
              placeholder="例如：金融市场部RPA"
            />
            <span class="f-hint">推送卡片中展示的来源前缀，例如：来源: 金融市场部RPA</span>
          </div>

          <div class="f-item">
            <label class="f-label">演练/测试固定接收人 (XIAOMISHU_SEND_USER, 选填)</label>
            <input
              v-model="form.xiaomishu_send_user"
              type="text"
              class="m3-input"
              placeholder="生产环境默认自动投递至各员工工号"
            />
            <span class="f-hint">生产规范：默认严格投递给登录员工工号；固定接收人仅在开启测试模式时作为备用演练接收</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-settings-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.page-desc {
  font-size: 13px;
  color: var(--md-sys-color-outline);
}

.top-actions {
  display: flex;
  gap: 10px;
}

.test-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  border: 1px solid rgba(0, 0, 0, 0.08);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.notice-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 500;
}

.notice-bar.success {
  background-color: #E6F4EA;
  color: #137333;
}

.notice-bar.error {
  background-color: #FEE2E2;
  color: #B91C1C;
}

.settings-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 20px;
}

.settings-card {
  padding: 24px;
  background-color: var(--md-sys-color-surface-container-lowest);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.03), 0 1px 2px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  padding-bottom: 16px;
}

.icon-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-color: var(--md-sys-color-surface-container-highest);
  color: var(--md-sys-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.card-sub {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.f-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.f-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface);
}

.m3-input {
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  font-family: var(--md-sys-typescale-font-family-brand);
  outline: none;
}

.m3-input:focus {
  border-color: var(--md-sys-color-primary);
}

.f-hint {
  font-size: 11px;
  color: var(--md-sys-color-outline);
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
