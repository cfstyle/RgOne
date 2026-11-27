<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { CheckCircle2, Database, RefreshCw, Server, ShieldCheck } from 'lucide-vue-next'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { getMcpErrorMessage, getServices, getSystemStatus, isMcpEngineUnavailable } from '@/api/mcp'
import type { McpService, SystemStatusResponse } from '@/types/mcp'

const emit = defineEmits<{
  (e: 'engine-error', message: string): void
}>()

const toast = useToast()
const authStore = useAuthStore()
const loading = ref(true)
const status = ref<SystemStatusResponse | null>(null)
const services = ref<McpService[]>([])
const lastCheckedAt = ref('')

let abortController: AbortController | null = null

const activeServicesCount = computed(
  () => services.value.filter((s) => s.status === 'active').length
)
const abnormalServicesCount = computed(
  () => services.value.filter((s) => s.status !== 'active').length
)

async function fetchStatus() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  loading.value = true
  try {
    const [statusRes, svcList] = await Promise.all([
      getSystemStatus(abortController.signal),
      getServices(undefined, abortController.signal).catch(() => []),
    ])
    status.value = statusRes
    services.value = svcList
    lastCheckedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = getMcpErrorMessage(err, '获取引擎状态失败')
    if (isMcpEngineUnavailable(err)) emit('engine-error', msg)
    else toast.error(msg)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void fetchStatus()
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="mcp-system-tab">
    <div class="tab-toolbar">
      <div>
        <h2 class="tab-title">MCP 引擎运行状态与运维概览</h2>
        <p class="tab-subtitle">下游引擎 hub-core 探活、协议模式与统一鉴权状态</p>
      </div>
      <MdButton variant="tonal" :disabled="loading" @click="fetchStatus">
        <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
        <span>重新探活</span>
      </MdButton>
    </div>

    <div class="system-grid">
      <MdCard variant="elevated">
        <div class="card-head">
          <Server :size="18" />
          <h3>Hub Core 实例状态</h3>
        </div>
        <div v-if="status" class="kv-list">
          <div class="kv-row">
            <span>引擎名称 / 版本</span>
            <strong>{{ status.hub_name }} v{{ status.hub_version }}</strong>
          </div>
          <div class="kv-row">
            <span>运行状态</span>
            <span class="status-pill" :class="status.status === 'degraded' ? 'st-warn' : 'st-ok'">
              <CheckCircle2 :size="12" />
              <span>{{ status.status }}</span>
            </span>
          </div>
          <div class="kv-row">
            <span>对外 MCP 统一端点</span>
            <span class="mono">{{ status.mcp_endpoint }}</span>
          </div>
          <div class="kv-row">
            <span>独立存储状态 (SQLite)</span>
            <span class="mono"><Database :size="13" /> {{ status.database }}</span>
          </div>
          <div class="kv-row">
            <span>纳管上游服务数</span>
            <strong>{{ status.upstream_services_count }}</strong>
          </div>
        </div>
        <div v-else class="empty-inline">{{ loading ? '探活中...' : '暂无状态信息' }}</div>
      </MdCard>

      <MdCard variant="elevated">
        <div class="card-head">
          <ShieldCheck :size="18" />
          <h3>运维状态与鉴权摘要</h3>
        </div>
        <div class="kv-list">
          <div class="kv-row">
            <span>MCP 传输模式</span>
            <span class="status-pill st-ok">Streamable HTTP · 无状态 (stateless_http)</span>
          </div>
          <div class="kv-row">
            <span>RgOne 统一 JWT 鉴权</span>
            <span class="status-pill st-ok">已打通（当前管理员：{{ authStore.adminUsername || 'admin' }}）</span>
          </div>
          <div class="kv-row">
            <span>下游服务在线 / 异常</span>
            <strong>
              在线 {{ activeServicesCount }} 个 · 异常 {{ abnormalServicesCount }} 个
            </strong>
          </div>
          <div class="kv-row">
            <span>最近探活时间</span>
            <span class="mono">{{ lastCheckedAt || '—' }}</span>
          </div>
        </div>
      </MdCard>
    </div>
  </div>
</template>

<style scoped>
.mcp-system-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
}

.tab-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.system-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 900px) {
  .system-grid {
    grid-template-columns: 1fr;
  }
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.card-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.kv-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.kv-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.kv-row > span:first-child {
  color: var(--md-sys-color-on-surface-variant);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
}

.status-pill.st-ok {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.status-pill.st-warn {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
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
  font-size: 12px;
}
</style>
