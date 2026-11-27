<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  Activity,
  BookOpen,
  Download,
  Edit3,
  Eye,
  PlayCircle,
  Plus,
  Power,
  RefreshCw,
  Search,
  Upload,
} from 'lucide-vue-next'
import AdaptiveModal from '@/components/m3/AdaptiveModal.vue'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import MdDrawer from '@/components/m3/MdDrawer.vue'
import MdSwitch from '@/components/m3/MdSwitch.vue'
import { useToast } from '@/composables/useToast'
import {
  downloadPluginTemplate,
  getDeveloperGuide,
  getMcpErrorMessage,
  getService,
  getServices,
  inspectPluginZip,
  installPluginZip,
  isMcpEngineUnavailable,
  listTools,
  refreshServiceTools,
  registerService,
  testServiceConnection,
  updateServiceCredentialTrust,
  updateServiceMetadata,
  updateServiceStatus,
} from '@/api/mcp'
import type {
  McpService,
  PluginInspectResult,
  RegisteredTool,
  ServiceStatus,
} from '@/types/mcp'

const props = defineProps<{
  pendingAction?: string
  initialServiceId?: string
}>()

const emit = defineEmits<{
  (e: 'debug-tool', payload: { serviceId: string; toolName: string }): void
  (e: 'engine-error', message: string): void
  (e: 'action-handled'): void
}>()

const toast = useToast()
const loading = ref(true)
const services = ref<McpService[]>([])
const allTools = ref<RegisteredTool[]>([])
const searchKeyword = ref('')
const statusFilter = ref<'all' | ServiceStatus>('all')
const busyIds = ref<Set<string>>(new Set())

// 注册远程服务弹窗
const registerModalVisible = ref(false)
const registering = ref(false)
const registerForm = reactive({
  service_id: '',
  name: '',
  endpoint_url: '',
  owner: '',
  category: '通用',
  description: '',
  auth_mode: 'platform_sso',
  auth_label: 'Hub 统一认证',
})

// ZIP 插件发布弹窗
const publishModalVisible = ref(false)
const pluginFile = ref<File | null>(null)
const inspectingPlugin = ref(false)
const installingPlugin = ref(false)
const downloadingTemplate = ref(false)
const inspectResult = ref<PluginInspectResult | null>(null)
const guideModalVisible = ref(false)
const loadingGuide = ref(false)
const guideContent = ref('')

// 服务详情抽屉
const detailDrawerVisible = ref(false)
const loadingDetail = ref(false)
const currentService = ref<McpService | null>(null)
const serviceTools = ref<RegisteredTool[]>([])
const schemaModalVisible = ref(false)
const schemaTool = ref<RegisteredTool | null>(null)

// 元数据编辑弹窗
const editModalVisible = ref(false)
const savingEdit = ref(false)
const editForm = reactive({
  name: '',
  description: '',
  owner: '',
  category: '通用',
  auth_mode: 'platform_sso',
  auth_label: 'Hub 统一认证',
  auth_guide: '',
  auth_entry_url: '',
  examples_text: '',
})

let abortController: AbortController | null = null

const toolCountMap = computed(() => {
  const map = new Map<string, number>()
  for (const t of allTools.value) {
    map.set(t.service_id, (map.get(t.service_id) ?? 0) + 1)
  }
  return map
})

function getToolCount(svc: McpService): number {
  return svc.tools_count ?? toolCountMap.value.get(svc.id) ?? 0
}

const filteredServices = computed(() => {
  return services.value.filter((svc) => {
    if (statusFilter.value !== 'all' && svc.status !== statusFilter.value) {
      return false
    }
    const kw = searchKeyword.value.trim().toLowerCase()
    if (!kw) return true
    return (
      svc.name.toLowerCase().includes(kw) ||
      svc.id.toLowerCase().includes(kw) ||
      (svc.description || '').toLowerCase().includes(kw) ||
      (svc.owner || '').toLowerCase().includes(kw)
    )
  })
})

function setBusy(id: string, busy: boolean) {
  const next = new Set(busyIds.value)
  if (busy) next.add(id)
  else next.delete(id)
  busyIds.value = next
}

async function fetchServices() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  loading.value = true
  try {
    const [svcList, toolList] = await Promise.all([
      getServices(undefined, abortController.signal),
      listTools(undefined, abortController.signal).catch(() => []),
    ])
    services.value = svcList
    allTools.value = toolList
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = getMcpErrorMessage(err, '获取服务列表失败')
    if (isMcpEngineUnavailable(err)) emit('engine-error', msg)
    else toast.error(msg)
  } finally {
    loading.value = false
  }
}

