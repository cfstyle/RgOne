<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Users,
  KeyRound,
  RefreshCw,
  Server,
  Zap,
  ShieldCheck,
  ChevronRight,
  Database,
  AlertCircle,
  Clock,
  Layers,
} from 'lucide-vue-next'
import { api } from '@/api'
import UsageRankingPanel from './UsageRankingPanel.vue'

export interface DepartmentRankingItem {
  department: string
  total_tokens: number
  request_count: number
  active_employees: number
}

export interface AdminOverviewData {
  total_employees?: number
  claimed_tokens?: number
  disabled_tokens?: number
  claim_rate?: number
  total_tokens?: number
  admin_user?: string
  department_ranking?: DepartmentRankingItem[]
  last_sync_status?: string
  last_sync_time?: string
  last_sync_message?: string
}

export interface GatewayStatusData {
  gateway_connected?: boolean
  is_mock?: boolean
  message?: string
}

const router = useRouter()

const overview = ref<AdminOverviewData>({})
const gatewayStatus = ref<GatewayStatusData>({})
const loading = ref(false)
const testingGw = ref(false)
const syncingLogs = ref(false)
const actionMsg = ref('')
const actionError = ref(false)
const rankingRevision = ref(0)

async function loadData() {
  loading.value = true
  try {
    const [ovRes, gwRes] = await Promise.all([
      api.getAdminOverview() as Promise<{ data?: AdminOverviewData }>,
      api.getGatewayStatus() as Promise<GatewayStatusData>,
    ])
    overview.value = (ovRes.data as AdminOverviewData) || {}
    gatewayStatus.value = (gwRes as GatewayStatusData) || {}
  } catch (e) {
    console.error('加载总览指标失败', e)
  } finally {
    loading.value = false
  }
}

async function handleTestGateway() {
  testingGw.value = true
  actionMsg.value = ''
  actionError.value = false
  try {
    const res = await api.testGateway() as { success?: boolean; message?: string }
    actionError.value = res.success !== true
    actionMsg.value = res.message || (actionError.value ? '网关连通性测试失败' : '网关连通性验证通过')
    await loadData()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '网关测试异常'
    actionMsg.value = `测试失败: ${msg}`
    actionError.value = true
  } finally {
    testingGw.value = false
  }
}

