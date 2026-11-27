<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Activity,
  CheckCircle2,
  Layers,
  PlayCircle,
  Plus,
  RefreshCw,
  Server,
  Upload,
  Wrench,
} from 'lucide-vue-next'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import { useToast } from '@/composables/useToast'
import {
  getAuditLogs,
  getDashboardSummary,
  getMcpErrorMessage,
  getServices,
  isMcpEngineUnavailable,
  listTools,
} from '@/api/mcp'
import type { AuditLog, DashboardSummary, McpService, RegisteredTool } from '@/types/mcp'

export type McpAdminTabKey =
  | 'dashboard'
  | 'servers'
  | 'tools'
  | 'debug'
  | 'permissions'
  | 'audit'
  | 'system'

const emit = defineEmits<{
  (e: 'navigate', payload: { tab: McpAdminTabKey; action?: string; serviceId?: string }): void
  (e: 'engine-error', message: string): void
}>()

const toast = useToast()
const loading = ref(true)
const summary = ref<DashboardSummary | null>(null)
const services = ref<McpService[]>([])
const tools = ref<RegisteredTool[]>([])
const recentLogs = ref<AuditLog[]>([])

let abortController: AbortController | null = null

const toolCountMap = computed(() => {
  const map = new Map<string, number>()
  for (const t of tools.value) {
    map.set(t.service_id, (map.get(t.service_id) ?? 0) + 1)
  }
  return map
})

const successRate = computed(() => {
  if (!summary.value || summary.value.calls_total === 0) return '100%'
  return `${Math.round((summary.value.calls_success / summary.value.calls_total) * 100)}%`
})

const dailyBuckets = computed(() => {
  if (summary.value?.daily_trends?.length) {
    return summary.value.daily_trends.map((item) => ({
      date: item.date,
      label: `${item.date.slice(5, 7)}/${item.date.slice(8, 10)}`,
      total: item.calls,
      success: item.success_calls,
    }))
  }

  const days: Array<{ date: string; label: string; total: number; success: number }> = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(now.getDate() - i)
    const iso = d.toISOString().slice(0, 10)
    days.push({
      date: iso,
      label: `${iso.slice(5, 7)}/${iso.slice(8, 10)}`,
      total: 0,
      success: 0,
    })
  }
  const byDate = new Map(days.map((item) => [item.date, item]))
  for (const log of recentLogs.value) {
    const dayKey = (log.timestamp || '').slice(0, 10)
    const bucket = byDate.get(dayKey)
    if (bucket) {
      bucket.total += 1
      if (log.result_status.toLowerCase() === 'success') bucket.success += 1
    }
  }
  return days
})

const maxDailyCalls = computed(() =>
  Math.max(...dailyBuckets.value.map((d) => d.total), 1)
)