async function openDetail(serviceId: string) {
  detailDrawerVisible.value = true
  loadingDetail.value = true
  try {
    const [svc, tools] = await Promise.all([getService(serviceId), listTools(serviceId)])
    currentService.value = svc
    serviceTools.value = tools
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '加载服务详情失败'))
    detailDrawerVisible.value = false
  } finally {
    loadingDetail.value = false
  }
}

async function handleRefresh(svc: McpService) {
  setBusy(svc.id, true)
  try {
    const res = await refreshServiceTools(svc.id)
    toast.success(`刷新成功，发现 ${res.tools_discovered} 个工具契约`)
    await fetchServices()
    if (currentService.value?.id === svc.id) {
      await openDetail(svc.id)
    }
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '刷新工具失败'))
  } finally {
    setBusy(svc.id, false)
  }
}

async function handleTestConnection(svc: McpService) {
  setBusy(svc.id, true)
  try {
    const res = await testServiceConnection(svc.id)
    if (res.success) {
      toast.success(`连接正常 (${res.latency_ms} ms)：${res.message}`)
    } else {
      toast.warning(`连接测试未通过：${res.message}`)
    }
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '连通性测试失败'))
  } finally {
    setBusy(svc.id, false)
  }
}

async function handleToggleStatus(svc: McpService) {
  const target: ServiceStatus = svc.status === 'active' ? 'inactive' : 'active'
  const label = target === 'active' ? '启用' : '停用'
  if (!window.confirm(`确定要${label}服务「${svc.name}」吗？`)) return
  setBusy(svc.id, true)
  try {
    const updated = await updateServiceStatus(svc.id, target)
    toast.success(`已${label}服务`)
    await fetchServices()
    if (currentService.value?.id === svc.id) {
      currentService.value = updated
    }
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '更新状态失败'))
  } finally {
    setBusy(svc.id, false)
  }
}

async function handleToggleTrustCredentials(svc: McpService, trusted: boolean) {
  setBusy(svc.id, true)
  try {
    const updated = await updateServiceCredentialTrust(svc.id, trusted)
    currentService.value = updated
    toast.success(trusted ? '已允许个人参数透传' : '已关闭个人参数透传')
    await fetchServices()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '更新参数透传信任策略失败'))
  } finally {
    setBusy(svc.id, false)
  }
}

function openRegisterModal() {
  registerForm.service_id = ''
  registerForm.name = ''
  registerForm.endpoint_url = ''
  registerForm.owner = ''
  registerForm.category = '通用'
  registerForm.description = ''
  registerForm.auth_mode = 'platform_sso'
  registerForm.auth_label = 'Hub 统一认证'
  registerModalVisible.value = true
}

async function handleSubmitRegister() {
  const serviceId = registerForm.service_id.trim()
  const name = registerForm.name.trim()
  const endpointUrl = registerForm.endpoint_url.trim()
  if (!serviceId || !name || !endpointUrl) {
    toast.warning('请填写服务标识、服务名称与接入地址 (Endpoint URL)')
    return
  }
  if (!/^[a-z][a-z0-9_-]{1,62}$/.test(serviceId)) {
    toast.warning('服务标识必须小写字母开头，仅含小写字母、数字、下划线或连字符（2-63位）')
    return
  }
  registering.value = true
  try {
    await registerService({
      service_id: serviceId,
      name,
      endpoint_url: endpointUrl,
      owner: registerForm.owner.trim() || undefined,
      category: registerForm.category.trim() || '通用',
      description: registerForm.description.trim() || undefined,
      auth_mode: registerForm.auth_mode,
      auth_label: registerForm.auth_label.trim() || 'Hub 统一认证',
    })
    toast.success('MCP 服务注册成功，已自动拉取工具契约')
    registerModalVisible.value = false
    await fetchServices()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '注册失败'))
  } finally {
    registering.value = false
  }
}

function openPublishModal() {
  pluginFile.value = null
  inspectResult.value = null
  publishModalVisible.value = true
}

async function handleDownloadTemplate() {
  downloadingTemplate.value = true
  try {
    const blob = await downloadPluginTemplate()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'python-mcp-demo.zip'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success('已下载插件脚手架模板 (python-mcp-demo.zip)')
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '下载模板失败'))
  } finally {
    downloadingTemplate.value = false
  }
}

