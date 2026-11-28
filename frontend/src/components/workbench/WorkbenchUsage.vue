<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  Eye,
  EyeOff,
  Copy,
  Check,
  RefreshCw,
  RotateCcw,
  Zap,
  Clock,
  Cpu,
  Layers,
  UserCheck,
} from 'lucide-vue-next'
import type { EChartsType } from 'echarts/core'
import { AdaptiveModal, MdButton, MdCard, MdChartCard, MdSelect, type SelectOption, type MdTableColumn } from '@/components/m3'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { copyToClipboard } from '@/utils/clipboard'
import { useEmployeeToken } from '@/composables/useEmployeeToken'

const props = defineProps<{ embed?: boolean }>()
const showDetails = ref(!props.embed)
const daily = ref<OverviewData>()
const monthly = ref<OverviewData>()
const summaryError = ref(false)
let summaryLoad = 0
let active = true

const authStore = useAuthStore()
const themeStore = useThemeStore()

interface OverviewData {
  total_requests?: number
  total_tokens?: number
  prompt_tokens?: number
  completion_tokens?: number
  avg_latency_ms?: number
  favorite_model?: string
  last_active?: string
  [key: string]: unknown
}

interface TrendData {
  categories: string[]
  series: {
    requests: number[]
    prompt_tokens: number[]
    completion_tokens: number[]
    total_tokens: number[]
  }
}

interface ModelDistItem {
  model_name: string
  requests: number
  total_tokens?: number
}

interface LogItem {
  id?: number
  created_at?: string
  model_name?: string
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  latency_ms?: number
  status_code?: number
  is_stream?: boolean
  [key: string]: unknown
}

const showResetConfirm = ref(false)

// 员工凭证信息
const {
  detail: tokenDetail,
  loading: loadingKey,
  failure: keyFailure,
  claiming: isClaiming,
  resetting: isResetting,
  reload: reloadKey,
  claim: claimKey,
  reset: resetKey,
} = useEmployeeToken()
const showPlainKey = ref(false)
const copiedKey = ref(false)
let copyFeedback: ReturnType<typeof setTimeout> | undefined

// 看板参数
const selectedRange = ref<'today' | '7d' | '30d' | 'all'>('7d')
const overview = ref<OverviewData>({})
const trendData = ref<TrendData>({ categories: [], series: { requests: [], prompt_tokens: [], completion_tokens: [], total_tokens: [] } })
const modelDist = ref<ModelDistItem[]>([])
const trendRows = computed(() => trendData.value.categories.map((time, index) => ({
  time,
  tokens: trendData.value.series.total_tokens[index] ?? 0,
  requests: trendData.value.series.requests[index] ?? 0,
})))
const trendColumns: MdTableColumn<(typeof trendRows.value)[number]>[] = [
  { key: 'time', title: '时间' },
  { key: 'tokens', title: 'Token' },
  { key: 'requests', title: '调用次数' },
]
const modelColumns: MdTableColumn<ModelDistItem>[] = [
  { key: 'model_name', title: '模型' },
  { key: 'requests', title: '调用次数' },
  { key: 'total_tokens', title: 'Token' },
]

// 明细表格
const logsPage = ref(1)
const logsPageSize = ref(10)
const selectedModelFilter = ref('')
const modelFilterOptions = computed<SelectOption[]>(() => [
  { label: '全部模型', value: '' },
  ...modelDist.value.map((m) => ({ label: m.model_name, value: m.model_name })),
])
const logsData = ref<{ total: number; items: LogItem[] }>({ total: 0, items: [] })
const loadingLogs = ref(false)

// 立即同步与数据更新时间
const syncing = ref(false)
const syncCooldown = ref(0)
const syncMsg = ref('')
const analyticsError = ref(false)
const logsError = ref(false)
const lastSyncTime = ref('')
let syncTimer: ReturnType<typeof setInterval> | undefined
let analyticsLoad = 0
let logsLoad = 0

// ECharts 实例引用
const trendChartEl = ref<HTMLDivElement | null>(null)
const modelChartEl = ref<HTMLDivElement | null>(null)
let trendChartInstance: EChartsType | null = null
let modelChartInstance: EChartsType | null = null
const chartError = ref(false)

async function updateCharts() {
  try {
    const { init } = await import('./usageCharts')
    if (active && showDetails.value) {
      initCharts(init)
      chartError.value = false
    }
  } catch {
    if (active) chartError.value = true
  }
}

