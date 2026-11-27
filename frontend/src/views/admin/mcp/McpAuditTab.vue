<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Eye, RefreshCw, Search } from 'lucide-vue-next'
import AdaptiveModal from '@/components/m3/AdaptiveModal.vue'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import MdPagination from '@/components/m3/MdPagination.vue'
import MdSelect, { type SelectOption } from '@/components/m3/MdSelect.vue'
import { useToast } from '@/composables/useToast'
import { getAuditLogs, getMcpErrorMessage, getServices, isMcpEngineUnavailable } from '@/api/mcp'
import type { AuditLog, McpService } from '@/types/mcp'
import { formatDebugResponse, highlightDebugJson } from './responseFormat'

const statusOptions: SelectOption[] = [
  { label: '全部状态', value: '' },
  { label: 'success', value: 'success' },
  { label: 'tool_error', value: 'tool_error' },
  { label: 'exception', value: 'exception' },
  { label: 'rejected', value: 'rejected' },
]

const emit = defineEmits<{
  (e: 'engine-error', message: string): void
}>()

const toast = useToast()
const loading = ref(true)
const logs = ref<AuditLog[]>([])
const services = ref<McpService[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filters = reactive({
  service_id: '',
  tool_name: '',
  status: '',
})

const serviceOptions = computed<SelectOption[]>(() => [
  { label: '全部服务', value: '' },
  ...services.value.map((svc) => ({ label: svc.name, value: svc.id })),
])

const serviceNameMap = computed(() => new Map(services.value.map((svc) => [svc.id, svc.name])))

const detailModalVisible = ref(false)
const activeLog = ref<AuditLog | null>(null)

let abortController: AbortController | null = null

async function fetchLogs() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  loading.value = true
  try {
    const [logsRes, svcRes] = await Promise.all([
      getAuditLogs(
        {
          service_id: filters.service_id || undefined,
          tool_name: filters.tool_name.trim() || undefined,
          status: filters.status || undefined,
          limit: pageSize.value,
          offset: (page.value - 1) * pageSize.value,
        },
        abortController.signal
      ),
      services.value.length
        ? Promise.resolve(services.value)
        : getServices(undefined, abortController.signal).catch(() => []),
    ])
    logs.value = logsRes.items || []
    total.value = logsRes.total || 0
    if (Array.isArray(svcRes)) services.value = svcRes
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = getMcpErrorMessage(err, '获取审计日志失败')
    if (isMcpEngineUnavailable(err)) emit('engine-error', msg)
    else toast.error(msg)
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  void fetchLogs()
}

function handlePageChange(payload: { page: number; pageSize: number }) {
  page.value = payload.page
  pageSize.value = payload.pageSize
  void fetchLogs()
}

function formatArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return '{}'
  return formatDebugResponse(args)
}

const highlightedParamsHtml = computed(() =>
  highlightDebugJson(formatArgs(activeLog.value?.params_summary))
)