async function handleOpenGuide() {
  guideModalVisible.value = true
  if (guideContent.value) return
  loadingGuide.value = true
  try {
    const res = await getDeveloperGuide()
    guideContent.value = res.content || '暂无开发规范文档'
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '加载开发规范失败'))
  } finally {
    loadingGuide.value = false
  }
}

async function handlePluginFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0] || null
  pluginFile.value = file
  inspectResult.value = null
  if (!file) return

  inspectingPlugin.value = true
  try {
    inspectResult.value = await inspectPluginZip(file)
    toast.success('插件清单预检通过')
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '插件包预检失败'))
    pluginFile.value = null
  } finally {
    inspectingPlugin.value = false
  }
}

async function handleInstallPlugin() {
  if (!pluginFile.value) return
  installingPlugin.value = true
  try {
    const svc = await installPluginZip(pluginFile.value)
    toast.success(`插件「${svc.name}」(${svc.id}) 发布上线成功`)
    publishModalVisible.value = false
    await fetchServices()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '插件发布失败'))
  } finally {
    installingPlugin.value = false
  }
}

function openEditMetadata(svc: McpService) {
  currentService.value = svc
  editForm.name = svc.name || ''
  editForm.description = svc.description || ''
  editForm.owner = svc.owner || ''
  editForm.category = svc.category || '通用'
  editForm.auth_mode = svc.auth_mode || 'platform_sso'
  editForm.auth_label = svc.auth_label || 'Hub 统一认证'
  editForm.auth_guide = svc.auth_guide || ''
  editForm.auth_entry_url = svc.auth_entry_url || ''
  editForm.examples_text = (svc.usage_examples || []).join('\n')
  editModalVisible.value = true
}

async function handleSaveMetadata() {
  if (!currentService.value) return
  if (!editForm.name.trim()) {
    toast.warning('服务名称不能为空')
    return
  }
  savingEdit.value = true
  try {
    const updated = await updateServiceMetadata(currentService.value.id, {
      name: editForm.name.trim(),
      description: editForm.description.trim(),
      owner: editForm.owner.trim(),
      category: editForm.category.trim() || '通用',
      auth_mode: editForm.auth_mode.trim(),
      auth_label: editForm.auth_label.trim() || 'Hub 统一认证',
      auth_guide: editForm.auth_guide.trim(),
      auth_entry_url: editForm.auth_entry_url.trim(),
      usage_examples: editForm.examples_text
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
    })
    currentService.value = updated
    toast.success('服务元数据更新成功')
    editModalVisible.value = false
    await fetchServices()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '更新失败'))
  } finally {
    savingEdit.value = false
  }
}

watch(
  () => props.pendingAction,
  (action) => {
    if (action === 'register') {
      openRegisterModal()
      emit('action-handled')
    } else if (action === 'publish') {
      openPublishModal()
      emit('action-handled')
    }
  },
  { immediate: true }
)

watch(
  () => props.initialServiceId,
  (sid) => {
    if (sid) {
      void openDetail(sid)
      emit('action-handled')
    }
  },
  { immediate: true }
)