function initCharts(init: typeof import('echarts/core')['init']) {
  const styles = getComputedStyle(document.documentElement)
  const color = (name: string) => styles.getPropertyValue('--md-sys-color-' + name).trim()
  const axisTextColor = color('on-surface-variant')
  const splitLineColor = color('outline-variant')
  const primaryColor = color('primary')
  const tooltipColor = color('inverse-surface')
  const tooltipText = color('inverse-on-surface')

  // 1. 趋势图
  if (trendChartEl.value) {
    if (!trendChartInstance) {
      trendChartInstance = init(trendChartEl.value)
    }
    const categories = (trendData.value.categories || []).map((c: string) =>
      c.length > 5 ? c.substring(5) : c
    )
    const tokenSeries = trendData.value.series?.total_tokens || []
    const requestSeries = trendData.value.series?.requests || []

    trendChartInstance.setOption({
      tooltip: {
        trigger: 'axis',
        backgroundColor: tooltipColor,
        borderColor: tooltipColor,
        textStyle: { color: tooltipText, fontSize: 12 },
        padding: [8, 12]
      },
      legend: {
        bottom: 0,
        textStyle: { color: axisTextColor, fontSize: 12 }
      },
      grid: {
        top: 30,
        left: 16,
        right: 20,
        bottom: 36,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: categories,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: axisTextColor, fontSize: 12 }
      },
      yAxis: [
        {
          type: 'value',
          name: 'Token',
          nameTextStyle: { color: axisTextColor, fontSize: 11 },
          axisLine: { show: false },
          splitLine: { lineStyle: { type: 'dashed', color: splitLineColor } },
          axisLabel: { color: axisTextColor, fontSize: 11 }
        },
        {
          type: 'value',
          name: '请求数',
          nameTextStyle: { color: axisTextColor, fontSize: 11 },
          axisLine: { show: false },
          splitLine: { show: false },
          axisLabel: { color: axisTextColor, fontSize: 11 }
        }
      ],
      series: [
        {
          name: '消耗 Token',
          type: 'line',
          smooth: true,
          data: tokenSeries,
          itemStyle: { color: primaryColor },
          lineStyle: { width: 2.5, color: primaryColor },
          areaStyle: { opacity: 0.12 }
        },
        {
          name: '请求次数',
          type: 'bar',
          yAxisIndex: 1,
          barWidth: 14,
          data: requestSeries,
          itemStyle: { color: color('secondary'), borderRadius: [4, 4, 0, 0] }
        }
      ]
    })
  }

  // 2. 模型分布图
  if (modelChartEl.value) {
    if (!modelChartInstance) {
      modelChartInstance = init(modelChartEl.value)
    }
    const pieData = (modelDist.value || []).map((m: ModelDistItem) => ({
      value: m.requests,
      name: m.model_name
    }))

    modelChartInstance.setOption({
      color: ['primary', 'secondary', 'tertiary', 'outline', 'inverse-surface'].map(color),
      tooltip: {
        trigger: 'item',
        backgroundColor: tooltipColor,
        borderColor: tooltipColor,
        textStyle: { color: tooltipText, fontSize: 12 },
        padding: [8, 12],
        formatter: '{b}: {c} 次 ({d}%)'
      },
      legend: {
        type: 'scroll',
        bottom: 0,
        textStyle: { color: axisTextColor, fontSize: 12 }
      },
      series: [
        {
          name: '模型调用占比',
          type: 'pie',
          radius: ['45%', '72%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 6,
            borderColor: color('surface-container-lowest'),
            borderWidth: 2
          },
          label: { show: false },
          data: pieData
        }
      ]
    })
  }
}

function handleWindowResize() {
  trendChartInstance?.resize()
  modelChartInstance?.resize()
}

async function loadSummary() {
  const requestId = ++summaryLoad
  summaryError.value = false
  const [today, month] = await Promise.allSettled([
    api.getUsageOverview('today') as Promise<{ data?: OverviewData }>,
    api.getUsageOverview('month') as Promise<{ data?: OverviewData }>,
  ])
  if (requestId !== summaryLoad) return
  daily.value = today.status === 'fulfilled' ? today.value?.data : undefined
  monthly.value = month.status === 'fulfilled' ? month.value?.data : undefined
  summaryError.value = !daily.value || !monthly.value
}

