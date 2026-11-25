<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Download,
  KeyRound,
  Sliders,
  Check,
  Copy,
  FileCode,
  Layers,
  Image as ImageIcon,
  MessageSquare,
  Info,
  Eye,
  EyeOff,
  RotateCcw,
  AlertTriangle,
  UserCheck,
} from 'lucide-vue-next'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import LoginModal from '@/components/LoginModal.vue'
import { copyToClipboard } from '@/utils/clipboard'

export interface ModelItem {
  id: string
  display_name: string
  input: string[]
  context_length: number
  is_recommended: boolean
  description: string
}

export interface GatewayStatus {
  success?: boolean
  gateway_connected?: boolean
  is_mock?: boolean
  message?: string
}

export interface InstallerData {
  id: number
  title: string
  version: string
  description: string
  file_size: number
  sha256: string
  download_url: string
}

export interface UserTokenDetail {
  emp_no: string
  name: string
  department: string
  token_name: string
  api_key: string
  masked_key: string
  base_url: string
  provider_id: string
  provider_name: string
  api_protocol: string
  default_model: string
  status?: string
  reset_count: number
  created_at: string
}

const authStore = useAuthStore()

const showLoginModal = ref(false)
const activeConfigTab = ref<'gui' | 'patch'>('gui')
const showPlainKey = ref(false)
const isClaiming = ref(false)

// 模型清单与主推安装包
const models = ref<ModelItem[]>([])
const gatewayStatus = ref<GatewayStatus>({})
const installer = ref<InstallerData | null>(null)
const myTokenDetail = ref<UserTokenDetail | null>(null)

// 复制状态记录
const copiedField = ref<string>('')

async function copyText(text: string, fieldKey: string) {
  if (!text) return
  const ok = await copyToClipboard(text)
  if (ok) {
    copiedField.value = fieldKey
    setTimeout(() => {
      copiedField.value = ''
    }, 2000)
  }
}

async function loadPortalData() {
  try {
    const [mRes, sRes, instRes] = await Promise.all([
      api.getModels() as Promise<{ data?: ModelItem[] }>,
      api.getGatewayStatus() as Promise<GatewayStatus>,
      api.getRecommendedInstaller() as Promise<{ has_installer?: boolean; data?: InstallerData }>,
    ])
    models.value = mRes.data || []
    gatewayStatus.value = sRes
    if (instRes.has_installer && instRes.data) {
      installer.value = instRes.data
    }
  } catch (e) {
    console.error('加载网关公共数据失败', e)
  }

  // 若已登录，拉取专属配置与明文 Key
  if (authStore.isEmployeeLoggedIn) {
    try {
      myTokenDetail.value = (await api.getMyToken()) as UserTokenDetail
    } catch (e) {
      console.warn('获取用户 Token 异常', e)
    }
  }
}

function handleVerifySuccess() {
  loadPortalData()
}

async function handleClaimKey() {
  if (isClaiming.value) return
  isClaiming.value = true
  try {
    myTokenDetail.value = (await api.claimMyToken()) as UserTokenDetail
  } catch (err: unknown) {
    const errObj = err as { message?: string }
    alert(errObj.message || '申领 Key 失败，请检查算力网关状态后重试')
  } finally {
    isClaiming.value = false
  }
}

onMounted(() => {
  loadPortalData()
})
</script>

