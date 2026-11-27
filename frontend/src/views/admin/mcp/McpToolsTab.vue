<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Edit3, PlayCircle, RefreshCw, Search } from 'lucide-vue-next'
import AdaptiveModal from '@/components/m3/AdaptiveModal.vue'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import MdSelect, { type SelectOption } from '@/components/m3/MdSelect.vue'
import MdSwitch from '@/components/m3/MdSwitch.vue'

const riskLevelOptions: SelectOption[] = [
  { label: 'L0 (公开只读)', value: 'L0' },
  { label: 'L1 (受控只读)', value: 'L1' },
  { label: 'L2 (业务写入)', value: 'L2' },
  { label: 'L3 (高危/敏感操作)', value: 'L3' },
]
import { useToast } from '@/composables/useToast'
import {
  getMcpErrorMessage,
  getServices,
  isMcpEngineUnavailable,
  listTools,
  updateToolPolicy,
} from '@/api/mcp'
import type { McpService, RegisteredTool, RiskLevel } from '@/types/mcp'

const emit = defineEmits<{
  (e: 'debug-tool', payload: { serviceId: string; toolName: string }): void
  (e: 'engine-error', message: string): void
}>()

const toast = useToast()
const loading = ref(true)
const tools = ref<RegisteredTool[]>([])
const services = ref<McpService[]>([])
const selectedServiceId = ref('')
const searchKeyword = ref('')

// Schema 弹窗
const schemaModalVisible = ref(false)
const selectedTool = ref<RegisteredTool | null>(null)

// 策略编辑弹窗
const policyModalVisible = ref(false)
const savingPolicy = ref(false)
const policyForm = reactive<{
  risk_level: RiskLevel
  requires_confirmation: boolean
  requires_credentials: boolean
  enabled: boolean
}>({
  risk_level: 'L0',
  requires_confirmation: false,
  requires_credentials: false,
  enabled: true,
})

let abortController: AbortController | null = null

const serviceMap = computed(() => {
  return new Map(services.value.map((svc) => [svc.id, svc.name]))
})

const serviceFilterOptions = computed<SelectOption[]>(() => [
  { label: '全部服务', value: '' },
  ...services.value.map((svc) => ({ label: svc.name, value: svc.id })),
])

const filteredTools = computed(() => {
  return tools.value.filter((tool) => {
    if (selectedServiceId.value && tool.service_id !== selectedServiceId.value) return false
    const kw = searchKeyword.value.trim().toLowerCase()
    if (!kw) return true
    return (
      tool.name.toLowerCase().includes(kw) ||
      tool.namespace_name.toLowerCase().includes(kw) ||
      (tool.description || '').toLowerCase().includes(kw)
    )
  })
})

async function fetchData() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  loading.value = true
  try {
    const [toolRes, svcRes] = await Promise.all([
      listTools(undefined, abortController.signal),
      getServices(undefined, abortController.signal),
    ])
    tools.value = toolRes
    services.value = svcRes
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = getMcpErrorMessage(err, '获取工具列表失败')
    if (isMcpEngineUnavailable(err)) emit('engine-error', msg)
    else toast.error(msg)
  } finally {
    loading.value = false
  }
}

async function toggleEnabled(tool: RegisteredTool, enabled: boolean) {
  try {
    const updated = await updateToolPolicy(tool.id, { enabled })
    const idx = tools.value.findIndex((item) => item.id === tool.id)
    if (idx >= 0) tools.value[idx] = updated
    toast.success(enabled ? '工具已启用' : '工具已停用')
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '更新工具状态失败'))
  }
}

function openPolicyModal(tool: RegisteredTool) {
  selectedTool.value = tool
  policyForm.risk_level = tool.risk_level || 'L0'
  policyForm.requires_confirmation = Boolean(tool.requires_confirmation)
  policyForm.requires_credentials = Boolean(tool.requires_credentials)
  policyForm.enabled = Boolean(tool.enabled)
  policyModalVisible.value = true
}

async function savePolicy() {
  if (!selectedTool.value) return
  savingPolicy.value = true
  try {
    const updated = await updateToolPolicy(selectedTool.value.id, {
      risk_level: policyForm.risk_level,
      requires_confirmation: policyForm.requires_confirmation,
      requires_credentials: policyForm.requires_credentials,
      enabled: policyForm.enabled,
    })
    const idx = tools.value.findIndex((item) => item.id === selectedTool.value?.id)
    if (idx >= 0) tools.value[idx] = updated
    toast.success('工具策略已更新')
    policyModalVisible.value = false
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '保存策略失败'))
  } finally {
    savingPolicy.value = false
  }
}