async function loadAnalytics() {
  if (!authStore.isEmployeeLoggedIn || !showDetails.value) return
  const requestId = ++analyticsLoad
  analyticsError.value = false
  try {
    const [ovRes, trRes, mdRes] = await Promise.all([
      api.getUsageOverview(selectedRange.value) as Promise<{ data?: OverviewData }>,
      api.getUsageTrend(selectedRange.value) as Promise<{ data?: TrendData }>,
      api.getUsageModels(selectedRange.value) as Promise<{ data?: ModelDistItem[] }>,
    ])
    if (requestId !== analyticsLoad) return
    if (!ovRes?.data || !Array.isArray(trRes?.data?.categories) ||
      !Array.isArray(trRes.data.series?.total_tokens) || !Array.isArray(trRes.data.series.requests) ||
      !Array.isArray(mdRes?.data)) throw new Error('用量统计数据格式异常')
    overview.value = ovRes.data
    trendData.value = trRes.data
    modelDist.value = mdRes.data
  } catch {
    if (requestId === analyticsLoad) analyticsError.value = true
  }
  if (requestId === analyticsLoad) void loadLogs()
}

async function loadLogs() {
  if (!authStore.isEmployeeLoggedIn) return
  const requestId = ++logsLoad
  loadingLogs.value = true
  logsError.value = false
  try {
    const res = await api.getUsageLogs(logsPage.value, logsPageSize.value, selectedModelFilter.value || undefined) as { data?: { total: number; items: LogItem[] } }
    if (!Array.isArray(res?.data?.items) || typeof res.data.total !== 'number') {
      throw new Error('调用明细数据格式异常')
    }
    if (requestId === logsLoad) logsData.value = res.data
  } catch {
    if (requestId === logsLoad) logsError.value = true
  } finally {
    if (requestId === logsLoad) loadingLogs.value = false
  }
}

function handleRangeChange(r: 'today' | '7d' | '30d' | 'all') {
  selectedRange.value = r
  loadAnalytics()
}

async function handleCopyKey() {
  if (!tokenDetail.value?.api_key) return
  const employeeSession = authStore.empToken
  const ok = await copyToClipboard(tokenDetail.value.api_key)
  if (active && ok && authStore.empToken === employeeSession) {
    clearTimeout(copyFeedback)
    copiedKey.value = true
    copyFeedback = setTimeout(() => {
      copiedKey.value = false
    }, 2000)
  }
}

async function handleConfirmReset() {
  if (await resetKey()) showResetConfirm.value = false
}

async function handleTriggerSync() {
  if (syncCooldown.value > 0 || syncing.value) return
  const employeeSession = authStore.empToken
  syncing.value = true
  syncMsg.value = ''
  try {
    const res = await api.triggerUsageSync() as { message?: string; last_successful_sync_time?: string }
    if (!active || authStore.empToken !== employeeSession) return
    syncMsg.value = res.message || '数据已刷新'
    if (res.last_successful_sync_time) {
      lastSyncTime.value = res.last_successful_sync_time
    }
    syncCooldown.value = 10
    syncTimer = setInterval(() => {
      syncCooldown.value--
      if (syncCooldown.value <= 0) clearInterval(syncTimer)
    }, 1000)
    await Promise.all([loadSummary(), loadAnalytics()])
  } catch (e: unknown) {
    const err = e as { message?: string }
    if (authStore.empToken === employeeSession) syncMsg.value = err.message || '刷新异常'
  } finally {
    if (authStore.empToken === employeeSession) syncing.value = false
  }
}

watch(() => authStore.empToken, (token) => {
  analyticsLoad++
  logsLoad++
  summaryLoad++
  setEmptyWorkspace()
  if (token) {
    void loadSummary()
    void loadAnalytics()
  }
}, { immediate: true })

function setEmptyWorkspace() {
  showPlainKey.value = false
  copiedKey.value = false
  showResetConfirm.value = false
  clearTimeout(copyFeedback)
  clearInterval(syncTimer)
  syncing.value = false
  syncCooldown.value = 0
  syncMsg.value = ''
  lastSyncTime.value = ''
  daily.value = undefined
  monthly.value = undefined
  overview.value = {}
  trendData.value = { categories: [], series: { requests: [], prompt_tokens: [], completion_tokens: [], total_tokens: [] } }
  modelDist.value = []
  logsData.value = { total: 0, items: [] }
  logsPage.value = 1
  selectedModelFilter.value = ''
  loadingLogs.value = false
  trendChartInstance?.dispose()
  modelChartInstance?.dispose()
  trendChartInstance = null
  modelChartInstance = null
}