<template>
  <div class="home-guide-view">
    <!-- 顶部状态与模型能力展示（无多余外大框） -->
    <section class="models-overview-section">
      <div class="status-top-row">
        <div class="gateway-status-pill">
          <span class="status-dot" />
          <span>算力网关就绪 · 已接入 {{ models.length }} 款内网大模型</span>
        </div>
        <span class="status-desc-text">
          纯内网离线专线提供 · 支持深度推理、代码补全与图文多模态
        </span>
      </div>

      <!-- 模型纯白浮雕卡片平铺 -->
      <div class="models-grid">
        <div
          v-for="m in models"
          :key="m.id"
          class="model-elevated-card studio-elevated-card"
        >
          <div class="model-card-header">
            <span class="model-name-text">{{ m.id }}</span>
            <span v-if="m.is_recommended" class="main-rec-badge">主力推荐</span>
          </div>
          <p class="model-desc-text">{{ m.description }}</p>
          <div class="model-tags-row">
            <span v-for="inp in m.input" :key="inp" class="m-tag-pill">
              <component :is="inp === 'image' ? ImageIcon : MessageSquare" :size="12" />
              <span>{{ inp === 'image' ? '多模态 (图文)' : '纯文本' }}</span>
            </span>
            <span class="m-tag-pill">{{ Math.round((m.context_length || 32768) / 1024) }}k 上下文</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 三步式新手接入引导向导 -->
    <section class="stepper-section">
      <div class="section-title-box">
        <h2 class="section-title">DeepSeek Harness 零门槛三步接入指引</h2>
        <p class="section-desc">
          只需 3 分钟，即可将您的工作电脑连接至行内统一大模型集群，享受无缝代码辅助与深度推理
        </p>
      </div>

      <div class="stepper-timeline">
        <!-- Step 1: 下载安装包 -->
        <div class="step-card studio-elevated-card">
          <div class="step-badge-col">
            <div class="step-num-badge">1</div>
            <div class="step-connector-line" />
          </div>
          <div class="step-card-content">
            <div class="step-card-header">
              <h3 class="step-heading">下载并安装客户端</h3>
              <span class="step-sub">官方内网特调 Windows 安装包</span>
            </div>
            <p class="step-text">
              行内定制版 DeepSeek Harness 客户端已针对内网网络与高分屏进行显示优化。
            </p>

            <div v-if="installer" class="installer-strip">
              <div class="inst-icon-base">
                <Layers :size="20" />
              </div>
              <div class="inst-meta">
                <div class="inst-title">{{ installer.title }}</div>
                <div class="inst-details">
                  版本: {{ installer.version }} · 大小:
                  {{ (installer.file_size > 0 ? (installer.file_size / (1024 * 1024)).toFixed(1) : '128.4') }} MB
                </div>
              </div>
              <a :href="installer.download_url" class="inst-dl-btn md-state-layer">
                <Download :size="15" />
                <span>一键下载安装包</span>
              </a>
            </div>
            <div v-else class="installer-strip fallback">
              <span>暂无可下载安装包，请联系管理员上传</span>
            </div>
          </div>
        </div>

        <!-- Step 2: 工号登录获取专属 Key -->
        <div class="step-card studio-elevated-card">
          <div class="step-badge-col">
            <div class="step-num-badge">2</div>
            <div class="step-connector-line" />
          </div>
          <div class="step-card-content">
            <div class="step-card-header">
              <h3 class="step-heading">工号登录获取专属 Key</h3>
              <span class="step-sub">小秘书动态验证 · 专属安全凭证</span>
            </div>
            <p class="step-text">
              员工登录工号后直接申领长期有效的个人专属 API 密钥，享受不限额度调用保障。
            </p>

            <div v-if="authStore.isEmployeeLoggedIn && myTokenDetail" class="logged-key-strip">
              <div class="key-strip-top">
                <span class="key-user-meta">
                  <UserCheck :size="16" />
                  {{ myTokenDetail.name }} · {{ myTokenDetail.emp_no }}
                  <span v-if="myTokenDetail.department"> · {{ myTokenDetail.department }}</span>
                </span>
                <span v-if="myTokenDetail.status === 'pending_claim' || !myTokenDetail.api_key" class="status-pill warning">
                  待申领 Key
                </span>
                <span v-else class="status-pill success">已授权就绪</span>
              </div>

              <!-- 若 Key 暂未申领成功（如网关故障），提供免验证码重新申领 -->
              <div v-if="myTokenDetail.status === 'pending_claim' || !myTokenDetail.api_key" class="key-strip-bottom retry-row">
                <span class="pending-tip-text">
                  <AlertTriangle :size="15" />
                  已登录，Key 暂未申领成功（网关服务可能未就绪）
                </span>
                <button
                  type="button"
                  class="copy-pill-btn primary md-state-layer"
                  :disabled="isClaiming"
                  @click="handleClaimKey"
                >
                  <RotateCcw :size="14" :class="{ 'spin-icon': isClaiming }" />
                  <span>{{ isClaiming ? '正在申领...' : '重新申领' }}</span>
                </button>
              </div>

              <!-- 正常就绪态：默认掩码展示，支持显隐与复制 -->
              <div v-else class="key-strip-bottom">
                <code class="key-code-block">{{ showPlainKey ? myTokenDetail.api_key : (myTokenDetail.masked_key || 'sk-••••••••') }}</code>
                <button
                  type="button"
                  class="toggle-eye-btn"
                  title="显示/隐藏明文"
                  @click="showPlainKey = !showPlainKey"
                >
                  <EyeOff v-if="showPlainKey" :size="14" />
                  <Eye v-else :size="14" />
                </button>
                <button
                  type="button"
                  class="copy-pill-btn md-state-layer"
                  :class="{ copied: copiedField === 'step2_key' }"
                  @click="copyText(myTokenDetail.api_key, 'step2_key')"
                >
                  <Check v-if="copiedField === 'step2_key'" :size="14" />
                  <Copy v-else :size="14" />
                  <span>{{ copiedField === 'step2_key' ? '已复制' : '复制 Key' }}</span>
                </button>
              </div>
            </div>
            <div v-else class="verify-trigger-strip">
              <span class="trigger-intro">尚未登录工号，点击右侧工号登录即刻获取专属 API Key</span>
              <button
                type="button"
                class="trigger-action-btn md-state-layer"
                @click="showLoginModal = true"
              >
                <KeyRound :size="15" />
                <span>立即工号登录获取 Key</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Step 3: 配置客户端（双轨模式 Tab） -->
        <div class="step-card studio-elevated-card">
          <div class="step-badge-col">
            <div class="step-num-badge">3</div>
          </div>
          <div class="step-card-content">
            <div class="step-card-header">
              <h3 class="step-heading">配置客户端（推荐粘贴或一键补丁）</h3>
              <span class="step-sub">对齐 DeepSeek Harness 自定义模型 API 字段</span>
            </div>

            <!-- Tab 切换器 -->
            <div class="config-tabs-nav">
              <button
                type="button"
                class="config-tab-btn"
                :class="{ active: activeConfigTab === 'gui' }"
                @click="activeConfigTab = 'gui'"
              >
                <Sliders :size="15" />
                <span>模式一：界面粘贴配置（对照客户端直接填）</span>
              </button>
              <button
                type="button"
                class="config-tab-btn"
                :class="{ active: activeConfigTab === 'patch' }"
                @click="activeConfigTab = 'patch'"
              >
                <FileCode :size="15" />
                <span>模式二：配置文件补丁（一键覆盖更省心）</span>
              </button>
            </div>

            <!-- Tab 1: GUI 复制配置 -->
            <div v-if="activeConfigTab === 'gui'" class="tab-pane">
              <p class="tab-instruction">
                打开 DeepSeek Harness 客户端，点击左下角
                <code>设置 (Settings) → 模型 (Models) → 自定义模型 API</code>，逐项点击下方复制并填入：
              </p>

              <div class="gui-fields-list">
                <!-- Field 1 -->
                <div class="gui-field-row">
                  <div class="f-info">
                    <span class="f-name">Provider ID</span>
                    <span class="f-tip">保持默认标识</span>
                  </div>
                  <div class="f-value-box">
                    <code class="field-code">{{ myTokenDetail ? myTokenDetail.provider_id : 'new-api-1' }}</code>
                    <button
                      type="button"
                      class="f-copy-btn md-state-layer"
                      :class="{ copied: copiedField === 'f_pid' }"
                      @click="copyText(myTokenDetail ? myTokenDetail.provider_id : 'new-api-1', 'f_pid')"
                    >
                      <Check v-if="copiedField === 'f_pid'" :size="13" />
                      <Copy v-else :size="13" />
                      <span>{{ copiedField === 'f_pid' ? '已复制' : '复制' }}</span>
                    </button>
                  </div>
                </div>

                <!-- Field 2 -->
                <div class="gui-field-row">
                  <div class="f-info">
                    <span class="f-name">显示名称 (Display Name)</span>
                    <span class="f-tip">客户端模型选择下拉框中的分组名</span>
                  </div>
                  <div class="f-value-box">
                    <code class="field-code">{{ myTokenDetail ? myTokenDetail.provider_name : '行内大模型平台' }}</code>
                    <button
                      type="button"
                      class="f-copy-btn md-state-layer"
                      :class="{ copied: copiedField === 'f_pname' }"
                      @click="copyText(myTokenDetail ? myTokenDetail.provider_name : '行内大模型平台', 'f_pname')"
                    >
                      <Check v-if="copiedField === 'f_pname'" :size="13" />
                      <Copy v-else :size="13" />
                      <span>{{ copiedField === 'f_pname' ? '已复制' : '复制' }}</span>
                    </button>
                  </div>
                </div>

                <!-- Field 3 -->
                <div class="gui-field-row">
                  <div class="f-info">
                    <span class="f-name">API 地址 (Base URL)</span>
                    <span class="f-tip">内网聚合网关统一端口与版本端点</span>
                  </div>
                  <div class="f-value-box">
                    <code class="field-code">{{ myTokenDetail ? myTokenDetail.base_url : 'http://30.20.4.144:3001/v1' }}</code>
                    <button
                      type="button"
                      class="f-copy-btn md-state-layer"
                      :class="{ copied: copiedField === 'f_url' }"
                      @click="copyText(myTokenDetail ? myTokenDetail.base_url : 'http://30.20.4.144:3001/v1', 'f_url')"
                    >
                      <Check v-if="copiedField === 'f_url'" :size="13" />
                      <Copy v-else :size="13" />
                      <span>{{ copiedField === 'f_url' ? '已复制' : '复制' }}</span>
                    </button>
                  </div>
                </div>

                <!-- Field 4 -->
                <div class="gui-field-row">
                  <div class="f-info">
                    <span class="f-name">API 协议 (Protocol)</span>
                    <span class="f-tip">在下拉列表选择 OpenAI Chat Completions</span>
                  </div>
                  <div class="f-value-box">
                    <code class="field-code">OpenAI Chat Completions</code>
                    <button
                      type="button"
                      class="f-copy-btn md-state-layer"
                      :class="{ copied: copiedField === 'f_proto' }"
                      @click="copyText('OpenAI Chat Completions', 'f_proto')"
                    >
                      <Check v-if="copiedField === 'f_proto'" :size="13" />
                      <Copy v-else :size="13" />
                      <span>{{ copiedField === 'f_proto' ? '已复制' : '复制' }}</span>
                    </button>
                  </div>
                </div>

                <!-- Field 5: API Key -->
                <div class="gui-field-row highlight-row">
                  <div class="f-info">
                    <span class="f-name">API 密钥 (API Key)</span>
                    <span class="f-tip">您的工号专属凭证 (请妥善保管)</span>
                  </div>
                  <div class="f-value-box">
                    <code class="field-code">
                      {{
                        myTokenDetail
                          ? myTokenDetail.status === 'pending_claim' || !myTokenDetail.api_key
                            ? 'Key 暂未申领成功，请点击重新申领'
                            : showPlainKey
                              ? myTokenDetail.api_key
                              : (myTokenDetail.masked_key || 'sk-••••••••')
                          : '请先登录工号获取专属 Key'
                      }}
                    </code>
                    <template v-if="myTokenDetail">
                      <button
                        v-if="myTokenDetail.status === 'pending_claim' || !myTokenDetail.api_key"
                        type="button"
                        class="f-copy-btn primary md-state-layer"
                        :disabled="isClaiming"
                        @click="handleClaimKey"
                      >
                        <RotateCcw :size="13" :class="{ 'spin-icon': isClaiming }" />
                        <span>{{ isClaiming ? '申领中...' : '重新申领' }}</span>
                      </button>
                      <template v-else>
                        <button
                          type="button"
                          class="toggle-eye-btn"
                          title="显示/隐藏明文"
                          @click="showPlainKey = !showPlainKey"
                        >
                          <EyeOff v-if="showPlainKey" :size="14" />
                          <Eye v-else :size="14" />
                        </button>
                        <button
                          type="button"
                          class="f-copy-btn primary md-state-layer"
                          :class="{ copied: copiedField === 'f_key' }"
                          @click="copyText(myTokenDetail.api_key, 'f_key')"
                        >
                          <Check v-if="copiedField === 'f_key'" :size="13" />
                          <Copy v-else :size="13" />
                          <span>{{ copiedField === 'f_key' ? '已复制' : '复制专属 Key' }}</span>
                        </button>
                      </template>
                    </template>
                    <button
                      v-else
                      type="button"
                      class="f-copy-btn primary md-state-layer"
                      @click="showLoginModal = true"
                    >
                      <span>工号登录获取 Key</span>
                    </button>
                  </div>
                </div>
              </div>

              <div class="model-refresh-hint">
                <Info :size="16" />
                <span>
                  <strong>温馨提示：</strong> 配置保存后，在客户端「编辑 → 刷新模型目录」即可直接拉取全量模型。后续后台新增模型时，只需再次点击刷新即可生效，无需重新配置！
                </span>
              </div>
            </div>

            <!-- Tab 2: Patch 覆盖配置 -->
            <div v-else class="tab-pane">
              <p class="tab-instruction">
                通过预置好的 <code>cordis.patch.yml</code>，系统已自动帮您<strong>关闭内网遥测打点</strong>，并预置全量模型映射表：
              </p>

              <div class="patch-steps-guide">
                <div class="p-step-row">
                  <span class="p-num-badge">1</span>
                  <div class="p-desc-content">
                    <strong>点击下载补丁文件：</strong>
                    <div style="margin-top: 8px">
                      <a :href="api.getCordisPatchUrl()" class="patch-dl-btn md-state-layer">
                        <Download :size="15" />
                        <span>下载最新 cordis.patch.yml (包含最新模型目录)</span>
                      </a>
                    </div>
                  </div>
                </div>

                <div class="p-step-row">
                  <span class="p-num-badge">2</span>
                  <div class="p-desc-content">
                    <strong>覆盖客户端配置文件：</strong>
                    点击 DeepSeek Harness 客户端右上角「打开配置文件」，将下载的 <code>cordis.patch.yml</code> 粘贴覆盖至该目录。
                  </div>
                </div>

                <div class="p-step-row">
                  <span class="p-num-badge">3</span>
                  <div class="p-desc-content">
                    <strong>重启客户端填入 Key：</strong>
                    重启客户端，进入「设置 → 模型」，填入您在第 2 步获取的专属 API Key 即可全功能畅享。
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 弹窗 -->
    <LoginModal v-model="showLoginModal" @success="handleVerifySuccess" />
  </div>