async function loadData() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  const { signal } = abortController

  loading.value = true
  try {
    const [sumRes, svcRes, toolRes, auditRes] = await Promise.all([
      getDashboardSummary(signal),
      getServices(undefined, signal),
      listTools(undefined, signal).catch(() => []),
      getAuditLogs({ limit: 100, offset: 0 }, signal).catch(() => ({
        items: [],
        total: 0,
      })),
    ])
    summary.value = sumRes
    services.value = svcRes
    tools.value = toolRes
    recentLogs.value = auditRes.items || []
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = getMcpErrorMessage(err, '获取总览指标失败')
    if (isMcpEngineUnavailable(err)) {
      emit('engine-error', msg)
    } else {
      toast.error(msg)
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadData()
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="mcp-dashboard">
    <div class="tab-toolbar">
      <div>
        <h2 class="tab-title">MCP 运行总览</h2>
        <p class="tab-subtitle">实时聚合下游业务服务健康状态、工具授权规模与调用审计趋势</p>
      </div>
      <div class="toolbar-btns">
        <MdButton variant="tonal" :disabled="loading" @click="loadData">
          <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
          <span>刷新指标</span>
        </MdButton>
        <MdButton variant="filled" @click="emit('navigate', { tab: 'servers', action: 'register' })">
          <Plus :size="15" />
          <span>注册 MCP 服务</span>
        </MdButton>
      </div>
    </div>

    <!-- KPI 卡片行 -->
    <div class="kpi-grid">
      <MdCard variant="elevated">
        <div class="kpi-card-body">
          <div class="kpi-icon tone-primary">
            <Server :size="20" />
          </div>
          <div>
            <div class="kpi-value">{{ loading ? '—' : summary?.servers_total ?? 0 }}</div>
            <div class="kpi-label">
              已注册服务（在线 {{ summary?.servers_active ?? 0 }}）
            </div>
          </div>
        </div>
      </MdCard>

      <MdCard variant="elevated">
        <div class="kpi-card-body">
          <div class="kpi-icon tone-secondary">
            <Wrench :size="20" />
          </div>
          <div>
            <div class="kpi-value">{{ loading ? '—' : summary?.tools_total ?? 0 }}</div>
            <div class="kpi-label">
              托管工具契约（健康率 {{ summary?.health_rate ?? 100 }}%）
            </div>
          </div>
        </div>
      </MdCard>

      <MdCard variant="elevated">
        <div class="kpi-card-body">
          <div class="kpi-icon tone-success">
            <Activity :size="20" />
          </div>
          <div>
            <div class="kpi-value">{{ loading ? '—' : summary?.calls_total ?? 0 }}</div>
            <div class="kpi-label">
              累计调用（成功 {{ summary?.calls_success ?? 0 }} / 失败 {{ summary?.calls_failed ?? 0 }}）
            </div>
          </div>
        </div>
      </MdCard>

      <MdCard variant="elevated">
        <div class="kpi-card-body">
          <div class="kpi-icon tone-primary">
            <CheckCircle2 :size="20" />
          </div>
          <div>
            <div class="kpi-value">{{ loading ? '—' : successRate }}</div>
            <div class="kpi-label">调用总体成功率</div>
          </div>
        </div>
      </MdCard>
    </div>

    <!-- 近 7 日趋势 + 快捷入口 -->
    <div class="dashboard-split">
      <MdCard variant="elevated">
        <div class="panel-header">
          <div>
            <h3>近 7 日工具调用趋势</h3>
            <p class="panel-sub">基于最近 100 条审计记录统计每日调用分布</p>
          </div>
        </div>
        <div class="trend-bars-wrap">
          <div v-for="bucket in dailyBuckets" :key="bucket.date" class="trend-bar-item">
            <span class="bar-count">{{ bucket.total }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{ height: `${Math.max(Math.round((bucket.total / maxDailyCalls) * 100), bucket.total ? 12 : 4)}%` }"
              ></div>
            </div>
            <span class="bar-date">{{ bucket.label }}</span>
          </div>
        </div>
      </MdCard>

      <MdCard variant="elevated">
        <div class="panel-header">
          <div>
            <h3>高频治理操作</h3>
            <p class="panel-sub">直达能力上架、插件发布、在线调试与风险策略配置</p>
          </div>
        </div>
        <div class="quick-actions-grid">
          <button
            type="button"
            class="quick-action-tile"
            @click="emit('navigate', { tab: 'servers', action: 'register' })"
          >
            <Plus :size="18" />
            <div>
              <strong>注册远程服务</strong>
              <span>录入 Streamable HTTP / SSE</span>
            </div>
          </button>
          <button
            type="button"
            class="quick-action-tile"
            @click="emit('navigate', { tab: 'servers', action: 'publish' })"
          >
            <Upload :size="18" />
            <div>
              <strong>上传 ZIP 插件</strong>
              <span>一键安装并托管本地 MCP</span>
            </div>
          </button>
          <button type="button" class="quick-action-tile" @click="emit('navigate', { tab: 'debug' })">
            <PlayCircle :size="18" />
            <div>
              <strong>在线调试台</strong>
              <span>动态参数表单受控试跑</span>
            </div>
          </button>
          <button type="button" class="quick-action-tile" @click="emit('navigate', { tab: 'tools' })">
            <Layers :size="18" />
            <div>
              <strong>工具风险治理</strong>
              <span>调整 L0-L3 分级与二次确认</span>
            </div>
          </button>
        </div>
      </MdCard>
    </div>

    <!-- 服务健康快照 -->
    <MdCard variant="elevated">
      <div class="panel-header">
        <div>
          <h3>下游 MCP 服务健康列表</h3>
          <p class="panel-sub">点击任意服务进入详情管理或工具刷新</p>
        </div>
        <MdButton variant="text" @click="emit('navigate', { tab: 'servers' })">管理全部服务</MdButton>
      </div>
      <div v-if="!services.length && !loading" class="empty-inline">暂无已注册 MCP 服务</div>
      <div v-else class="service-rows">
        <div
          v-for="svc in services.slice(0, 8)"
          :key="svc.id"
          class="service-row-item"
          @click="emit('navigate', { tab: 'servers', serviceId: svc.id })"
        >
          <div class="svc-left">
            <strong>{{ svc.name }}</strong>
            <span class="mono svc-id">{{ svc.id }}</span>
          </div>
          <div class="svc-meta">
            <span>Streamable HTTP · {{ svc.tools_count ?? toolCountMap.get(svc.id) ?? 0 }} 个工具</span>
            <span class="status-pill" :class="`st-${svc.status}`">{{ svc.status }}</span>
          </div>
        </div>
      </div>
    </MdCard>
  </div>
</template>

<style scoped>
.mcp-dashboard {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.tab-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--md-sys-color-on-surface);
}

.tab-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.toolbar-btns {
  display: flex;
  gap: 10px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

@media (max-width: 1080px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.kpi-card-body {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kpi-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--md-sys-shape-corner-medium);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.tone-primary {
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-primary-container);
}

.tone-secondary {
  background-color: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
}

.tone-success {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.kpi-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--md-sys-color-on-surface);
}

.kpi-label {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.dashboard-split {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 16px;
}

@media (max-width: 960px) {
  .dashboard-split {
    grid-template-columns: 1fr;
  }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.panel-sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.trend-bars-wrap {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 150px;
  padding-top: 12px;
}

.trend-bar-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
}

.bar-count {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.bar-track {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.bar-fill {
  width: 100%;
  max-width: 28px;
  border-radius: 6px 6px 2px 2px;
  background-color: var(--md-sys-color-primary);
}

.bar-date {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.quick-actions-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.quick-action-tile {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: var(--md-sys-shape-corner-medium);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  text-align: left;
  cursor: pointer;
  transition: background-color 0.2s;
}

.quick-action-tile:hover {
  background-color: var(--md-sys-color-surface-container);
}

.quick-action-tile strong {
  display: block;
  font-size: 13px;
}

.quick-action-tile span {
  display: block;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  margin-top: 2px;
}

.service-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.service-row-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
  cursor: pointer;
}

.service-row-item:hover {
  background-color: var(--md-sys-color-surface-container);
}

.svc-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.svc-id {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.svc-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.status-pill {
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
}

.status-pill.st-active {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.status-pill.st-degraded {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.status-pill.st-inactive,
.status-pill.st-pending {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface-variant);
}

.empty-inline {
  padding: 20px;
  text-align: center;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.is-spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