async function handleSyncLogs() {
  syncingLogs.value = true
  actionMsg.value = ''
  actionError.value = false
  try {
    const res = await api.adminSyncLogs() as { message?: string; added_count?: number }
    actionMsg.value = res.message || `同步成功，新增 ${res.added_count || 0} 条日志`
    actionError.value = false
    rankingRevision.value += 1
    await loadData()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '未知网关错误'
    actionMsg.value = `网关同步失败: ${msg}`
    actionError.value = true
  } finally {
    syncingLogs.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="admin-dashboard-view">
    <div class="page-title-box">
      <h2 class="page-title">全行大模型接入与运营总览</h2>
      <p class="page-desc">实时监控全行员工 API Key 申领覆盖率、网关服务健康度与日志增量同步状态</p>
    </div>

    <!-- 顶部核心数据 4 张 KPI 卡片（1:1 复刻模板骨架） -->
    <div class="kpi-grid">
      <!-- KPI 1 -->
      <div class="kpi-elevated-card studio-elevated-card">
        <div class="kpi-card-top">
          <div class="kpi-icon-base">
            <Users :size="20" />
          </div>
          <span class="status-pill neutral">行内白名单</span>
        </div>
        <div class="kpi-card-bottom">
          <span class="kpi-label">全行员工总数</span>
          <div class="kpi-number-row">
            <span class="kpi-number tabular-nums">{{ overview.total_employees || 0 }}</span>
            <span class="kpi-unit">人</span>
          </div>
        </div>
      </div>

      <!-- KPI 2 -->
      <div class="kpi-elevated-card studio-elevated-card">
        <div class="kpi-card-top">
          <div class="kpi-icon-base">
            <KeyRound :size="20" />
          </div>
          <span class="status-pill success">覆盖率 {{ overview.claim_rate || 0 }}%</span>
        </div>
        <div class="kpi-card-bottom">
          <span class="kpi-label">已申领专属 API Key</span>
          <div class="kpi-number-row">
            <span class="kpi-number tabular-nums">{{ overview.claimed_tokens || 0 }}</span>
            <span class="kpi-unit">人</span>
          </div>
        </div>
      </div>

      <!-- KPI 3 -->
      <div class="kpi-elevated-card studio-elevated-card">
        <div class="kpi-card-top">
          <div class="kpi-icon-base">
            <Zap :size="20" />
          </div>
          <span class="status-pill warning">{{ overview.disabled_tokens || 0 }} 个已冻结</span>
        </div>
        <div class="kpi-card-bottom">
          <span class="kpi-label">全行消耗总 Token</span>
          <div class="kpi-number-row">
            <span class="kpi-number tabular-nums">{{ (overview.total_tokens || 0).toLocaleString() }}</span>
          </div>
        </div>
      </div>

      <!-- KPI 4 -->
      <div class="kpi-elevated-card studio-elevated-card">
        <div class="kpi-card-top">
          <div class="kpi-icon-base">
            <Server :size="20" />
          </div>
          <span
            class="status-pill"
            :class="gatewayStatus.gateway_connected ? 'success' : 'danger'"
          >
            {{ gatewayStatus.gateway_connected ? (gatewayStatus.is_mock ? 'Mock 仿真中' : '生产直连') : '服务不可达' }}
          </span>
        </div>
        <div class="kpi-card-bottom">
          <span class="kpi-label">算力网关服务状态</span>
          <div class="kpi-number-row">
            <span class="kpi-number text-status">
              {{ gatewayStatus.gateway_connected ? '稳定运行' : '连接异常' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <UsageRankingPanel :revision="rankingRevision" />

    <!-- 下半屏内容：单层纯白 Elevated 卡片列表（重塑框套框与空白） -->
    <div class="operations-elevated-card studio-elevated-card">
      <div class="ops-card-header">
        <div class="ops-header-text">
          <h3 class="ops-title">算力网关控制与核心业务流</h3>
          <p class="ops-sub">快速触发全行日志增量拉取、健康探测及各模块运维快速入口</p>
        </div>
        <div class="ops-header-actions">
          <button
            type="button"
            class="ops-action-btn md-state-layer"
            :disabled="testingGw"
            @click="handleTestGateway"
          >
            <RefreshCw :size="14" :class="{ rotating: testingGw }" />
            <span>{{ testingGw ? '正在探测...' : '测试网关连通性' }}</span>
          </button>
          <button
            type="button"
            class="ops-action-btn primary md-state-layer"
            :disabled="syncingLogs"
            @click="handleSyncLogs"
          >
            <Database :size="14" :class="{ rotating: syncingLogs }" />
            <span>{{ syncingLogs ? '同步中...' : '手动拉取日志' }}</span>
          </button>
        </div>
      </div>

      <!-- 操作反馈提示条（柔和语义色） -->
      <div v-if="actionMsg" class="action-feedback-strip" :class="{ error: actionError }">
        <component :is="actionError ? AlertCircle : ShieldCheck" :size="15" />
        <span>{{ actionMsg }}</span>
      </div>

      <!-- 网关增量同步元数据状态条 -->
      <div class="sync-meta-bar">
        <div class="sync-meta-item">
          <Clock :size="14" />
          <span>最近同步时间: <strong>{{ overview.last_sync_time || '-' }}</strong></span>
        </div>
        <div class="sync-meta-item">
          <span>状态: </span>
          <span
            class="status-pill"
            :class="overview.last_sync_status === 'success' ? 'success' : overview.last_sync_status === 'failed' ? 'danger' : 'neutral'"
          >
            {{ overview.last_sync_status === 'success' ? '同步成功' : overview.last_sync_status === 'failed' ? '同步异常' : '未同步' }}
          </span>
        </div>
        <div class="sync-meta-item sync-msg-text">
          <span>{{ overview.last_sync_message || '系统准备就绪' }}</span>
        </div>
      </div>

      <!-- 全行部门用量排行表 -->
      <div class="dept-ranking-box" v-if="overview.department_ranking?.length">
        <div class="dept-ranking-header">
          <Layers :size="16" />
          <span class="dept-ranking-title">全行部门用量排行与活跃统计</span>
        </div>
        <div class="dept-table-wrap">
          <table class="dept-table">
            <thead>
              <tr>
                <th>部门名称</th>
                <th>消耗总 Token</th>
                <th>调用频次</th>
                <th>活跃员工</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in overview.department_ranking" :key="item.department">
                <td><strong>{{ item.department }}</strong></td>
                <td class="tabular-nums">{{ item.total_tokens.toLocaleString() }}</td>
                <td class="tabular-nums">{{ item.request_count.toLocaleString() }} 次</td>
                <td class="tabular-nums">{{ item.active_employees }} 人</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 单层无边框清爽列表行 -->
      <div class="ops-items-list">
        <!-- Item 1 -->
        <div class="ops-row-item" @click="router.push('/admin/employees')">
          <div class="ops-row-icon">
            <Users :size="18" />
          </div>
          <div class="ops-row-content">
            <div class="ops-row-title-line">
              <span class="row-main-title">员工白名单同步与批量导入</span>
              <span class="status-pill neutral">名单底表</span>
            </div>
            <p class="row-sub-text">支持 Excel (.xlsx) / CSV 批量导入、导出模板及增量覆盖，保障工号精准核验</p>
          </div>
          <div class="ops-row-arrow">
            <ChevronRight :size="18" />
          </div>
        </div>

        <!-- Item 2 -->
        <div class="ops-row-item" @click="router.push('/admin/tokens')">
          <div class="ops-row-icon">
            <KeyRound :size="18" />
          </div>
          <div class="ops-row-content">
            <div class="ops-row-title-line">
              <span class="row-main-title">全行 API Key 凭证与启停运维</span>
              <span class="status-pill success">凭证管控</span>
            </div>
            <p class="row-sub-text">实时检索各工号已签发的 Token 状态，支持一键封禁、启用与对称加密密钥强制重置</p>
          </div>
          <div class="ops-row-arrow">
            <ChevronRight :size="18" />
          </div>
        </div>

        <!-- Item 3 -->
        <div class="ops-row-item" @click="router.push('/admin/files')">
          <div class="ops-row-icon">
            <Zap :size="18" />
          </div>
          <div class="ops-row-content">
            <div class="ops-row-title-line">
              <span class="row-main-title">客户端安装程序与资料分发</span>
              <span class="status-pill neutral">下载中心</span>
            </div>
            <p class="row-sub-text">流式分块托管 DeepSeek Harness 客户端安装包，维护 SHA256 校验和与首页主推版本</p>
          </div>
          <div class="ops-row-arrow">
            <ChevronRight :size="18" />
          </div>
        </div>

        <!-- Item 4 -->
        <div class="ops-row-item" @click="router.push('/admin/settings')">
          <div class="ops-row-icon">
            <Server :size="18" />
          </div>
          <div class="ops-row-content">
            <div class="ops-row-title-line">
              <span class="row-main-title">系统网络与聚合网关参数配置</span>
              <span class="status-pill neutral">网关配置</span>
            </div>
            <p class="row-sub-text">配置 new-api Base URL (http://30.20.4.144:3001)、系统访问令牌与默认 Agent 模型</p>
          </div>
          <div class="ops-row-arrow">
            <ChevronRight :size="18" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-dashboard-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 4px;
}

.page-desc {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
}

/* 4 张 KPI 卡片 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 18px;
}

.kpi-elevated-card {
  padding: 22px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 20px;
}

.kpi-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.kpi-icon-base {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  display: flex;
  align-items: center;
  justify-content: center;
}

.kpi-card-bottom {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi-label {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.kpi-number-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.kpi-number {
  font-size: 30px;
  font-weight: 700;
  color: #1F1F1F;
  line-height: 1.1;
  font-family: "Plus Jakarta Sans", sans-serif;
}

:root[data-theme="dark"] .kpi-number {
  color: #FFFFFF;
}

.kpi-number.text-status {
  font-size: 22px;
  font-weight: 600;
}

.kpi-unit {
  font-size: 13px;
  color: var(--md-sys-color-outline);
}

/* 业务动态与控制单层 Elevated 卡片 */
.operations-elevated-card {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.ops-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.ops-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 4px;
}

.ops-sub {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.ops-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ops-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.ops-action-btn.primary {
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-weight: 600;
}

:root[data-theme="dark"] .ops-action-btn.primary {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.action-feedback-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: var(--md-sys-shape-corner-medium);
  background-color: var(--sys-status-success-bg, #E6F4EA);
  color: var(--sys-status-success-text, #137333);
  font-size: 13px;
  font-weight: 500;
}

.action-feedback-strip.error {
  background-color: #FEE2E2;
  color: #B91C1C;
}

.sync-meta-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px 18px;
  background-color: var(--md-sys-color-surface);
  border-radius: 12px;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.sync-meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sync-msg-text {
  color: var(--md-sys-color-outline);
}

.dept-ranking-box {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dept-ranking-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.dept-table-wrap {
  overflow-x: auto;
}

.dept-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.dept-table th {
  text-align: left;
  padding: 10px 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface-variant);
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.dept-table td {
  padding: 12px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  color: var(--md-sys-color-on-surface);
}

.dept-table tr:hover td {
  background-color: var(--md-sys-color-primary-container);
}

/* 列表行排版 */
.ops-items-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ops-row-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.ops-row-item:hover {
  background-color: var(--md-sys-color-primary-container);
}

.ops-row-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.ops-row-item:hover .ops-row-icon {
  background-color: var(--md-sys-color-surface-container-lowest);
}

.ops-row-content {
  flex: 1;
  min-width: 0;
}

.ops-row-title-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 3px;
}

.row-main-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.row-sub-text {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

.ops-row-arrow {
  color: var(--md-sys-color-outline);
  display: flex;
  align-items: center;
  transition: transform 0.2s;
}

.ops-row-item:hover .ops-row-arrow {
  transform: translateX(3px);
  color: var(--md-sys-color-on-surface);
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