</template>

<style scoped>
.home-guide-view {
  display: flex;
  flex-direction: column;
  gap: 36px;
}

/* 顶部状态与模型能力展示 */
.models-overview-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.status-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.gateway-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--sys-status-success-bg, #E6F4EA);
  color: var(--sys-status-success-text, #137333);
  font-size: 13px;
  font-weight: 600;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--sys-status-success-text, #137333);
}

.status-desc-text {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 18px;
}

.model-elevated-card {
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.model-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.model-name-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  line-height: 1.3;
}

.main-rec-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: #1F1F1F;
  color: #FFFFFF;
  white-space: nowrap;
}

:root[data-theme="dark"] .main-rec-badge {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.model-desc-text {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.45;
  flex: 1;
}

.model-tags-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.m-tag-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface-variant);
}

/* Stepper 引导区 */
.stepper-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-title-box {
  margin-bottom: 4px;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 6px;
}

.section-desc {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
}

.stepper-timeline {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-card {
  display: flex;
  gap: 20px;
  padding: 24px;
}

.step-badge-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 36px;
}

.step-num-badge {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

:root[data-theme="dark"] .step-num-badge {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.step-connector-line {
  flex: 1;
  width: 0;
  border-left: 2px dashed rgba(0, 0, 0, 0.08);
  margin-top: 8px;
  min-height: 24px;
}

:root[data-theme="dark"] .step-connector-line {
  border-left-color: rgba(255, 255, 255, 0.12);
}

.step-card-content {
  flex: 1;
  min-width: 0;
}

.step-card-header {
  margin-bottom: 6px;
}

.step-heading {
  font-size: 16px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  display: inline-block;
  margin-right: 12px;
}

.step-sub {
  font-size: 13px;
  color: var(--md-sys-color-outline);
}

.step-text {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
  margin-bottom: 16px;
  line-height: 1.5;
}

/* Step 1 安装包条带 (无多余外边框) */
.installer-strip {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: var(--md-sys-shape-corner-medium);
  flex-wrap: wrap;
}

.inst-icon-base {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  display: flex;
  align-items: center;
  justify-content: center;
}

.inst-meta {
  flex: 1;
  min-width: 200px;
}

.inst-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 2px;
}

.inst-details {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

.inst-dl-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: opacity 0.2s;
}

.inst-dl-btn:hover {
  opacity: 0.9;
}

:root[data-theme="dark"] .inst-dl-btn {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

/* Step 2 工号条带 */
.logged-key-strip {
  padding: 16px 20px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: var(--md-sys-shape-corner-medium);
}

.key-strip-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.key-user-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.key-strip-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: var(--md-sys-color-surface-container-lowest);
  padding: 10px 14px;
  border-radius: var(--md-sys-shape-corner-small);
  gap: 12px;
}

.key-code-block {
  font-family: "Cascadia Mono", "Consolas", monospace;
  font-size: 13px;
  color: var(--md-sys-color-on-surface);
  word-break: break-all;
}

.copy-pill-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.copy-pill-btn.copied {
  background-color: var(--sys-status-success-bg, #E6F4EA);
  color: var(--sys-status-success-text, #137333);
}

.verify-trigger-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: var(--md-sys-shape-corner-medium);
  flex-wrap: wrap;
  gap: 12px;
}

.trigger-intro {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.trigger-action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

:root[data-theme="dark"] .trigger-action-btn {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

/* Step 3 Tabs & Items */
.config-tabs-nav {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  padding-bottom: 12px;
}

.config-tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-primary-container);
  cursor: pointer;
  transition: all 0.2s;
}

.config-tab-btn.active {
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-weight: 600;
}

:root[data-theme="dark"] .config-tab-btn.active {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.tab-instruction {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
  margin-bottom: 16px;
  line-height: 1.5;
}

.tab-instruction code {
  background-color: var(--md-sys-color-primary-container);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: "Cascadia Mono", monospace;
  font-size: 13px;
}

.gui-fields-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.gui-field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: var(--md-sys-shape-corner-medium);
  gap: 16px;
  flex-wrap: wrap;
}

.gui-field-row.highlight-row {
  background-color: color-mix(in srgb, var(--md-sys-color-primary-container) 70%, var(--md-sys-color-surface-container-highest));
}

.f-info {
  display: flex;
  flex-direction: column;
}

.f-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.f-tip {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

.f-value-box {
  display: flex;
  align-items: center;
  gap: 12px;
}

.field-code {
  font-family: "Cascadia Mono", "Consolas", monospace;
  font-size: 13px;
  padding: 6px 10px;
  background-color: var(--md-sys-color-surface-container-lowest);
  border-radius: 6px;
  color: var(--md-sys-color-on-surface);
}

.f-copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.f-copy-btn.copied {
  background-color: var(--sys-status-success-bg, #E6F4EA);
  color: var(--sys-status-success-text, #137333);
}

.f-copy-btn.primary {
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-weight: 600;
}

:root[data-theme="dark"] .f-copy-btn.primary {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.model-refresh-hint {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 18px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: var(--md-sys-shape-corner-small);
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.5;
}

/* Patch Tab */
.patch-steps-guide {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.p-step-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 18px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: var(--md-sys-shape-corner-medium);
}

.p-num-badge {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-weight: 700;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

:root[data-theme="dark"] .p-num-badge {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.p-desc-content {
  font-size: 13px;
  color: var(--md-sys-color-on-surface);
  line-height: 1.5;
}

.patch-dl-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}

:root[data-theme="dark"] .patch-dl-btn {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.toggle-eye-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface-variant);
  border: 1px solid var(--md-sys-color-outline-variant, #E0E2E6);
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-eye-btn:hover {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface);
}

.pending-tip-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #D97706;
  font-weight: 500;
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