onMounted(() => {
  void fetchServices()
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="mcp-servers-tab">
    <div class="tab-toolbar">
      <div class="filter-left">
        <div class="search-box">
          <Search :size="15" class="search-icon" />
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索服务名称、ID、负责人..."
            class="search-input"
          />
        </div>
        <div class="status-pills">
          <button
            v-for="st in ['all', 'active', 'inactive', 'degraded'] as const"
            :key="st"
            type="button"
            :class="['filter-pill', { 'is-active': statusFilter === st }]"
            @click="statusFilter = st"
          >
            {{ st === 'all' ? '全部' : st }}
          </button>
        </div>
      </div>

      <div class="toolbar-actions">
        <MdButton variant="text" :disabled="loading" @click="fetchServices">
          <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
          <span>刷新</span>
        </MdButton>
        <MdButton variant="tonal" @click="openPublishModal">
          <Upload :size="15" />
          <span>ZIP 插件发布</span>
        </MdButton>
        <MdButton variant="filled" @click="openRegisterModal">
          <Plus :size="15" />
          <span>注册远程服务</span>
        </MdButton>
      </div>
    </div>

    <MdCard variant="elevated">
      <div v-if="loading && !services.length" class="empty-box">正在加载 MCP 服务列表...</div>
      <div v-else-if="!filteredServices.length" class="empty-box">暂无匹配的 MCP 服务</div>
      <div v-else class="table-wrap">
        <table class="m3-native-table">
          <thead>
            <tr>
              <th>服务名称</th>
              <th>协议</th>
              <th>端点 / 运行时</th>
              <th>工具数</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="svc in filteredServices" :key="svc.id">
              <td>
                <div class="name-cell">
                  <strong>{{ svc.name }}</strong>
                  <span class="mono sub-id">{{ svc.id }}</span>
                </div>
              </td>
              <td>
                <span class="tag-pill">Streamable HTTP</span>
              </td>
              <td>
                <span class="mono endpoint-text">{{ svc.endpoint_url }}</span>
              </td>
              <td>{{ getToolCount(svc) }}</td>
              <td>
                <span class="status-pill" :class="`st-${svc.status}`">{{ svc.status }}</span>
              </td>
              <td>
                <div class="row-actions">
                  <MdButton variant="text" @click="openDetail(svc.id)">
                    <Eye :size="14" />
                    <span>详情</span>
                  </MdButton>
                  <MdButton
                    variant="text"
                    :disabled="busyIds.has(svc.id)"
                    @click="handleRefresh(svc)"
                  >
                    <RefreshCw :size="14" />
                    <span>刷新工具</span>
                  </MdButton>
                  <MdButton
                    variant="text"
                    :disabled="busyIds.has(svc.id)"
                    @click="handleTestConnection(svc)"
                  >
                    <Activity :size="14" />
                    <span>测连</span>
                  </MdButton>
                  <MdButton
                    variant="text"
                    :disabled="busyIds.has(svc.id)"
                    @click="handleToggleStatus(svc)"
                  >
                    <Power :size="14" />
                    <span>{{ svc.status === 'active' ? '停用' : '启用' }}</span>
                  </MdButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </MdCard>

    <!-- 注册远程服务弹窗 -->
    <AdaptiveModal v-model="registerModalVisible" title="注册远程 MCP Service" max-width="600px">
      <div class="form-grid">
        <div class="form-row-2">
          <div class="form-item">
            <label class="form-label">服务唯一标识 (Service ID) *</label>
            <input
              v-model="registerForm.service_id"
              type="text"
              placeholder="如：finance, ticm (小写字母开头)"
              class="form-input mono"
            />
          </div>
          <div class="form-item">
            <label class="form-label">服务显示名称 *</label>
            <input v-model="registerForm.name" type="text" placeholder="如：财务知识助手" class="form-input" />
          </div>
        </div>
        <div class="form-item">
          <label class="form-label">上游端点 URL (Streamable HTTP) *</label>
          <input
            v-model="registerForm.endpoint_url"
            type="text"
            placeholder="http://my-mcp-server:8090/mcp"
            class="form-input mono"
          />
        </div>
        <div class="form-row-2">
          <div class="form-item">
            <label class="form-label">分类标签</label>
            <input v-model="registerForm.category" type="text" placeholder="通用 / 业务 / 知识" class="form-input" />
          </div>
          <div class="form-item">
            <label class="form-label">负责人</label>
            <input v-model="registerForm.owner" type="text" placeholder="团队或负责人" class="form-input" />
          </div>
        </div>
        <div class="form-item">
          <label class="form-label">认证标签</label>
          <input v-model="registerForm.auth_label" type="text" placeholder="Hub 统一认证" class="form-input" />
        </div>
        <div class="form-item">
          <label class="form-label">业务描述</label>
          <textarea
            v-model="registerForm.description"
            rows="3"
            placeholder="描述该 MCP 提供的能力边界"
            class="form-textarea"
          ></textarea>
        </div>
      </div>
      <template #actions>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="registerModalVisible = false">取消</MdButton>
          <MdButton variant="filled" :disabled="registering" @click="handleSubmitRegister">
            {{ registering ? '注册中...' : '确认注册并发现工具' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- ZIP 插件发布弹窗 -->
    <AdaptiveModal v-model="publishModalVisible" title="ZIP 插件包一键发布" max-width="620px">
      <div class="publish-panel">
        <div class="guide-banner">
          <span>不熟悉包结构？可下载脚手架模板包（含 manifest.json 示例）或阅读规范。</span>
          <div class="guide-banner-actions">
            <MdButton variant="text" @click="handleOpenGuide">
              <BookOpen :size="14" />
              <span>开发规范</span>
            </MdButton>
            <MdButton variant="tonal" :disabled="downloadingTemplate" @click="handleDownloadTemplate">
              <Download :size="14" />
              <span>{{ downloadingTemplate ? '下载中...' : '下载脚手架 (.zip)' }}</span>
            </MdButton>
          </div>
        </div>

        <label class="upload-dropzone">
          <Upload :size="24" />
          <span>{{ pluginFile ? pluginFile.name : '选择标准 MCP 插件压缩包 (.zip)' }}</span>
          <input type="file" accept=".zip" class="hidden-file-input" @change="handlePluginFileChange" />
        </label>

        <div v-if="inspectingPlugin" class="empty-box">正在校验插件清单与目录结构...</div>
        <MdCard v-else-if="inspectResult" variant="tonal">
          <div class="inspect-summary">
            <div><strong>插件名称:</strong> {{ inspectResult.name }} ({{ inspectResult.service_id }})</div>
            <div><strong>版本 / 维护方:</strong> v{{ inspectResult.version }} · {{ inspectResult.author || '未署名' }}</div>
            <div><strong>声明工具数:</strong> {{ inspectResult.tools?.length || 0 }} 个</div>
            <div v-if="inspectResult.description"><strong>说明:</strong> {{ inspectResult.description }}</div>
          </div>
        </MdCard>
      </div>
      <template #actions>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="publishModalVisible = false">取消</MdButton>
          <MdButton
            variant="filled"
            :disabled="!inspectResult || installingPlugin"
            @click="handleInstallPlugin"
          >
            {{ installingPlugin ? '正在安装启动...' : '确认发布并启动' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- 服务详情抽屉 -->
    <MdDrawer
      v-model="detailDrawerVisible"
      :title="currentService ? `服务详情: ${currentService.name}` : '服务详情'"
      width="740px"
    >
      <div v-if="loadingDetail" class="empty-box">正在加载详情...</div>
      <div v-else-if="currentService" class="detail-body">
        <MdCard variant="tonal">
          <div class="detail-top">
            <div>
              <h3>{{ currentService.name }}</h3>
              <span class="mono sub-id">{{ currentService.id }}</span>
            </div>
            <div class="detail-top-actions">
              <MdButton variant="tonal" @click="openEditMetadata(currentService)">
                <Edit3 :size="14" />
                <span>编辑元数据</span>
              </MdButton>
              <MdButton variant="tonal" @click="handleRefresh(currentService)">
                <RefreshCw :size="14" />
                <span>刷新工具</span>
              </MdButton>
            </div>
          </div>
          <p class="detail-desc">{{ currentService.description || '暂无描述' }}</p>
          <div class="detail-kv-grid">
            <div><span>协议:</span> Streamable HTTP</div>
            <div><span>端点:</span> <span class="mono">{{ currentService.endpoint_url }}</span></div>
            <div><span>版本:</span> v{{ currentService.version || '0.0.0' }}</div>
            <div><span>工具数:</span> {{ serviceTools.length }}</div>
            <div><span>分类:</span> {{ currentService.category || '通用' }}</div>
            <div><span>状态:</span> {{ currentService.status }}</div>
          </div>
          <div class="trust-row">
            <div>
              <strong>允许个人参数透传</strong>
              <p>
                开启后，网关才会将员工在前台加密托管的个人业务参数（如账号/密码/Token）透传给该服务；若服务版本或地址变更，信任状态会自动重置。
              </p>
            </div>
            <MdSwitch
              :model-value="Boolean(currentService.trusted_credential_recipient)"
              @update:model-value="(val) => currentService && handleToggleTrustCredentials(currentService, val)"
            />
          </div>
        </MdCard>

        <div class="tools-sublist">
          <h4>已发现工具契约 ({{ serviceTools.length }})</h4>
          <div v-if="!serviceTools.length" class="empty-box">暂无已发现工具</div>
          <div v-else class="tool-rows">
            <div v-for="t in serviceTools" :key="t.id" class="tool-row">
              <div class="tool-row-main">
                <div class="tool-title">
                  <strong>{{ t.name }}</strong>
                  <span class="tag-pill">{{ t.risk_level }}</span>
                  <span v-if="t.requires_credentials" class="tag-pill">需个人凭据</span>
                </div>
                <p class="tool-desc">{{ t.description || '无描述' }}</p>
              </div>
              <div class="tool-row-actions">
                <MdButton
                  variant="text"
                  @click="
                    () => {
                      schemaTool = t
                      schemaModalVisible = true
                    }
                  "
                >
                  Schema
                </MdButton>
                <MdButton
                  variant="tonal"
                  @click="emit('debug-tool', { serviceId: t.service_id, toolName: t.name })"
                >
                  <PlayCircle :size="14" />
                  <span>调试</span>
                </MdButton>
              </div>
            </div>
          </div>
        </div>
      </div>
    </MdDrawer>

    <!-- 开发规范文档弹窗 -->
    <AdaptiveModal v-model="guideModalVisible" title="MCP 插件开发与发布规范" max-width="760px">
      <div v-if="loadingGuide" class="empty-box">正在加载开发规范文档...</div>
      <pre v-else class="schema-pre"><code>{{ guideContent }}</code></pre>
      <template #actions>
        <div class="modal-footer-actions">
          <MdButton variant="filled" @click="guideModalVisible = false">关闭</MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- 编辑元数据弹窗 -->
    <AdaptiveModal v-model="editModalVisible" title="编辑服务门户元数据" max-width="600px">
      <div class="form-grid">
        <div class="form-row-2">
          <div class="form-item">
            <label class="form-label">显示名称 *</label>
            <input v-model="editForm.name" type="text" class="form-input" />
          </div>
          <div class="form-item">
            <label class="form-label">分类标签</label>
            <input v-model="editForm.category" type="text" class="form-input" />
          </div>
        </div>
        <div class="form-row-2">
          <div class="form-item">
            <label class="form-label">负责人</label>
            <input v-model="editForm.owner" type="text" class="form-input" />
          </div>
          <div class="form-item">
            <label class="form-label">认证标签</label>
            <input v-model="editForm.auth_label" type="text" class="form-input" />
          </div>
        </div>
        <div class="form-item">
          <label class="form-label">服务描述</label>
          <textarea v-model="editForm.description" rows="3" class="form-textarea"></textarea>
        </div>
        <div class="form-item">
          <label class="form-label">推荐提问示例（每行一条）</label>
          <textarea v-model="editForm.examples_text" rows="3" class="form-textarea"></textarea>
        </div>
      </div>
      <template #actions>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="editModalVisible = false">取消</MdButton>
          <MdButton variant="filled" :disabled="savingEdit" @click="handleSaveMetadata">
            {{ savingEdit ? '保存中...' : '保存更新' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- Schema 查看弹窗 -->
    <AdaptiveModal
      v-model="schemaModalVisible"
      :title="`Input Schema: ${schemaTool?.name || ''}`"
      max-width="640px"
    >
      <pre class="schema-pre"><code>{{ JSON.stringify(schemaTool?.input_schema || {}, null, 2) }}</code></pre>
      <template #actions>
        <div class="modal-footer-actions">
          <MdButton variant="filled" @click="schemaModalVisible = false">关闭</MdButton>
        </div>
      </template>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.mcp-servers-tab {
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

.filter-left {
  display: flex;
  align-items: center;
  gap: 12px;
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
  height: 36px;
  width: 240px;
  padding: 0 12px 0 34px;
  border-radius: var(--md-sys-shape-corner-full);
  border: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  outline: none;
}

.status-pills {
  display: flex;
  gap: 6px;
}

.filter-pill {
  padding: 5px 12px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 12px;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.filter-pill.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
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
  font-weight: 600;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
}

.name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sub-id {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.endpoint-text {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  word-break: break-all;
}

.tag-pill,
.status-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface-variant);
}

.status-pill.st-active {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.status-pill.st-degraded {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.empty-box {
  padding: 28px;
  text-align: center;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.form-grid,
.publish-panel,
.detail-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-row-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--md-sys-shape-corner-small);
  border: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  box-sizing: border-box;
}

.guide-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
  font-size: 13px;
}

.guide-banner-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  white-space: nowrap;
}

.upload-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 28px;
  border-radius: var(--md-sys-shape-corner-medium);
  border: 1px dashed var(--md-sys-color-outline);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.hidden-file-input {
  display: none;
}

.inspect-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.detail-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-top h3 {
  margin: 0 0 2px;
}

.detail-top-actions {
  display: flex;
  gap: 8px;
}

.detail-desc {
  margin: 10px 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.detail-kv-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  font-size: 12px;
}

.detail-kv-grid span:first-child {
  color: var(--md-sys-color-on-surface-variant);
}

.trust-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--md-sys-color-outline-variant);
}

.trust-row p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.tools-sublist h4 {
  margin: 0 0 10px;
  font-size: 14px;
}

.tool-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
}

.tool-row-main {
  flex: 1;
  min-width: 0;
}

.tool-row-actions {
  flex-shrink: 0;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.tool-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
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