onMounted(() => {
  void fetchData()
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="mcp-tools-tab">
    <div class="tab-toolbar">
      <div class="filter-row">
        <div class="search-box">
          <Search :size="15" class="search-icon" />
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索工具名称 / 命名空间..."
            class="search-input"
          />
        </div>
        <MdSelect v-model="selectedServiceId" :options="serviceFilterOptions" size="sm" />
      </div>
      <MdButton variant="tonal" :disabled="loading" @click="fetchData">
        <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
        <span>刷新目录</span>
      </MdButton>
    </div>

    <MdCard variant="elevated">
      <div v-if="loading && !tools.length" class="empty-box">正在加载工具目录...</div>
      <div v-else-if="!filteredTools.length" class="empty-box">暂无匹配的工具契约</div>
      <div v-else class="table-wrap">
        <table class="m3-native-table">
          <thead>
            <tr>
              <th>工具名称</th>
              <th>所属服务</th>
              <th>风险等级</th>
              <th>安全约束</th>
              <th>启用状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="tool in filteredTools" :key="tool.id">
              <td>
                <div class="tool-name-cell">
                  <strong>{{ tool.name }}</strong>
                  <span class="mono sub-text">{{ tool.namespace_name }}</span>
                </div>
              </td>
              <td>{{ tool.service_name || serviceMap.get(tool.service_id) || tool.service_id }}</td>
              <td>
                <span class="risk-pill" :class="`risk-${tool.risk_level.toLowerCase()}`">
                  {{ tool.risk_level }}
                </span>
              </td>
              <td>
                <div class="constraint-tags">
                  <span v-if="tool.requires_confirmation" class="tag-pill">需确认</span>
                  <span v-if="tool.requires_credentials" class="tag-pill">需个人凭据</span>
                  <span v-if="!tool.requires_confirmation && !tool.requires_credentials">-</span>
                </div>
              </td>
              <td>
                <MdSwitch
                  :model-value="tool.enabled"
                  @update:model-value="(val) => toggleEnabled(tool, val)"
                />
              </td>
              <td>
                <div class="row-actions">
                  <MdButton
                    variant="text"
                    @click="
                      () => {
                        selectedTool = tool
                        schemaModalVisible = true
                      }
                    "
                  >
                    Schema
                  </MdButton>
                  <MdButton variant="text" @click="openPolicyModal(tool)">
                    <Edit3 :size="14" />
                    <span>策略</span>
                  </MdButton>
                  <MdButton
                    variant="tonal"
                    @click="emit('debug-tool', { serviceId: tool.service_id, toolName: tool.name })"
                  >
                    <PlayCircle :size="14" />
                    <span>调试</span>
                  </MdButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </MdCard>

    <AdaptiveModal
      v-model="policyModalVisible"
      :title="`治理策略: ${selectedTool?.name || ''}`"
      max-width="480px"
    >
      <div class="policy-form">
        <div class="form-item">
          <label class="form-label">风险分级</label>
          <MdSelect v-model="policyForm.risk_level" :options="riskLevelOptions" style="width: 100%" />
        </div>
        <div class="switch-row">
          <span>需要人工确认 (requires_confirmation)</span>
          <MdSwitch v-model="policyForm.requires_confirmation" />
        </div>
        <div class="switch-row">
          <span>需要个人凭据 (requires_credentials)</span>
          <MdSwitch v-model="policyForm.requires_credentials" />
        </div>
        <div class="switch-row">
          <span>启用此工具 (enabled)</span>
          <MdSwitch v-model="policyForm.enabled" />
        </div>
      </div>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="policyModalVisible = false">取消</MdButton>
          <MdButton variant="filled" :disabled="savingPolicy" @click="savePolicy">
            {{ savingPolicy ? '保存中...' : '保存策略' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <AdaptiveModal
      v-model="schemaModalVisible"
      :title="`Input Schema: ${selectedTool?.name || ''}`"
      max-width="640px"
    >
      <pre class="schema-pre"><code>{{ JSON.stringify(selectedTool?.input_schema || {}, null, 2) }}</code></pre>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="filled" @click="schemaModalVisible = false">关闭</MdButton>
        </div>
      </template>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.mcp-tools-tab {
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
  width: 240px;
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

.tool-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sub-text {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.risk-pill,
.tag-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
}

.risk-l0 {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.risk-l1 {
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-primary-container);
}

.risk-l2 {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.risk-l3 {
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
}

.tag-pill {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface-variant);
}

.constraint-tags,
.row-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.policy-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
}

.form-input {
  padding: 8px 10px;
  border-radius: var(--md-sys-shape-corner-small);
  border: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.schema-pre {
  margin: 0;
  padding: 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  overflow-x: auto;
}

.modal-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
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
