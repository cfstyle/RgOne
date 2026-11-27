<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Activity,
  FileSearch,
  LayoutDashboard,
  PlayCircle,
  RefreshCw,
  Server,
  ServerCrash,
  ShieldCheck,
  Wrench,
} from 'lucide-vue-next'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import McpAuditTab from './mcp/McpAuditTab.vue'
import McpDashboardTab, { type McpAdminTabKey } from './mcp/McpDashboardTab.vue'
import McpDebugTab from './mcp/McpDebugTab.vue'
import McpPermissionsTab from './mcp/McpPermissionsTab.vue'
import McpServersTab from './mcp/McpServersTab.vue'
import McpSystemTab from './mcp/McpSystemTab.vue'
import McpToolsTab from './mcp/McpToolsTab.vue'

const route = useRoute()
const router = useRouter()

const TABS: Array<{ key: McpAdminTabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: 'dashboard', label: '运行总览', icon: LayoutDashboard },
  { key: 'servers', label: 'MCP 服务', icon: Server },
  { key: 'tools', label: '工具目录', icon: Wrench },
  { key: 'debug', label: '在线调试', icon: PlayCircle },
  { key: 'permissions', label: '权限审批', icon: ShieldCheck },
  { key: 'audit', label: '调用审计', icon: FileSearch },
  { key: 'system', label: '系统状态', icon: Activity },
]

function normalizeTab(raw: unknown): McpAdminTabKey {
  const val = typeof raw === 'string' ? raw : 'dashboard'
  if (TABS.some((t) => t.key === val)) {
    return val as McpAdminTabKey
  }
  return 'dashboard'
}

const activeTab = ref<McpAdminTabKey>(normalizeTab(route.query.tab))
const pendingServerAction = ref<string | undefined>(undefined)
const pendingServerId = ref<string | undefined>(undefined)
const debugServiceId = ref<string | undefined>(undefined)
const debugToolName = ref<string | undefined>(undefined)

const engineUnavailable = ref(false)
const engineErrorMessage = ref('')
const retryNonce = ref(0)

function switchTab(tab: McpAdminTabKey) {
  activeTab.value = tab
  engineUnavailable.value = false
  void router.replace({ query: { ...route.query, tab } })
}

function handleNavigate(payload: { tab: McpAdminTabKey; action?: string; serviceId?: string }) {
  pendingServerAction.value = payload.action
  pendingServerId.value = payload.serviceId
  switchTab(payload.tab)
}

function handleDebugTool(payload: { serviceId: string; toolName: string }) {
  debugServiceId.value = payload.serviceId
  debugToolName.value = payload.toolName
  switchTab('debug')
}

function handleEngineError(message: string) {
  engineUnavailable.value = true
  engineErrorMessage.value = message
}

function retryEngine() {
  engineUnavailable.value = false
  engineErrorMessage.value = ''
  retryNonce.value += 1
}

watch(
  () => route.query.tab,
  (val) => {
    const next = normalizeTab(val)
    if (next !== activeTab.value) {
      activeTab.value = next
    }
  }
)
</script>

<template>
  <section class="mcp-hub-admin" aria-label="MCP 能力治理控制台">
    <!-- 顶部二级导航 Tab -->
    <div class="mcp-tabs-bar" role="tablist">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.key"
        :class="['mcp-tab-pill', { 'is-active': activeTab === tab.key }]"
        @click="switchTab(tab.key)"
      >
        <component :is="tab.icon" :size="15" />
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <!-- 故障隔离兜底：仅在 hub-core 不可用时降级显示，不影响 RgOne 其他管理模块 -->
    <MdCard v-if="engineUnavailable" variant="elevated">
      <div class="engine-down-box">
        <div class="engine-down-icon">
          <ServerCrash :size="28" />
        </div>
        <div class="engine-down-copy">
          <h3>MCP 能力引擎连接受阻</h3>
          <p>
            {{ engineErrorMessage || '无法连接 hub-core（/mcp-api/v1），RgOne 管理端其他功能运行正常。' }}
          </p>
        </div>
        <MdButton variant="tonal" @click="retryEngine">
          <RefreshCw :size="15" />
          <span>重试连接</span>
        </MdButton>
      </div>
    </MdCard>

    <template v-else>
      <McpDashboardTab
        v-if="activeTab === 'dashboard'"
        :key="`dash-${retryNonce}`"
        @navigate="handleNavigate"
        @engine-error="handleEngineError"
      />
      <McpServersTab
        v-else-if="activeTab === 'servers'"
        :key="`srv-${retryNonce}`"
        :pending-action="pendingServerAction"
        :initial-service-id="pendingServerId"
        @debug-tool="handleDebugTool"
        @action-handled="
          () => {
            pendingServerAction = undefined
            pendingServerId = undefined
          }
        "
        @engine-error="handleEngineError"
      />
      <McpToolsTab
        v-else-if="activeTab === 'tools'"
        :key="`tools-${retryNonce}`"
        @debug-tool="handleDebugTool"
        @engine-error="handleEngineError"
      />
      <McpDebugTab
        v-else-if="activeTab === 'debug'"
        :key="`debug-${retryNonce}`"
        :initial-service-id="debugServiceId"
        :initial-tool-name="debugToolName"
        @engine-error="handleEngineError"
      />
      <McpPermissionsTab
        v-else-if="activeTab === 'permissions'"
        :key="`perm-${retryNonce}`"
        @engine-error="handleEngineError"
      />
      <McpAuditTab
        v-else-if="activeTab === 'audit'"
        :key="`audit-${retryNonce}`"
        @engine-error="handleEngineError"
      />
      <McpSystemTab
        v-else
        :key="`sys-${retryNonce}`"
        @engine-error="handleEngineError"
      />
    </template>
  </section>
</template>

<style scoped>
.mcp-hub-admin {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.mcp-tabs-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.mcp-tab-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
}

.mcp-tab-pill:hover {
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
}

.mcp-tab-pill.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}

.engine-down-box {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.engine-down-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--md-sys-shape-corner-medium);
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.engine-down-copy {
  flex: 1;
  min-width: 240px;
}

.engine-down-copy h3 {
  margin: 0 0 4px;
  font-size: 16px;
}

.engine-down-copy p {
  margin: 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}
</style>