onMounted(() => {
  void fetchLogs()
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="mcp-audit-tab">
    <div class="tab-toolbar">
      <div class="filter-row">
        <MdSelect
          v-model="filters.service_id"
          :options="serviceOptions"
          size="sm"
          @change="handleSearch"
        />

        <div class="search-box">
          <Search :size="15" class="search-icon" />
          <input
            v-model="filters.tool_name"
            type="text"
            placeholder="按工具名称过滤..."
            class="search-input"
            @keyup.enter="handleSearch"
          />
        </div>

        <MdSelect
          v-model="filters.status"
          :options="statusOptions"
          size="sm"
          @change="handleSearch"
        />

        <MdButton variant="tonal" @click="handleSearch">查询</MdButton>
      </div>

      <MdButton variant="text" :disabled="loading" @click="fetchLogs">
        <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
        <span>刷新</span>
      </MdButton>
    </div>

    <MdCard variant="elevated">
      <div v-if="loading && !logs.length" class="empty-box">正在加载审计记录...</div>
      <div v-else-if="!logs.length" class="empty-box">暂无匹配的调用审计记录</div>
      <div v-else class="table-wrap">
        <table class="m3-native-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>调用主体</th>
              <th>来源 IP</th>
              <th>服务 / 工具</th>
              <th>客户端</th>
              <th>状态</th>
              <th>耗时</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in logs" :key="item.id">
              <td class="mono sub-text">
                {{ item.timestamp ? item.timestamp.slice(0, 19).replace('T', ' ') : '-' }}
              </td>
              <td>{{ item.user_id || '-' }}</td>
              <td class="mono sub-text">{{ item.client_ip || '-' }}</td>
              <td>
                <div class="tool-cell">
                  <strong>{{ item.tool_name }}</strong>
                  <span class="sub-text">{{ serviceNameMap.get(item.service_id) || item.service_id }}</span>
                </div>
              </td>
              <td>
                <span class="tag-pill">{{ item.client_id || '-' }}</span>
              </td>
              <td>
                <span
                  class="status-pill"
                  :class="item.result_status.toLowerCase() === 'success' ? 'st-success' : 'st-error'"
                >
                  {{ item.result_status }}
                </span>
              </td>
              <td class="mono">{{ item.duration_ms }} ms</td>
              <td>
                <MdButton
                  variant="text"
                  @click="
                    () => {
                      activeLog = item
                      detailModalVisible = true
                    }
                  "
                >
                  <Eye :size="14" />
                  <span>查看</span>
                </MdButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="total > 0" class="pagination-wrap">
        <MdPagination :page="page" :page-size="pageSize" :total="total" @change="handlePageChange" />
      </div>
    </MdCard>

    <AdaptiveModal v-model="detailModalVisible" title="调用审计详情" max-width="640px">
      <div v-if="activeLog" class="audit-detail">
        <div class="kv-grid">
          <div class="kv-item">
            <span class="kv-label">调用时间</span>
            <span class="kv-val mono">{{ activeLog.timestamp ? activeLog.timestamp.slice(0, 19).replace('T', ' ') : '-' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-label">调用主体</span>
            <span class="kv-val">{{ activeLog.user_id || '-' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-label">来源 IP</span>
            <span class="kv-val mono">{{ activeLog.client_ip || '-' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-label">客户端</span>
            <span class="kv-val">{{ activeLog.client_id || '-' }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-label">所属服务</span>
            <span class="kv-val">{{ serviceNameMap.get(activeLog.service_id) || activeLog.service_id }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-label">工具名称</span>
            <span class="kv-val mono break-all-cell">{{ activeLog.tool_name }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-label">执行状态</span>
            <span class="kv-val">{{ activeLog.result_status }}</span>
          </div>
          <div class="kv-item">
            <span class="kv-label">耗时</span>
            <span class="kv-val mono">{{ activeLog.duration_ms }} ms</span>
          </div>
        </div>
        <div class="detail-block">
          <strong>脱敏入参 (Params Summary)</strong>
          <div
            v-if="!activeLog.params_summary || Object.keys(activeLog.params_summary).length === 0"
            class="empty-params-hint"
          >
            无调用入参
          </div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <pre v-else class="detail-pre"><code v-html="highlightedParamsHtml"></code></pre>
        </div>
      </div>
      <template #actions>
        <div class="modal-footer-actions">
          <MdButton variant="filled" @click="detailModalVisible = false">关闭</MdButton>
        </div>
      </template>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.mcp-audit-tab {
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

.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.search-input {
  width: 220px;
  height: 36px;
  padding: 0 12px 0 34px;
  border-radius: var(--md-sys-shape-corner-full);
  border: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  outline: none;
}

.table-wrap {
  overflow-x: auto;
}

.m3-native-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.m3-native-table th,
.m3-native-table td {
  padding: 12px 10px;
  text-align: left;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.m3-native-table th {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.tool-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sub-text {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.tag-pill,
.status-pill {
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
}

.tag-pill {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface-variant);
}

.status-pill.st-success {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.status-pill.st-denied {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.status-pill.st-error {
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
}

.pagination-wrap {
  margin-top: 14px;
}

.audit-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
  padding: 12px 14px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
  font-size: 12px;
}

.kv-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.kv-label {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.kv-val {
  color: var(--md-sys-color-on-surface);
  font-weight: 500;
}

.break-all-cell {
  word-break: break-all;
}

.empty-params-hint {
  padding: 14px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
  text-align: center;
}

.detail-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
}

.detail-pre {
  margin: 0;
  padding: 12px 14px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow: auto;
  max-height: 360px;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-pre :deep(.json-key) {
  color: var(--md-sys-color-primary);
  font-weight: 600;
}

.detail-pre :deep(.json-string) {
  color: var(--sys-status-success-text);
}

.detail-pre :deep(.json-number),
.detail-pre :deep(.json-boolean) {
  color: var(--sys-status-warning-text);
}

.detail-pre :deep(.json-null) {
  color: var(--md-sys-color-on-surface-variant);
}

.error-box {
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
  font-size: 12px;
}

.modal-footer-actions {
  display: flex;
  justify-content: flex-end;
}

.empty-box {
  padding: 28px;
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