watch(showDetails, (open) => {
  if (open) {
    void loadAnalytics()
  } else {
    analyticsLoad++
    logsLoad++
  }
})

watch([trendChartEl, modelChartEl, trendData, modelDist, () => themeStore.isDark], ([trendEl, modelEl]) => {
  if (!trendEl) {
    trendChartInstance?.dispose()
    trendChartInstance = null
  }
  if (!modelEl) {
    modelChartInstance?.dispose()
    modelChartInstance = null
  }
  if (trendEl || modelEl) void updateCharts()
}, { flush: 'post' })

onMounted(() => {
  window.addEventListener('resize', handleWindowResize)
})

onBeforeUnmount(() => {
  active = false
  analyticsLoad++
  logsLoad++
  summaryLoad++
  clearTimeout(copyFeedback)
  clearInterval(syncTimer)
  window.removeEventListener('resize', handleWindowResize)
  trendChartInstance?.dispose()
  modelChartInstance?.dispose()
})
</script>

<template>
  <section :class="['workspace-view', { compact: embed }]" aria-label="个人状态与 Token 用量">
    <!-- 凭证卡片 (纯白 Elevated 浮雕卡片) -->
    <MdCard variant="elevated">
      <div class="credential-card">
        <div class="cred-left">
          <div class="user-avatar-base">
            <UserCheck :size="22" />
          </div>
          <div class="cred-user-info">
            <div class="user-primary-row">
              <span class="user-name">{{ tokenDetail?.name || authStore.empName }}</span>
              <span class="user-empno">· {{ tokenDetail?.emp_no || authStore.empNo }}</span>
              <span v-if="!tokenDetail" class="status-pill warning">
                {{ loadingKey ? '读取中' : '待读取 Key' }}
              </span>
              <span v-else-if="tokenDetail.status === 'pending_claim' || !tokenDetail.api_key" class="status-pill warning">
                待申领 Key
              </span>
              <span v-else-if="tokenDetail?.status === 'disabled'" class="status-pill danger">
                Key 已禁用
              </span>
              <span v-else class="status-pill success">
                Key 正常启用
              </span>
            </div>
            <div class="user-dept">{{ tokenDetail?.department || '行内科技业务部' }}</div>
          </div>
        </div>

        <div class="cred-right">
          <div v-if="!tokenDetail" class="key-control-box">
            <span class="key-label">专属 API Key：</span>
            <span role="status">{{ loadingKey ? '正在读取专属 Key…' : keyFailure || '专属 Key 尚未读取' }}</span>
            <button v-if="!loadingKey" type="button" class="cred-icon-btn md-state-layer" @click="reloadKey">
              重试读取
            </button>
          </div>
          <div v-else-if="tokenDetail.status === 'pending_claim' || !tokenDetail.api_key" class="key-control-box">
            <span class="key-label">专属 API Key：</span>
            <code class="key-string pending">已登录，Key 暂未申领成功（网关服务可能未就绪）</code>
            <button
              type="button"
              class="cred-icon-btn reset-btn md-state-layer"
              :disabled="isClaiming"
              title="重新申领"
              @click="claimKey"
            >
              <RotateCcw :size="14" :class="{ 'spin-icon': isClaiming }" />
              <span>{{ isClaiming ? '申领中...' : '重新申领' }}</span>
            </button>
          </div>
          <div v-else class="key-control-box">
            <span class="key-label">专属 API Key：</span>
            <code class="key-string">
              {{ showPlainKey ? tokenDetail?.api_key : tokenDetail?.masked_key }}
            </code>
            <button
              type="button"
              class="cred-icon-btn md-state-layer"
              title="切换明文/掩码"
              @click="showPlainKey = !showPlainKey"
            >
              <EyeOff v-if="showPlainKey" :size="15" />
              <Eye v-else :size="15" />
            </button>
            <button
              type="button"
              class="cred-icon-btn md-state-layer"
              :class="{ copied: copiedKey }"
              title="复制 API Key"
              @click="handleCopyKey"
            >
              <Check v-if="copiedKey" :size="15" />
              <Copy v-else :size="15" />
              <span>{{ copiedKey ? '已复制' : '复制' }}</span>
            </button>
            <button
              type="button"
              class="cred-icon-btn reset-btn md-state-layer"
              title="重置专属 Key"
              @click="showResetConfirm = true"
            >
              <RotateCcw :size="14" />
              <span>重置 Key</span>
            </button>
          </div>
          <p v-if="tokenDetail && keyFailure && !showResetConfirm" class="reset-count-hint" role="status">{{ keyFailure }}</p>
          <div class="reset-count-hint">已重置 {{ tokenDetail?.reset_count || 0 }} 次 · 历史用量数据持续保留</div>
        </div>
      </div>
    </MdCard>

    <div class="period-grid">
      <MdCard v-for="period in [{ title: '今日', value: daily }, { title: '本月', value: monthly }]"
        :key="period.title" variant="filled">
        <strong>{{ period.title }}</strong>
        <div class="period-metrics tabular-nums">
          <span>{{ period.value?.total_tokens?.toLocaleString() ?? '—' }} Token</span>
          <span>{{ period.value?.total_requests?.toLocaleString() ?? '—' }} 次调用</span>
        </div>
      </MdCard>
    </div>
    <p v-if="summaryError" role="status">
      部分用量摘要暂不可用 <MdButton variant="text" @click="loadSummary">重试</MdButton>
    </p>
    <MdButton v-if="embed" variant="tonal" :aria-expanded="showDetails" @click="showDetails = !showDetails">
      {{ showDetails ? '收起用量趋势' : '展开用量趋势' }}
    </MdButton>

    <template v-if="showDetails">
      <!-- 用量看板操作栏 -->
      <section class="analytics-toolbar">
        <div class="range-selector">
          <button
            type="button"
            class="range-pill"
            :class="{ active: selectedRange === 'today' }"
            @click="handleRangeChange('today')"
          >
            今日
          </button>
          <button
            type="button"
            class="range-pill"
            :class="{ active: selectedRange === '7d' }"
            @click="handleRangeChange('7d')"
          >
            近 7 天
          </button>
          <button
            type="button"
            class="range-pill"
            :class="{ active: selectedRange === '30d' }"
            @click="handleRangeChange('30d')"
          >
            近 30 天
          </button>
          <button
            type="button"
            class="range-pill"
            :class="{ active: selectedRange === 'all' }"
            @click="handleRangeChange('all')"
          >
            全部历史
          </button>
        </div>

        <div class="sync-actions">
          <span class="sync-meta-hint">
            数据更新至：{{ lastSyncTime || '等待同步' }} · 后台每 5 分钟自动增量同步
          </span>
          <span v-if="syncMsg" class="sync-msg-text">{{ syncMsg }}</span>
          <button
            type="button"
            class="sync-btn md-state-layer"
            :disabled="syncing || syncCooldown > 0"
            @click="handleTriggerSync"
          >
            <RefreshCw :size="14" :class="{ rotating: syncing }" />
            <span>{{ syncCooldown > 0 ? `${syncCooldown}s 冷却` : '刷新用量明细' }}</span>
          </button>
        </div>
      </section>

      <!-- 核心 KPI 指标卡片群 (1:1 纯白浮雕卡片) -->
      <section class="kpi-grid">
        <MdCard variant="elevated" class="kpi-elevated-card">
          <div class="kpi-card-top">
            <div class="kpi-icon-base">
              <Zap :size="20" />
            </div>
            <span class="status-pill neutral">请求频次</span>
          </div>
          <div class="kpi-card-bottom">
            <span class="kpi-label">累计调用请求</span>
            <div class="kpi-number-row">
              <span class="kpi-number tabular-nums">{{ overview.total_requests?.toLocaleString() || 0 }}</span>
              <span class="kpi-unit">次</span>
            </div>
          </div>
        </MdCard>

        <MdCard variant="elevated" class="kpi-elevated-card">
          <div class="kpi-card-top">
            <div class="kpi-icon-base">
              <Layers :size="20" />
            </div>
            <span class="status-pill neutral">算力总耗</span>
          </div>
          <div class="kpi-card-bottom">
            <span class="kpi-label">消耗总 Token</span>
            <div class="kpi-number-row">
              <span class="kpi-number tabular-nums">{{ overview.total_tokens?.toLocaleString() || 0 }}</span>
            </div>
            <span class="kpi-meta-line">
              输入 {{ overview.prompt_tokens?.toLocaleString() || 0 }} · 输出 {{ overview.completion_tokens?.toLocaleString() || 0 }}
            </span>
          </div>
        </MdCard>

        <MdCard variant="elevated" class="kpi-elevated-card">
          <div class="kpi-card-top">
            <div class="kpi-icon-base">
              <Clock :size="20" />
            </div>
            <span class="status-pill neutral">响应效率</span>
          </div>
          <div class="kpi-card-bottom">
            <span class="kpi-label">平均响应耗时</span>
            <div class="kpi-number-row">
              <span class="kpi-number tabular-nums">{{ overview.avg_response_time || 0 }}</span>
              <span class="kpi-unit">ms</span>
            </div>
          </div>
        </MdCard>

        <MdCard variant="elevated" class="kpi-elevated-card">
          <div class="kpi-card-top">
            <div class="kpi-icon-base">
              <Cpu :size="20" />
            </div>
            <span class="status-pill neutral">偏好分析</span>
          </div>
          <div class="kpi-card-bottom">
            <span class="kpi-label">最常用大模型</span>
            <div class="kpi-number-row">
              <span class="kpi-number model-name-val">{{ overview.top_model || '-' }}</span>
            </div>
            <span class="kpi-meta-line">最近活跃: {{ overview.last_active_time || '-' }}</span>
          </div>
        </MdCard>
      </section>

      <p v-if="analyticsError" role="status">
        用量趋势暂不可用 <MdButton variant="text" @click="loadAnalytics">重试</MdButton>
      </p>
      <p v-if="chartError" role="status">
        图表暂不可用，可切换到数据表 <MdButton variant="text" @click="updateCharts">重试</MdButton>
      </p>
      <section class="charts-grid">
        <MdChartCard title="Token 消耗与调用频次趋势" :data="trendRows" :columns="trendColumns"
          row-key="time" export-filename="usage-trend.csv">
          <div ref="trendChartEl" class="echarts-container" />
        </MdChartCard>
        <MdChartCard title="模型调用分布" :data="modelDist" :columns="modelColumns"
          row-key="model_name" export-filename="usage-models.csv">
          <div ref="modelChartEl" class="echarts-container" />
        </MdChartCard>
      </section>

      <!-- 调用明细表 (纯白 Elevated 容器) -->
      <MdCard variant="elevated" class="logs-section">
        <p v-if="logsError" role="status">
          调用明细暂不可用 <MdButton variant="text" @click="loadLogs">重试</MdButton>
        </p>
        <div class="logs-header">
          <div class="table-title-box">
            <h4 class="table-title">调用明细流水检索</h4>
            <span class="table-sub">共 {{ logsData.total }} 条消费记录</span>
          </div>
          <div class="table-filters">
            <MdSelect
              v-model="selectedModelFilter"
              :options="modelFilterOptions"
              size="sm"
              @change="loadLogs"
            />
          </div>
        </div>

        <div class="table-container">
          <table class="m3-data-table">
            <thead>
              <tr>
                <th>调用时间</th>
                <th>模型名称</th>
                <th>输入 Prompt</th>
                <th>输出 Completion</th>
                <th>消耗总 Token</th>
                <th>耗时 (ms)</th>
                <th>传输协议</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="logsData.items.length === 0">
                <td colspan="7" class="empty-td">暂无匹配的明细记录</td>
              </tr>
              <tr v-for="row in logsData.items" :key="row.id">
                <td class="time-col tabular-nums">{{ row.created_at }}</td>
                <td class="model-col">{{ row.model_name }}</td>
                <td class="tabular-nums">{{ (row.prompt_tokens ?? 0).toLocaleString() }}</td>
                <td class="tabular-nums">{{ (row.completion_tokens ?? 0).toLocaleString() }}</td>
                <td class="tabular-nums"><strong>{{ (row.total_tokens ?? 0).toLocaleString() }}</strong></td>
                <td class="tabular-nums">{{ row.use_time }} ms</td>
                <td>
                  <span class="status-pill" :class="row.is_stream ? 'success' : 'neutral'">
                    {{ row.is_stream ? '流式' : '非流式' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 分页 -->
        <div v-if="logsData.total > logsPageSize" class="pagination-box">
          <button
            type="button"
            class="pg-btn md-state-layer"
            :disabled="logsPage <= 1"
            @click="logsPage--; loadLogs()"
          >
            上一页
          </button>
          <span class="pg-info tabular-nums">第 {{ logsPage }} 页</span>
          <button
            type="button"
            class="pg-btn md-state-layer"
            :disabled="logsPage * logsPageSize >= logsData.total"
            @click="logsPage++; loadLogs()"
          >
            下一页
          </button>
        </div>
      </MdCard>
    </template>

    <!-- 重置确认弹窗 -->
    <AdaptiveModal v-model="showResetConfirm" title="重置专属 API 密钥">
      <div class="reset-modal-body">
        <p class="warn-text">
          重置后旧 API Key 将立即失效！客户端需填入新 Key 才能继续调用。历史用量与日志数据将完整保留。
        </p>
        <p v-if="keyFailure" class="warn-text" role="status">{{ keyFailure }}</p>
      </div>
      <template #actions>
        <MdButton variant="text" @click="showResetConfirm = false">取消</MdButton>
        <MdButton :disabled="isResetting" @click="handleConfirmReset">
          {{ isResetting ? '正在重置…' : '确认重置' }}
        </MdButton>
      </template>
    </AdaptiveModal>
  </section>
</template>

<style scoped>
.workspace-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 凭证卡片 */
.credential-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 20px;
}

.cred-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-avatar-base {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-primary-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.user-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.user-empno {
  font-size: 13px;
  color: var(--md-sys-color-outline);
}

.user-dept {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.cred-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.key-control-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: var(--md-sys-shape-corner-medium);
  flex-wrap: wrap;
}

.key-label {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.key-string {
  font-family: "Cascadia Mono", monospace;
  font-size: 13px;
  color: var(--md-sys-color-on-surface);
  background-color: var(--md-sys-color-surface-container-lowest);
  padding: 4px 10px;
  border-radius: 6px;
}

.cred-icon-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.cred-icon-btn.copied {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.cred-icon-btn.reset-btn {
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
}

.reset-count-hint {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

/* 工具栏 */
.analytics-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

.range-selector {
  display: inline-flex;
  gap: 6px;
  background-color: var(--md-sys-color-primary-container);
  padding: 4px;
  border-radius: var(--md-sys-shape-corner-full);
}

.range-pill {
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
  transition: all 0.2s;
}

.range-pill.active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}


.sync-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.sync-meta-hint {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

.sync-msg-text {
  font-size: 13px;
  color: var(--md-sys-color-outline);
}

.sync-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}


/* KPI 卡片 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
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
  color: var(--md-sys-color-on-surface);
  line-height: 1.1;
  font-family: "Plus Jakarta Sans", sans-serif;
}


.kpi-number.model-name-val {
  font-size: 16px;
  font-weight: 600;
  word-break: break-all;
}

.kpi-unit {
  font-size: 13px;
  color: var(--md-sys-color-outline);
}

.kpi-meta-line {
  font-size: 12px;
  color: var(--md-sys-color-outline);
  margin-top: 2px;
}

/* 图表区 */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
  gap: 18px;
}

.echarts-container {
  width: 100%;
  height: 280px;
}

/* 日志明细表 */
.logs-section {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.logs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.table-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.table-sub {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

.table-container {
  overflow-x: auto;
}

.m3-data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.m3-data-table th,
.m3-data-table td {
  padding: 12px 14px;
  text-align: left;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.m3-data-table th {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-outline);
  background-color: var(--md-sys-color-primary-container);
}

.m3-data-table tbody tr:hover {
  background-color: var(--md-sys-color-primary-container);
}

.time-col {
  color: var(--md-sys-color-outline);
  white-space: nowrap;
}

.model-col {
  font-weight: 500;
  color: var(--md-sys-color-on-surface);
}

.empty-td {
  text-align: center;
  padding: 36px !important;
  color: var(--md-sys-color-outline);
}

.pagination-box {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}

.pg-btn {
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.pg-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pg-info {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

/* 重置弹窗样式 */
.reset-modal-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 8px 0;
}

.warn-text {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.6;
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.period-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.period-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-top: 6px;
  overflow-wrap: anywhere;
}

.compact { gap: 12px; --md-card-padding: 12px; }
.compact .credential-card { gap: 8px; }
.compact > .m3-button { align-self: start; }
.credential-card, .cred-right { min-width: 0; }
.credential-card .key-control-box { flex-wrap: wrap; max-width: 100%; }
.credential-card .key-string { min-width: 0; overflow-wrap: anywhere; }
.range-selector { flex-wrap: wrap; }

@media (prefers-reduced-motion: reduce) {
  .rotating { animation: none; }
}
</style>
