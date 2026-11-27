<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  BookOpen,
  Bot,
  CheckCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Code,
  Compass,
  Copy,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  FolderKanban,
  Info,
  Key,
  Layers,
  ListChecks,
  MessageSquare,
  MessageSquarePlus,
  RefreshCw,
  Search,
  SearchX,
  ServerCrash,
  Shield,
  ShieldCheck,
  Sparkles,
  User,
  Wrench,
  X,
  Zap,
} from 'lucide-vue-next'
import AdaptiveModal from '@/components/m3/AdaptiveModal.vue'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import MdDrawer from '@/components/m3/MdDrawer.vue'
import MdSwitch from '@/components/m3/MdSwitch.vue'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { copyToClipboard } from '@/utils/clipboard'
import {
  createPortalPermissionRequest,
  getMcpErrorMessage,
  getPortalCapabilities,
  getPortalCapabilityDetail,
  getPortalMyConfig,
  getPortalMyGrants,
  getPortalMyMcps,
  getPortalMyRequests,
  getPortalOverview,
  isMcpEngineUnavailable,
  togglePortalServiceEnabled,
  unbindPortalServiceBinding,
  updatePortalServiceBinding,
} from '@/api/mcp'
import type {
  PermissionRequest,
  PortalCapabilityCard,
  PortalCapabilityDetail,
  PortalOverview,
  PortalToolItem,
  PortalTrendItem,
  UserClientConfig,
  UserMcpDetail,
} from '@/types/mcp'
import {
  buildPermissionRequestPayload,
  getMyMcpStatusLabel,
  getMyMcpStatusTone,
  isServiceUnavailable,
  selectedToolsRequireCredentials,
  validateCredentialFormForSelectedTools,
} from './mcpStatus'

const toast = useToast()
const authStore = useAuthStore()

// 核心身份直接绑定 RgOne 员工态
const isLoggedIn = computed(() => authStore.isEmployeeLoggedIn)
const currentUserId = computed(() => authStore.empNo || '')
const currentUserName = computed(() => authStore.empName || authStore.empNo || '未登录')

// 引擎可用性（故障隔离，绝不拖垮 RgOne 主站）
const engineUnavailable = ref(false)
const engineErrorMessage = ref('')

// 数据状态
const loadingOverview = ref(true)
const overview = ref<PortalOverview | null>(null)
const loadingCapabilities = ref(true)
const capabilities = ref<PortalCapabilityCard[]>([])

const searchInputRef = ref<HTMLInputElement | null>(null)
const searchKeyword = ref('')
const selectedCategory = ref('全部')
const sortBy = ref<'popular' | 'recent_active' | 'newest'>('popular')

// 一键接入弹窗
const accessModalVisible = ref(false)
const selectedCap = ref<PortalCapabilityCard | null>(null)
const activeAccessTab = ref<'form' | 'json' | 'prompt'>('form')
const pendingAccessCap = ref<PortalCapabilityCard | null | undefined>(undefined)

// 能力详情抽屉
const detailDrawerVisible = ref(false)
const loadingDetail = ref(false)
const currentDetail = ref<PortalCapabilityDetail | null>(null)
const expandedTools = ref<Set<string>>(new Set())

// 员工授权与凭据资产
const userClientConfig = ref<UserClientConfig | null>(null)
const myGrantedToolIds = ref<Set<string>>(new Set())

// 权限申请弹窗
const selectedToolIdsForApply = ref<Set<string>>(new Set())
const applyModalVisible = ref(false)
const applyReason = ref('')
const submittingApply = ref(false)
const applyCredentialForm = ref<Record<string, string>>({})
const showCustomCredInApply = ref(false)

// 申请记录抽屉
const myRequestsDrawerVisible = ref(false)
const myRequests = ref<PermissionRequest[]>([])
const loadingMyRequests = ref(false)

// 我的 MCP 抽屉与改密弹窗
const myMcpsDrawerVisible = ref(false)
const loadingMyMcps = ref(false)
const myMcpsList = ref<UserMcpDetail[]>([])
const editBindingModalVisible = ref(false)
const editingMcpItem = ref<UserMcpDetail | null>(null)
const editBindingForm = ref({ username: '', password: '' })
const submittingEditBinding = ref(false)

// 接入指引弹窗
const guideModalVisible = ref(false)
const togglingServiceIds = ref<Set<string>>(new Set())

let activeAbortController: AbortController | null = null

const pendingRequestsCount = computed(() =>
  myRequests.value.filter((item) => item.status === 'pending').length
)

const currentServiceExistingBinding = computed(() => {
  if (!currentDetail.value || !myMcpsList.value.length) return null
  return (
    myMcpsList.value.find(
      (item) =>
        item.service_id === currentDetail.value?.id &&
        (item.credential_status === 'saved' ||
          item.credential_status === 'verified' ||
          item.credential_status === 'active')
    ) || null
  )
})

const selectedRequiresCredentials = computed(() =>
  selectedToolsRequireCredentials(currentDetail.value, selectedToolIdsForApply.value)
)

const currentGatewayUrl = computed(() => {
  if (userClientConfig.value?.gateway_url) {
    return userClientConfig.value.gateway_url
  }
  if (currentDetail.value?.gateway_url) {
    return currentDetail.value.gateway_url
  }
  return `${window.location.origin}/mcp`
})

const currentGatewayUrlWithToken = computed(() => {
  const base = currentGatewayUrl.value
  if (userClientConfig.value?.token) {
    return `${base}?token=${userClientConfig.value.token}`
  }
  return base
})

const trendList = computed<PortalTrendItem[]>(() => overview.value?.daily_trends || [])

const recent7DaysCallsTotal = computed(() =>
  trendList.value.reduce((acc, curr) => acc + curr.calls, 0)
)

const availableCategories = computed(() => {
  const cats = new Set<string>(['全部'])
  capabilities.value.forEach((cap) => {
    if (cap.category) cats.add(cap.category)
  })
  return Array.from(cats)
})

const filteredCapabilities = computed(() => {
  return capabilities.value.filter((cap) => {
    if (selectedCategory.value !== '全部' && cap.category !== selectedCategory.value) {
      return false
    }
    const kw = searchKeyword.value.trim().toLowerCase()
    if (!kw) return true
    return (
      cap.name.toLowerCase().includes(kw) ||
      (cap.description || '').toLowerCase().includes(kw) ||
      (cap.category || '').toLowerCase().includes(kw)
    )
  })
})

const generatedMcpJson = computed(() => {
  const token = userClientConfig.value?.token || ''
  const serverKey = selectedCap.value ? selectedCap.value.id : 'ai-capability-hub'
  const config = {
    mcpServers: {
      [serverKey]: {
        transport: 'streamable-http',
        url: currentGatewayUrl.value,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      },
    },
  }
  return JSON.stringify(config, null, 2)
})

const generatedNaturalLanguagePrompt = computed(() => {
  const name = selectedCap.value ? selectedCap.value.name : 'AI Capability Hub'
  const desc = selectedCap.value?.description
    ? `主要功能：${selectedCap.value.description}`
    : '提供企业统一业务能力'
  const token = userClientConfig.value?.token
  const authLine = token ? `- 鉴权请求头: Authorization: Bearer ${token}\n` : ''
  const identityDesc =
    isLoggedIn.value && currentUserId.value
      ? `（已绑定工号 ${currentUserId.value} 专属凭证，默认享有 L0 基础公开工具）`
      : '（公共访客模式接入，享有 L0 基础公开工具；可在能力中心登录小秘书工号以开通敏感业务权限）'
  return `请帮我添加并配置以下 MCP 服务：
- 服务名称: ${name}
- 传输协议: Streamable HTTP
- 端点地址: ${currentGatewayUrl.value}
${authLine}- 说明: ${desc} ${identityDesc}
配置完成后请重新加载 MCP 工具列表。`
})

const selectedToolsSummary = computed(() => {
  if (!currentDetail.value) return []
  return currentDetail.value.tools
    .filter((tool) => selectedToolIdsForApply.value.has(getToolKey(tool)))
    .map((tool) => ({
      id: getToolKey(tool),
      name: getToolBusinessTitle(tool),
      techName: tool.name,
      risk: tool.risk_level,
    }))
})

const selectableToolsCount = computed(() => {
  if (!currentDetail.value) return 0
  return currentDetail.value.tools.filter((tool) => isToolSelectable(tool)).length
})

const allSelectableSelected = computed(() => {
  if (!currentDetail.value) return false
  const selectable = currentDetail.value.tools.filter((tool) => isToolSelectable(tool))
  return (
    selectable.length > 0 &&
    selectable.every((tool) => selectedToolIdsForApply.value.has(getToolKey(tool)))
  )
})

function openEmployeeLogin() {
  window.dispatchEvent(
    new CustomEvent('rgone:open-login', {
      detail: { mode: 'employee' },
    })
  )
}

function handleAccessClick(cap?: PortalCapabilityCard) {
  if (!isLoggedIn.value) {
    pendingAccessCap.value = cap ?? null
    toast.info('请先使用小秘书工号登录，以便为您自动签发专属 MCP 鉴权 Token')
    openEmployeeLogin()
    return
  }
  if (cap) {
    openAccessModal(cap)
  } else {
    openGlobalAccessModal()
  }
}

function openGlobalAccessModal() {
  selectedCap.value = null
  activeAccessTab.value = 'form'
  accessModalVisible.value = true
}

function openAccessModal(cap: PortalCapabilityCard) {
  selectedCap.value = cap
  activeAccessTab.value = 'form'
  accessModalVisible.value = true
}

function getCategoryIcon(cat?: string) {
  if (!cat) return Bot
  if (cat.includes('知识') || cat.includes('文档')) return FileText
  if (cat.includes('数据') || cat.includes('分析')) return BarChart3
  if (cat.includes('业务') || cat.includes('协作')) return FolderKanban
  return Bot
}

function calculateBarHeight(calls: number): number {
  if (!recent7DaysCallsTotal.value) return 6
  const max = Math.max(...trendList.value.map((item) => item.calls), 1)
  return Math.max(Math.round((calls / max) * 100), 8)
}

function formatDayShort(dateStr: string): string {
  if (!dateStr) return '-'
  const parts = dateStr.split('-')
  return parts.length >= 3 ? `${parts[1]}/${parts[2]}` : dateStr
}

function getToolKey(tool: PortalToolItem): string {
  return tool.id || tool.namespace_name || tool.name
}

function isToolL0(tool: PortalToolItem): boolean {
  return (tool.risk_level || '').toUpperCase() === 'L0'
}

function isToolGranted(tool: PortalToolItem): boolean {
  if (isToolL0(tool)) return true
  const tid = getToolKey(tool)
  return (
    myGrantedToolIds.value.has(tid) ||
    myGrantedToolIds.value.has(tool.name) ||
    myGrantedToolIds.value.has(tool.namespace_name)
  )
}

function isToolSelectable(tool: PortalToolItem): boolean {
  return !isToolL0(tool) && !isToolGranted(tool)
}

function getToolBusinessTitle(tool: PortalToolItem): string {
  const rawName = tool.name || tool.namespace_name || ''
  const cleanName = rawName.includes('__') ? rawName.split('__')[1] || rawName : rawName
  const knownMap: Record<string, string> = {
    send_notification: '发送消息通知',
    list_pending: '查询待办消息列表',
    portfolio_summary: '投资组合汇总分析',
    market_quotes: '实时市场行情查询',
    risk_assessment: '资产风险合规评估',
    document_export: '业务文档格式导出',
    search_docs: '业务知识文档检索',
    export_pdf: '导出为 PDF 报告',
    export_excel: '导出为 Excel 表格',
  }
  if (knownMap[cleanName]) return knownMap[cleanName]

  const desc = (tool.description || '').trim()
  if (desc) {
    const firstSentence = desc.split(/[。；;\n]/)[0]?.trim() || ''
    if (firstSentence && firstSentence.length <= 18) return firstSentence
    if (desc.length <= 22) return desc
    return `${desc.slice(0, 16)}...`
  }

  const words = cleanName.split(/[_-]/).filter(Boolean)
  if (words.length > 0) {
    return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  }
  return rawName || '未知功能'
}

function getToolBusinessDesc(tool: PortalToolItem): string {
  const title = getToolBusinessTitle(tool)
  const desc = (tool.description || '').trim()
  if (desc && desc !== title) return desc
  return isToolL0(tool)
    ? '基础只读功能，连接本服务后在 AI 客户端中输入自然语言即可直接调用。'
    : '涉及业务写入或敏感数据，需勾选申请开通后方可在 AI 对话中启用。'
}

function toggleToolSelection(tool: PortalToolItem) {
  const tid = getToolKey(tool)
  const next = new Set(selectedToolIdsForApply.value)
  if (next.has(tid)) {
    next.delete(tid)
  } else {
    next.add(tid)
  }
  selectedToolIdsForApply.value = next
}

function toggleSelectAllNonL0() {
  if (!currentDetail.value) return
  const selectable = currentDetail.value.tools.filter((tool) => isToolSelectable(tool))
  const next = new Set(selectedToolIdsForApply.value)
  if (allSelectableSelected.value) {
    selectable.forEach((tool) => next.delete(getToolKey(tool)))
  } else {
    selectable.forEach((tool) => next.add(getToolKey(tool)))
  }
  selectedToolIdsForApply.value = next
}

function toggleToolSchema(toolName: string) {
  const next = new Set(expandedTools.value)
  if (next.has(toolName)) {
    next.delete(toolName)
  } else {
    next.add(toolName)
  }
  expandedTools.value = next
}

function resetSignal(): AbortSignal {
  if (activeAbortController) {
    activeAbortController.abort()
  }
  activeAbortController = new AbortController()
  return activeAbortController.signal
}

function markEngineError(err: unknown) {
  if (isMcpEngineUnavailable(err)) {
    engineUnavailable.value = true
    engineErrorMessage.value = getMcpErrorMessage(err, '能力引擎暂不可用')
  }
}

async function loadOverview(signal?: AbortSignal) {
  loadingOverview.value = true
  try {
    overview.value = await getPortalOverview(signal)
    engineUnavailable.value = false
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    markEngineError(err)
  } finally {
    loadingOverview.value = false
  }
}

async function loadCapabilities(signal?: AbortSignal) {
  loadingCapabilities.value = true
  try {
    capabilities.value = await getPortalCapabilities(
      {
        category: selectedCategory.value !== '全部' ? selectedCategory.value : undefined,
        sort_by: sortBy.value,
      },
      signal
    )
    engineUnavailable.value = false
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    markEngineError(err)
  } finally {
    loadingCapabilities.value = false
  }
}

async function loadMyMcps(signal?: AbortSignal) {
  if (!isLoggedIn.value) {
    myMcpsList.value = []
    return
  }
  loadingMyMcps.value = true
  try {
    myMcpsList.value = await getPortalMyMcps(true, signal)
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    markEngineError(err)
  } finally {
    loadingMyMcps.value = false
  }
}

async function loadUserConfigAndGrants(signal?: AbortSignal) {
  if (!isLoggedIn.value || !currentUserId.value) {
    userClientConfig.value = null
    myGrantedToolIds.value = new Set()
    myRequests.value = []
    myMcpsList.value = []
    return
  }
  try {
    const [cfg, grants, reqs] = await Promise.all([
      getPortalMyConfig(currentUserId.value, signal),
      getPortalMyGrants(currentUserId.value, signal),
      getPortalMyRequests(currentUserId.value, signal).catch(() => []),
      loadMyMcps(signal).catch(() => []),
    ])
    userClientConfig.value = cfg
    myGrantedToolIds.value = new Set(grants.granted_tool_ids || [])
    myRequests.value = Array.isArray(reqs) ? reqs : []
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    markEngineError(err)
  }
}

async function reloadAll() {
  const signal = resetSignal()
  engineUnavailable.value = false
  engineErrorMessage.value = ''
  await Promise.all([
    loadOverview(signal),
    loadCapabilities(signal),
    loadUserConfigAndGrants(signal),
  ])
}

function selectCategory(cat: string) {
  selectedCategory.value = cat
}

function changeSort(sort: 'popular' | 'recent_active' | 'newest') {
  sortBy.value = sort
  void loadCapabilities()
}

function resetFilters() {
  searchKeyword.value = ''
  selectedCategory.value = '全部'
  sortBy.value = 'popular'
  void loadCapabilities()
}

async function openDetailDrawer(id: string) {
  detailDrawerVisible.value = true
  loadingDetail.value = true
  expandedTools.value = new Set()
  selectedToolIdsForApply.value = new Set()
  applyCredentialForm.value = {}
  showCustomCredInApply.value = false
  try {
    currentDetail.value = await getPortalCapabilityDetail(id)
    if (isLoggedIn.value) {
      await loadUserConfigAndGrants()
    }
  } catch (err: unknown) {
    detailDrawerVisible.value = false
    if (isMcpEngineUnavailable(err)) {
      markEngineError(err)
      toast.error(getMcpErrorMessage(err, '能力引擎暂不可用'))
    } else {
      toast.error(getMcpErrorMessage(err, '获取能力详情失败'))
    }
  } finally {
    loadingDetail.value = false
  }
}

function openApplyModal() {
  if (!isLoggedIn.value) {
    toast.info('提交功能权限申请需先登录小秘书工号')
    openEmployeeLogin()
    return
  }
  if (selectedToolIdsForApply.value.size === 0) {
    toast.warning('请先勾选需要申请开通的功能')
    return
  }
  applyReason.value = ''
  applyCredentialForm.value = {}
  showCustomCredInApply.value = false
  applyModalVisible.value = true
}

async function submitPermissionApplication() {
  if (!currentDetail.value) return
  if (!applyReason.value.trim()) {
    toast.warning('请填写业务申请说明')
    return
  }
  const hasExisting = Boolean(currentServiceExistingBinding.value)
  const credCheck = validateCredentialFormForSelectedTools(
    currentDetail.value,
    selectedToolIdsForApply.value,
    hasExisting,
    showCustomCredInApply.value,
    applyCredentialForm.value
  )
  if (!credCheck.valid) {
    toast.warning(`请填写必填业务凭据: ${credCheck.missingFieldLabel}`)
    return
  }

  const payload = buildPermissionRequestPayload({
    userId: currentUserId.value,
    userName: currentUserName.value,
    detail: currentDetail.value,
    selectedToolIds: selectedToolIdsForApply.value,
    reason: applyReason.value,
    hasExistingBinding: hasExisting,
    showCustomCredInApply: showCustomCredInApply.value,
    credentialForm: applyCredentialForm.value,
  })

  submittingApply.value = true
  try {
    await createPortalPermissionRequest(payload)
    toast.success('权限申请已提交，待管理员审批通过后即可使用')
    applyModalVisible.value = false
    selectedToolIdsForApply.value = new Set()
    applyCredentialForm.value = {}
    showCustomCredInApply.value = false
    await loadUserConfigAndGrants()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '提交申请失败，请稍后重试'))
  } finally {
    submittingApply.value = false
  }
}

function handleMenuMyMcps() {
  if (!isLoggedIn.value) {
    openEmployeeLogin()
    return
  }
  myMcpsDrawerVisible.value = true
  void loadMyMcps()
}

function handleMenuMyRequests() {
  if (!isLoggedIn.value) {
    openEmployeeLogin()
    return
  }
  myRequestsDrawerVisible.value = true
  void loadMyRequests()
}

async function loadMyRequests() {
  loadingMyRequests.value = true
  try {
    myRequests.value = await getPortalMyRequests(currentUserId.value)
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '加载申请历史失败'))
  } finally {
    loadingMyRequests.value = false
  }
}

function openEditBindingDialog(item: UserMcpDetail) {
  editingMcpItem.value = item
  editBindingForm.value = {
    username: item.credential_summary?.username || '',
    password: '',
  }
  editBindingModalVisible.value = true
}

async function submitEditBinding() {
  if (!editingMcpItem.value) return
  if (!editBindingForm.value.username.trim()) {
    toast.warning('请输入业务用户名')
    return
  }
  submittingEditBinding.value = true
  try {
    const payload: Record<string, string> = {
      username: editBindingForm.value.username.trim(),
    }
    if (editBindingForm.value.password) {
      payload.password = editBindingForm.value.password
    }
    await updatePortalServiceBinding(editingMcpItem.value.service_id, payload)
    toast.success('业务凭据已更新，原会话已失效')
    editBindingModalVisible.value = false
    await loadMyMcps()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '保存凭据失败，请重试'))
  } finally {
    submittingEditBinding.value = false
  }
}

async function handleUnbindService(item: UserMcpDetail) {
  if (
    !window.confirm(
      `确定要解绑 ${item.service_name} 的个人业务凭据吗？解绑后将立即阻断后续需要此绑定的工具调用。`
    )
  ) {
    return
  }
  try {
    await unbindPortalServiceBinding(item.service_id)
    toast.success(`已解绑 ${item.service_name} 的业务凭据`)
    await loadMyMcps()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '解绑失败，请重试'))
  }
}

function openAccessModalFromDetail() {
  if (!currentDetail.value) return
  const cap: PortalCapabilityCard = {
    id: currentDetail.value.id,
    name: currentDetail.value.name,
    description: currentDetail.value.description,
    category: currentDetail.value.category,
    tools_count: currentDetail.value.tools.length,
    status: currentDetail.value.status,
    auth_mode: currentDetail.value.auth_mode,
    auth_label: currentDetail.value.auth_label,
    auth_guide: currentDetail.value.auth_guide,
    auth_entry_url: currentDetail.value.auth_entry_url,
    call_count: currentDetail.value.total_calls,
    recent_calls_7d: currentDetail.value.recent_calls_7d,
    last_active_at: currentDetail.value.last_active_at,
    created_at: currentDetail.value.created_at,
  }
  detailDrawerVisible.value = false
  handleAccessClick(cap)
}

async function handleToggleServiceEnabled(serviceId: string, enabled: boolean) {
  if (!isLoggedIn.value) {
    toast.info('调整个人 MCP 装配开关需先登录小秘书工号')
    openEmployeeLogin()
    return
  }
  const nextBusy = new Set(togglingServiceIds.value)
  nextBusy.add(serviceId)
  togglingServiceIds.value = nextBusy
  try {
    const res = await togglePortalServiceEnabled(serviceId, enabled)
    const cap = capabilities.value.find((item) => item.id === serviceId)
    if (cap) cap.user_enabled = res.user_enabled
    const myItem = myMcpsList.value.find((item) => item.service_id === serviceId)
    if (myItem) myItem.user_enabled = res.user_enabled
    toast.success(
      res.user_enabled
        ? '已为当前账号开启该 MCP 服务装配'
        : '已为当前账号关闭该 MCP 服务装配（重启/刷新工具生效）'
    )
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '更新装配开关失败'))
  } finally {
    const doneBusy = new Set(togglingServiceIds.value)
    doneBusy.delete(serviceId)
    togglingServiceIds.value = doneBusy
  }
}

async function copyText(text: string, label = '内容') {
  const ok = await copyToClipboard(text)
  if (ok) {
    toast.success(`${label}已复制到剪贴板`)
  } else {
    toast.error('复制失败，请手动选择复制')
  }
}

function handlePrimaryCopy() {
  if (activeAccessTab.value === 'form') {
    void copyText(currentGatewayUrlWithToken.value, '统一 MCP 服务地址')
  } else if (activeAccessTab.value === 'json') {
    void copyText(generatedMcpJson.value, '标准 JSON 配置')
  } else {
    void copyText(generatedNaturalLanguagePrompt.value, '自然语言接入指令')
  }
}

function handleAuthAction() {
  if (selectedCap.value?.auth_entry_url) {
    window.open(selectedCap.value.auth_entry_url, '_blank', 'noopener,noreferrer')
  } else {
    toast.info('当前服务已接入平台统一认证托管，在 AI 助手首次发起调用时将自动完成校验。')
  }
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  }
}

watch(
  () => [authStore.empToken, authStore.empNo],
  async () => {
    await loadUserConfigAndGrants()
    if (isLoggedIn.value && pendingAccessCap.value !== undefined) {
      const target = pendingAccessCap.value
      pendingAccessCap.value = undefined
      if (target) {
        openAccessModal(target)
      } else {
        openGlobalAccessModal()
      }
    }
  }
)

onMounted(() => {
  void reloadAll()
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  if (activeAbortController) {
    activeAbortController.abort()
    activeAbortController = null
  }
})
</script>

<template>
  <div class="capabilities-page">
    <!-- 顶部操作工具栏 -->
    <div class="portal-toolbar">
      <div class="toolbar-search">
        <Search :size="16" class="search-icon" />
        <input
          ref="searchInputRef"
          v-model="searchKeyword"
          type="text"
          placeholder="搜业务场景、能力服务或工具... (Ctrl+K)"
          class="search-input"
        />
        <button
          v-if="searchKeyword"
          type="button"
          class="search-clear-btn"
          title="清空搜索"
          @click="searchKeyword = ''"
        >
          <X :size="14" />
        </button>
      </div>

      <div class="toolbar-actions">
        <MdButton variant="filled" @click="handleAccessClick()">
          <Zap :size="15" />
          <span>一键接入</span>
        </MdButton>
        <template v-if="isLoggedIn">
          <MdButton variant="tonal" @click="handleMenuMyMcps">
            <Layers :size="15" />
            <span>我的 MCP</span>
            <span v-if="myMcpsList.length > 0" class="count-pill">{{ myMcpsList.length }}</span>
          </MdButton>
          <MdButton variant="tonal" @click="handleMenuMyRequests">
            <ListChecks :size="15" />
            <span>申请记录</span>
            <span v-if="pendingRequestsCount > 0" class="count-pill">{{
              pendingRequestsCount
            }}</span>
          </MdButton>
        </template>
        <MdButton v-else variant="tonal" @click="openEmployeeLogin">
          <User :size="15" />
          <span>小秘书登录</span>
        </MdButton>
        <MdButton variant="text" @click="guideModalVisible = true">
          <BookOpen :size="15" />
          <span>接入指引</span>
        </MdButton>
      </div>
    </div>

    <!-- 故障隔离兜底卡片：当 hub-core 未启动或网关不可达时优雅降级 -->
    <MdCard v-if="engineUnavailable" variant="elevated" class="engine-down-card">
      <div class="engine-down-content">
        <div class="engine-down-icon">
          <ServerCrash :size="28" />
        </div>
        <div class="engine-down-text">
          <h2>MCP 能力引擎暂不可用</h2>
          <p>
            {{ engineErrorMessage || '无法连接下游能力引擎（hub-core），已隔离异常，RgOne 主站其他功能不受影响。' }}
          </p>
        </div>
        <MdButton variant="tonal" @click="reloadAll">
          <RefreshCw :size="15" />
          <span>重新连接</span>
        </MdButton>
      </div>
    </MdCard>

    <template v-else>
      <!-- Hero 与真实活跃度指标条 -->
      <MdCard variant="tonal" class="portal-hero-card">
        <div class="hero-header">
          <div class="hero-badge">
            <Sparkles :size="14" />
            <span>企业级 AI 能力自助消费中心</span>
          </div>
          <h1 class="hero-title">发现企业 AI 能力，一键赋能本地智能助手</h1>
          <p class="hero-desc">
            免登录浏览与检索，一键复制标准 Streamable HTTP 接入配置；高风险或需个人凭据的业务工具通过企业小秘书工号统一鉴权。
          </p>
        </div>

        <div class="stats-row">
          <MdCard variant="elevated" class="stat-card">
            <div class="stat-inner">
              <div class="stat-icon-wrapper tone-primary">
                <Layers :size="20" />
              </div>
              <div class="stat-content">
                <span class="stat-value">{{ loadingOverview ? '—' : overview?.services_count ?? '-' }}</span>
                <span class="stat-label">已上线业务服务</span>
              </div>
            </div>
          </MdCard>

          <MdCard variant="elevated" class="stat-card">
            <div class="stat-inner">
              <div class="stat-icon-wrapper tone-secondary">
                <Wrench :size="20" />
              </div>
              <div class="stat-content">
                <span class="stat-value">{{ loadingOverview ? '—' : overview?.tools_count ?? '-' }}</span>
                <span class="stat-label">可用能力工具</span>
              </div>
            </div>
          </MdCard>

          <MdCard variant="elevated" class="stat-card">
            <div class="stat-inner">
              <div class="stat-icon-wrapper tone-success">
                <Activity :size="20" />
              </div>
              <div class="stat-content">
                <span class="stat-value">{{ loadingOverview ? '—' : overview?.total_calls ?? 0 }}</span>
                <span class="stat-label">平台累计真实调用</span>
              </div>
            </div>
          </MdCard>

          <MdCard variant="elevated" class="stat-card trend-stat-card">
            <div class="trend-header">
              <span class="stat-label">近 7 日活跃趋势</span>
              <span class="trend-total">
                {{ recent7DaysCallsTotal > 0 ? `7日: ${recent7DaysCallsTotal}次` : '暂无近7日调用' }}
              </span>
            </div>
            <div class="mini-trend-bar-chart">
              <div
                v-for="(item, idx) in trendList"
                :key="idx"
                class="mini-bar-col"
                :title="`${item.date}: 调用 ${item.calls} 次`"
              >
                <div class="mini-bar-track">
                  <div
                    class="mini-bar-fill"
                    :style="{ height: `${calculateBarHeight(item.calls)}%` }"
                  ></div>
                </div>
                <span class="mini-bar-day">{{ formatDayShort(item.date) }}</span>
              </div>
            </div>
          </MdCard>
        </div>
      </MdCard>

      <!-- 筛选栏 -->
      <div class="discovery-filter-bar">
        <div class="category-tabs">
          <button
            v-for="cat in availableCategories"
            :key="cat"
            type="button"
            :class="['category-tab-btn', { 'is-active': selectedCategory === cat }]"
            @click="selectCategory(cat)"
          >
            {{ cat }}
          </button>
        </div>

        <div class="sort-selector">
          <span class="sort-label">排序:</span>
          <div class="sort-options">
            <button
              type="button"
              :class="['sort-opt-btn', { 'is-active': sortBy === 'popular' }]"
              @click="changeSort('popular')"
            >
              最受欢迎
            </button>
            <button
              type="button"
              :class="['sort-opt-btn', { 'is-active': sortBy === 'recent_active' }]"
              @click="changeSort('recent_active')"
            >
              最近活跃
            </button>
            <button
              type="button"
              :class="['sort-opt-btn', { 'is-active': sortBy === 'newest' }]"
              @click="changeSort('newest')"
            >
              最新上线
            </button>
          </div>
        </div>
      </div>

      <!-- 能力列表 -->
      <div v-if="loadingCapabilities" class="cards-skeleton-grid">
        <MdCard v-for="i in 6" :key="i" variant="elevated" class="skeleton-card">
          <div class="skeleton-line short"></div>
          <div class="skeleton-line long"></div>
          <div class="skeleton-line medium"></div>
        </MdCard>
      </div>

      <MdCard
        v-else-if="filteredCapabilities.length === 0"
        variant="filled"
        class="empty-portal-state"
      >
        <div class="empty-inner">
          <SearchX :size="36" />
          <h3>未找到符合条件的能力服务</h3>
          <p>
            {{
              searchKeyword
                ? `没有与「${searchKeyword}」匹配的结果，请尝试更换关键词`
                : '当前分类下暂无已发布能力'
            }}
          </p>
          <MdButton
            v-if="searchKeyword || selectedCategory !== '全部'"
            variant="tonal"
            @click="resetFilters"
          >
            重置筛选条件
          </MdButton>
        </div>
      </MdCard>

      <div v-else class="capabilities-grid">
        <MdCard
          v-for="cap in filteredCapabilities"
          :key="cap.id"
          variant="elevated"
          class="cap-card"
        >
          <div class="cap-card__header">
            <div class="cap-card__avatar">
              <component :is="getCategoryIcon(cap.category)" :size="22" />
            </div>
            <div class="cap-card__title-area">
              <div class="cap-card__name-row">
                <h3 class="cap-name" :title="cap.name">{{ cap.name }}</h3>
                <span
                  class="status-indicator"
                  :class="cap.status === 'active' ? 'is-active' : 'is-degraded'"
                  :title="cap.status === 'active' ? '服务运行正常' : '服务可能降级'"
                ></span>
              </div>
              <div class="cap-card__tags">
                <span class="category-pill">{{ cap.category || '通用' }}</span>
                <span class="auth-pill" :title="cap.auth_label">
                  <Shield :size="12" />
                  <span>{{ cap.auth_label || 'Hub 统一认证' }}</span>
                </span>
              </div>
            </div>
          </div>

          <p class="cap-card__desc" :title="cap.description || '暂无业务描述'">
            {{ cap.description || '为本地智能助手提供高可用、标准化的业务能力集成接口。' }}
          </p>

          <div class="cap-card__metrics">
            <div class="metric-item">
              <Wrench :size="14" />
              <span>包含 <strong>{{ cap.tools_count }}</strong> 个工具</span>
            </div>
            <div class="metric-item">
              <Activity :size="14" />
              <span v-if="cap.call_count > 0">累计调用 <strong>{{ cap.call_count }}</strong> 次</span>
              <span v-else>新上线</span>
            </div>
          </div>

          <div class="cap-assembly-row">
            <span class="assembly-label">
              个人装配开关：{{ cap.user_enabled !== false ? '已启用' : '已停用' }}
            </span>
            <MdSwitch
              :model-value="cap.user_enabled !== false"
              :disabled="togglingServiceIds.has(cap.id)"
              @update:model-value="(val) => handleToggleServiceEnabled(cap.id, val)"
            />
          </div>

          <div class="cap-card__footer">
            <MdButton variant="tonal" @click="openDetailDrawer(cap.id)">
              <span>查看详情</span>
              <ArrowRight :size="14" />
            </MdButton>
            <MdButton variant="filled" @click="handleAccessClick(cap)">
              <Zap :size="14" />
              <span>一键接入</span>
            </MdButton>
          </div>
        </MdCard>
      </div>
    </template>

    <!-- 1. 一键接入弹窗 -->
    <AdaptiveModal
      v-model="accessModalVisible"
      :title="selectedCap ? `接入能力: ${selectedCap.name}` : '一键接入企业 AI 能力'"
      max-width="860px"
    >
      <div class="access-panel">
        <div class="aggregation-banner">
          <Info :size="18" class="banner-icon" />
          <div class="banner-content">
            <p class="banner-title">平台聚合统一端点提示</p>
            <p class="banner-text">
              只需在您的本地或网页端 AI 客户端（Cherry Studio、Claude Desktop、Cursor 等）中添加一次平台接入地址，即可消费全部已获批能力。
            </p>
          </div>
        </div>

        <div v-if="isLoggedIn && currentUserId" class="user-binding-banner is-logged-in">
          <CheckCircle :size="16" />
          <span>
            已绑定当前登录工号: <strong>{{ currentUserName }} ({{ currentUserId }})</strong> · 专属 Token 已写入配置
          </span>
        </div>
        <div v-else class="user-binding-banner is-guest">
          <AlertCircle :size="16" />
          <span>当前为未登录状态，仅享有公开 L0 工具；请登录小秘书工号获取完整授权。</span>
          <MdButton variant="text" @click="openEmployeeLogin">立即登录</MdButton>
        </div>

        <div class="access-tabs">
          <button
            type="button"
            :class="['access-tab-btn', { 'is-active': activeAccessTab === 'form' }]"
            @click="activeAccessTab = 'form'"
          >
            <FileSpreadsheet :size="15" />
            <span>表单参数 (网页端)</span>
          </button>
          <button
            type="button"
            :class="['access-tab-btn', { 'is-active': activeAccessTab === 'json' }]"
            @click="activeAccessTab = 'json'"
          >
            <Code :size="15" />
            <span>标准 JSON (桌面端)</span>
          </button>
          <button
            type="button"
            :class="['access-tab-btn', { 'is-active': activeAccessTab === 'prompt' }]"
            @click="activeAccessTab = 'prompt'"
          >
            <MessageSquarePlus :size="15" />
            <span>自然语言指令 (AI 助手)</span>
          </button>
        </div>

        <div v-if="activeAccessTab === 'form'" class="tab-pane">
          <div class="field-copy-group">
            <div class="field-row">
              <span class="field-title">服务名称 (Server Name)</span>
              <div class="field-box">
                <span class="field-val mono">{{
                  selectedCap ? selectedCap.name : 'AI Capability Hub'
                }}</span>
                <MdButton
                  variant="text"
                  @click="copyText(selectedCap ? selectedCap.name : 'AI Capability Hub', '服务名称')"
                >
                  <Copy :size="14" />
                  <span>复制</span>
                </MdButton>
              </div>
            </div>
            <div class="field-row">
              <span class="field-title">传输协议 (Transport)</span>
              <div class="field-box">
                <span class="field-val mono">Streamable HTTP (MCP)</span>
                <MdButton variant="text" @click="copyText('Streamable HTTP', '传输协议')">
                  <Copy :size="14" />
                  <span>复制</span>
                </MdButton>
              </div>
            </div>
            <div class="field-row">
              <span class="field-title">服务接入地址 (Endpoint URL)</span>
              <div class="field-box highlight-box">
                <span class="field-val mono break-all">{{ currentGatewayUrl }}</span>
                <MdButton
                  variant="tonal"
                  @click="copyText(currentGatewayUrl, '服务接入地址')"
                >
                  <Copy :size="14" />
                  <span>复制地址</span>
                </MdButton>
              </div>
            </div>
            <div v-if="userClientConfig?.token" class="field-row">
              <span class="field-title">个人长效 Token (Authorization Bearer)</span>
              <div class="field-box">
                <span class="field-val mono break-all">{{ userClientConfig.token }}</span>
                <MdButton
                  variant="tonal"
                  @click="copyText(`Bearer ${userClientConfig.token}`, 'Bearer Token')"
                >
                  <Copy :size="14" />
                  <span>复制 Bearer</span>
                </MdButton>
              </div>
            </div>
          </div>
        </div>

        <div v-else-if="activeAccessTab === 'json'" class="tab-pane">
          <div class="code-block-header">
            <span>mcpServers 配置片段</span>
            <MdButton variant="tonal" @click="copyText(generatedMcpJson, 'JSON 配置')">
              <Copy :size="14" />
              <span>复制 JSON</span>
            </MdButton>
          </div>
          <pre class="code-preview"><code>{{ generatedMcpJson }}</code></pre>
        </div>

        <div v-else class="tab-pane">
          <div class="code-block-header">
            <span>发送给具备 MCP 配置能力的 AI 助手</span>
            <MdButton
              variant="tonal"
              @click="copyText(generatedNaturalLanguagePrompt, '自然语言指令')"
            >
              <Copy :size="14" />
              <span>复制指令</span>
            </MdButton>
          </div>
          <div class="natural-prompt-box">{{ generatedNaturalLanguagePrompt }}</div>
        </div>

        <div class="auth-notice-card">
          <div class="auth-notice-left">
            <ShieldCheck :size="20" />
            <div>
              <div class="auth-notice-title">
                企业平台统一安全认证托管 · {{ selectedCap?.auth_label || 'Hub 统一认证' }}
              </div>
              <p class="auth-notice-desc">
                {{
                  selectedCap?.auth_guide ||
                  '接入后，所有高风险工具权限审批与个人下游账号凭据由企业能力引擎统一加密托管。'
                }}
              </p>
            </div>
          </div>
          <MdButton variant="text" @click="handleAuthAction">
            <ExternalLink :size="14" />
            <span>{{ selectedCap?.auth_entry_url ? '前往统一认证' : '授权说明' }}</span>
          </MdButton>
        </div>
      </div>

      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="accessModalVisible = false">关闭</MdButton>
          <MdButton variant="filled" @click="handlePrimaryCopy">
            <Copy :size="15" />
            <span>一键复制当前配置</span>
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- 2. 能力完整详情抽屉 -->
    <MdDrawer
      v-model="detailDrawerVisible"
      :title="currentDetail?.name || '能力详情'"
      width="740px"
    >
      <div v-if="loadingDetail" class="detail-loading-box">
        <RefreshCw :size="24" class="is-spinning" />
        <span>正在加载能力详情与工具契约...</span>
      </div>

      <div v-else-if="currentDetail" class="detail-drawer-body">
        <MdCard variant="tonal" class="detail-hero-card">
          <div class="detail-title-row">
            <div class="detail-avatar">
              <component :is="getCategoryIcon(currentDetail.category)" :size="24" />
            </div>
            <div>
              <h2 class="detail-title">{{ currentDetail.name }}</h2>
              <div class="detail-tags-row">
                <span class="category-pill">{{ currentDetail.category }}</span>
                <span class="auth-pill">
                  <Shield :size="12" />
                  <span>{{ currentDetail.auth_label }}</span>
                </span>
                <span class="version-pill">v{{ currentDetail.version }}</span>
              </div>
            </div>
          </div>
          <p class="detail-desc">{{ currentDetail.description || '暂无业务描述' }}</p>

          <div class="detail-stats-grid">
            <div class="detail-stat-box">
              <span class="stat-num">{{ currentDetail.total_calls }}</span>
              <span class="stat-sub">累计调用量</span>
            </div>
            <div class="detail-stat-box">
              <span class="stat-num">{{ currentDetail.recent_calls_7d }}</span>
              <span class="stat-sub">近 7 日调用</span>
            </div>
            <div class="detail-stat-box">
              <span class="stat-num">{{ currentDetail.tools.length }}</span>
              <span class="stat-sub">包含可用工具</span>
            </div>
          </div>
        </MdCard>

        <div class="usage-guide-section">
          <h3 class="section-title">
            <Compass :size="17" />
            <span>三步极简接入指南</span>
          </h3>
          <div class="three-steps">
            <div class="step-card">
              <div class="step-num">1</div>
              <div class="step-body">
                <span class="step-title">一键复制配置</span>
                <span class="step-text">复制统一网关地址或标准 JSON</span>
              </div>
            </div>
            <div class="step-card">
              <div class="step-num">2</div>
              <div class="step-body">
                <span class="step-title">粘贴至 AI 助手</span>
                <span class="step-text">导入 Cursor / Cherry Studio 等客户端</span>
              </div>
            </div>
            <div class="step-card">
              <div class="step-num">3</div>
              <div class="step-body">
                <span class="step-title">按需开通高敏工具</span>
                <span class="step-text">L0 公开即用，高敏工具勾选提交审批</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="currentDetail.usage_examples?.length" class="examples-section">
          <h3 class="section-title">
            <MessageSquare :size="17" />
            <span>推荐提问方式与适用场景</span>
          </h3>
          <div class="examples-list">
            <div
              v-for="(example, eIdx) in currentDetail.usage_examples"
              :key="eIdx"
              class="example-pill-item"
            >
              <span>{{ example }}</span>
              <MdButton variant="text" @click="copyText(example, '示例提问')">
                <Copy :size="13" />
              </MdButton>
            </div>
          </div>
        </div>

        <!-- 工具列表与权限申请勾选 -->
        <div class="tools-section">
          <div class="tools-header">
            <h3 class="section-title">
              <Wrench :size="17" />
              <span>包含业务工具 ({{ currentDetail.tools.length }})</span>
            </h3>
            <div v-if="selectableToolsCount > 0" class="tools-header-actions">
              <MdButton variant="text" @click="toggleSelectAllNonL0">
                {{ allSelectableSelected ? '取消全选' : `全选待开通 (${selectableToolsCount})` }}
              </MdButton>
              <MdButton
                variant="filled"
                :disabled="selectedToolIdsForApply.size === 0"
                @click="openApplyModal"
              >
                申请开通所选 ({{ selectedToolIdsForApply.size }})
              </MdButton>
            </div>
          </div>

          <div class="tools-list">
            <div v-for="tool in currentDetail.tools" :key="getToolKey(tool)" class="tool-item-card">
              <div class="tool-item-main">
                <input
                  v-if="isToolSelectable(tool)"
                  type="checkbox"
                  :checked="selectedToolIdsForApply.has(getToolKey(tool))"
                  class="tool-checkbox"
                  @change="toggleToolSelection(tool)"
                />
                <div class="tool-item-body">
                  <div class="tool-item-title-row">
                    <span class="tool-biz-title">{{ getToolBusinessTitle(tool) }}</span>
                    <span class="tool-tech-name mono">{{ tool.name }}</span>
                    <span class="risk-badge" :class="`risk-${(tool.risk_level || 'L0').toLowerCase()}`">
                      {{ tool.risk_level || 'L0' }}
                    </span>
                    <span v-if="isToolGranted(tool)" class="granted-badge">
                      {{ isToolL0(tool) ? '公开可用' : '已获授权' }}
                    </span>
                  </div>
                  <p class="tool-biz-desc">{{ getToolBusinessDesc(tool) }}</p>
                </div>
                <button
                  type="button"
                  class="schema-toggle-btn"
                  @click="toggleToolSchema(getToolKey(tool))"
                >
                  <span>参数</span>
                  <ChevronUp v-if="expandedTools.has(getToolKey(tool))" :size="14" />
                  <ChevronDown v-else :size="14" />
                </button>
              </div>
              <pre
                v-if="expandedTools.has(getToolKey(tool))"
                class="tool-schema-pre"
              ><code>{{ JSON.stringify(tool.input_schema || {}, null, 2) }}</code></pre>
            </div>
          </div>
        </div>

        <div class="drawer-bottom-actions">
          <MdButton variant="filled" @click="openAccessModalFromDetail">
            <Zap :size="15" />
            <span>一键获取此能力接入配置</span>
          </MdButton>
        </div>
      </div>
    </MdDrawer>

    <!-- 3. 提交权限申请弹窗 -->
    <AdaptiveModal
      v-model="applyModalVisible"
      title="申请开通敏感业务工具"
      description="所选工具经管理员审批通过后，将自动生效于您的 MCP 长效 Token。"
      max-width="580px"
    >
      <div v-if="currentDetail" class="apply-modal-body">
        <div class="selected-tools-summary">
          <span class="summary-label">待开通工具 ({{ selectedToolsSummary.length }})</span>
          <div class="selected-tools-tags">
            <span v-for="t in selectedToolsSummary" :key="t.id" class="selected-tool-chip">
              {{ t.name }} ({{ t.risk }})
            </span>
          </div>
        </div>

        <div
          v-if="selectedRequiresCredentials && currentDetail.credential_schema"
          class="credential-section"
        >
          <div class="credential-tip">
            {{
              currentDetail.credential_schema.instructions ||
              '此服务要求绑定个人业务账号，所有已获批工具将共用此加密凭据。'
            }}
          </div>

          <div v-if="currentServiceExistingBinding" class="credential-bound-card">
            <CheckCircle2 :size="16" />
            <span>
              已绑定账号:
              <strong>{{
                currentServiceExistingBinding.credential_summary?.username || '已保存凭据'
              }}</strong>
              （本次申请将自动复用）
            </span>
            <MdButton variant="text" @click="showCustomCredInApply = !showCustomCredInApply">
              {{ showCustomCredInApply ? '收起修改' : '修改凭据' }}
            </MdButton>
          </div>

          <div
            v-if="!currentServiceExistingBinding || showCustomCredInApply"
            class="credential-inputs-grid"
          >
            <div
              v-for="field in currentDetail.credential_schema.fields"
              :key="field.field_name"
              class="credential-input-item"
            >
              <label class="form-label">
                {{ field.label }}
                <span v-if="field.required" class="required-mark">*</span>
              </label>
              <input
                v-model="applyCredentialForm[field.field_name]"
                :type="field.field_type === 'password' ? 'password' : 'text'"
                :placeholder="field.placeholder || field.description || `请输入${field.label}`"
                class="form-input"
                :class="{ mono: field.field_type === 'password' }"
              />
            </div>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">
            申请原因 / 业务场景说明 <span class="required-mark">*</span>
          </label>
          <textarea
            v-model="applyReason"
            rows="3"
            placeholder="请简述日常业务场景及申请理由"
            class="form-textarea"
          ></textarea>
        </div>
      </div>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="applyModalVisible = false">取消</MdButton>
          <MdButton
            variant="filled"
            :disabled="submittingApply || !applyReason.trim()"
            @click="submitPermissionApplication"
          >
            {{ submittingApply ? '正在提交...' : '确认提交申请' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- 4. 我的申请记录抽屉 -->
    <MdDrawer v-model="myRequestsDrawerVisible" title="我的功能权限申请记录" width="600px">
      <div v-if="loadingMyRequests" class="detail-loading-box">
        <RefreshCw :size="24" class="is-spinning" />
        <span>正在加载申请记录...</span>
      </div>
      <div v-else-if="!myRequests.length" class="empty-drawer-box">
        <ListChecks :size="44" />
        <p class="empty-title">暂无权限申请记录</p>
        <p class="empty-desc">在能力详情抽屉中勾选非 L0 工具即可提交开通申请</p>
      </div>
      <div v-else class="my-requests-list">
        <MdCard
          v-for="req in myRequests"
          :key="req.id"
          variant="filled"
          class="req-record-card"
        >
          <div class="req-card-header">
            <div class="req-svc-title">
              <strong>{{ req.service_name || req.service_id }}</strong>
              <span class="req-id-tag mono">{{ req.id }}</span>
            </div>
            <span class="req-status-pill" :class="`status-${req.status}`">
              {{
                req.status === 'approved'
                  ? '已通过'
                  : req.status === 'rejected'
                    ? '已驳回'
                    : '待审批'
              }}
            </span>
          </div>

          <div class="req-tools-box">
            <span class="req-tools-label">申请功能:</span>
            <span v-for="tName in req.tool_names" :key="tName" class="req-tool-tag">
              {{ tName }}
            </span>
          </div>

          <p class="req-reason-text"><strong>申请理由:</strong> {{ req.reason || '无说明' }}</p>

          <div v-if="req.comment" class="req-comment-box">
            <span>审批批注 ({{ req.reviewed_by || '管理员' }}):</span>
            <p>{{ req.comment }}</p>
          </div>

          <div class="req-time-row">
            <span>提交: {{ req.created_at ? req.created_at.slice(0, 19).replace('T', ' ') : '-' }}</span>
            <span v-if="req.reviewed_at">
              审批: {{ req.reviewed_at.slice(0, 19).replace('T', ' ') }}
            </span>
          </div>
        </MdCard>
      </div>
    </MdDrawer>

    <!-- 5. 我的 MCP 资产与凭据管理抽屉 -->
    <MdDrawer v-model="myMcpsDrawerVisible" title="我添加的 MCP 能力" width="640px">
      <div v-if="loadingMyMcps" class="detail-loading-box">
        <RefreshCw :size="24" class="is-spinning" />
        <span>正在加载个人 MCP 资产...</span>
      </div>
      <div v-else-if="!myMcpsList.length" class="empty-drawer-box">
        <Layers :size="44" />
        <p class="empty-title">暂未绑定或申请任何受控 MCP 服务</p>
        <p class="empty-desc">在能力详情中申请非 L0 工具或绑定个人凭据后将在此展示</p>
      </div>
      <div v-else class="my-mcps-container">
        <MdCard
          v-for="item in myMcpsList"
          :key="item.service_id"
          variant="filled"
          class="my-mcp-item-card"
        >
          <div class="my-mcp-header">
            <div class="my-mcp-title">
              <strong>{{ item.service_name }}</strong>
              <span class="req-id-tag mono">{{ item.service_id }}</span>
            </div>
            <div class="my-mcp-header-right">
              <span class="mcp-status-pill" :class="`tone-${getMyMcpStatusTone(item)}`">
                {{ getMyMcpStatusLabel(item) }}
              </span>
              <MdSwitch
                :model-value="item.user_enabled !== false"
                :disabled="togglingServiceIds.has(item.service_id)"
                @update:model-value="(val) => handleToggleServiceEnabled(item.service_id, val)"
              />
            </div>
          </div>

          <div class="my-mcp-tools">
            <span class="sub-label">已获批工具:</span>
            <div v-if="item.approved_tools?.length" class="tool-chip-list">
              <span v-for="tool in item.approved_tools" :key="tool" class="tool-chip granted">
                {{ tool }}
              </span>
            </div>
            <span v-else class="sub-empty">暂无获批工具</span>
          </div>

          <div v-if="item.pending_tools?.length" class="my-mcp-tools">
            <span class="sub-label">待审批工具:</span>
            <div class="tool-chip-list">
              <span v-for="tool in item.pending_tools" :key="tool" class="tool-chip pending">
                {{ tool }}
              </span>
            </div>
          </div>

          <div v-if="item.requires_credentials" class="my-mcp-cred-bar">
            <div class="cred-info">
              <Key :size="14" />
              <span>
                业务账号:
                <strong>{{ item.credential_summary?.username || '未配置' }}</strong>
                <span v-if="isServiceUnavailable(item)" class="cred-msg danger">
                  （下游不可用{{ item.downstream_error ? `: ${item.downstream_error}` : '' }}）
                </span>
                <span v-else-if="item.credential_status === 'verified'" class="cred-msg success">
                  （已验证）
                </span>
                <span v-else-if="item.credential_status === 'saved'" class="cred-msg primary">
                  （已保存，待调用验证）
                </span>
                <span v-else-if="item.credential_status === 'invalid'" class="cred-msg danger">
                  （登录失效，请更新密码）
                </span>
                <span v-else-if="item.credential_status === 'unbound'" class="cred-msg danger">
                  （已解绑，调用已阻断）
                </span>
                <span v-else class="cred-msg warning">（未配置有效凭据）</span>
              </span>
            </div>
            <div class="cred-actions">
              <MdButton variant="text" @click="openEditBindingDialog(item)">修改账号密码</MdButton>
              <MdButton
                v-if="
                  item.credential_status === 'saved' ||
                  item.credential_status === 'verified' ||
                  item.credential_status === 'invalid'
                "
                variant="text"
                @click="handleUnbindService(item)"
              >
                解绑
              </MdButton>
            </div>
          </div>
          <div v-else-if="isServiceUnavailable(item)" class="my-mcp-cred-bar">
            <span class="cred-msg danger">
              下游不可用{{ item.downstream_error ? `：${item.downstream_error}` : '：服务暂不可达或已停用' }}
            </span>
          </div>
        </MdCard>
      </div>
    </MdDrawer>

    <!-- 6. 改密弹窗 -->
    <AdaptiveModal
      v-model="editBindingModalVisible"
      title="更新个人业务凭据"
      description="更新业务账号密码后，新凭据将立即加密保存，原下游会话立即失效以确保安全。"
      max-width="460px"
    >
      <div v-if="editingMcpItem" class="edit-binding-content">
        <p class="edit-binding-tip">
          正在为服务 <strong>{{ editingMcpItem.service_name }}</strong> 更新业务账号凭据。
        </p>
        <div class="form-item">
          <label class="form-label">业务用户名 / 账号</label>
          <input
            v-model="editBindingForm.username"
            type="text"
            placeholder="请输入业务用户名"
            class="form-input"
          />
        </div>
        <div class="form-item">
          <label class="form-label">新密码</label>
          <input
            v-model="editBindingForm.password"
            type="password"
            placeholder="请输入新密码（留空则不修改密码）"
            class="form-input mono"
          />
        </div>
      </div>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="editBindingModalVisible = false">取消</MdButton>
          <MdButton
            variant="filled"
            :disabled="submittingEditBinding || !editBindingForm.username.trim()"
            @click="submitEditBinding"
          >
            {{ submittingEditBinding ? '正在保存...' : '确认保存' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- 7. 接入指引弹窗 -->
    <AdaptiveModal v-model="guideModalVisible" title="MCP 能力接入指引" max-width="640px">
      <div class="guide-modal-body">
        <div class="three-steps single-col">
          <div class="step-card">
            <div class="step-num">1</div>
            <div class="step-body">
              <span class="step-title">登录小秘书账号</span>
              <span class="step-text">点击右上角小秘书登录，系统自动签发与工号绑定的长效 MCP Token。</span>
            </div>
          </div>
          <div class="step-card">
            <div class="step-num">2</div>
            <div class="step-body">
              <span class="step-title">复制标准配置到 AI 客户端</span>
              <span class="step-text">
                点击任意卡片或顶部「一键接入」，将生成的 Streamable HTTP 地址与 Bearer Token 粘贴至 Cursor / Cherry Studio / Claude Desktop。
              </span>
            </div>
          </div>
          <div class="step-card">
            <div class="step-num">3</div>
            <div class="step-body">
              <span class="step-title">分级权限与个人凭据托管</span>
              <span class="step-text">
                L0 公开工具开箱即用；L1-L3 高敏工具可在能力详情中勾选提交审批，需个人业务账号的工具可一站式绑定并随时修改或解绑。
              </span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="filled" @click="guideModalVisible = false">我知道了</MdButton>
        </div>
      </template>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.capabilities-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.portal-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.toolbar-search {
  position: relative;
  flex: 1;
  min-width: 260px;
  max-width: 440px;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 14px;
  color: var(--md-sys-color-on-surface-variant);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 40px;
  padding: 0 36px 0 40px;
  border-radius: var(--md-sys-shape-corner-full);
  border: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s, background-color 0.2s;
}

.search-input:focus {
  border-color: var(--md-sys-color-primary);
  background-color: var(--md-sys-color-surface-container-lowest);
}

.search-clear-btn {
  position: absolute;
  right: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--md-sys-shape-corner-full);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-size: 11px;
  font-weight: 700;
}

.engine-down-card {
  margin-top: 8px;
}

.engine-down-content {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.engine-down-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--md-sys-shape-corner-medium);
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
  flex-shrink: 0;
}

.engine-down-text {
  flex: 1;
  min-width: 220px;
}

.engine-down-text h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  margin: 0 0 4px;
}

.engine-down-text p {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  margin: 0;
}

.portal-hero-card {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  padding: 4px 12px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-primary);
  font-size: 12px;
  font-weight: 600;
}

.hero-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--md-sys-color-on-surface);
  letter-spacing: -0.02em;
}

.hero-desc {
  margin: 0;
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
  max-width: 780px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

@media (max-width: 960px) {
  .stats-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-icon-wrapper {
  width: 42px;
  height: 42px;
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

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--md-sys-color-on-surface);
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.trend-stat-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
}

.trend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.trend-total {
  font-size: 11px;
  font-weight: 600;
  color: var(--md-sys-color-primary);
}

.mini-trend-bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 42px;
}

.mini-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  height: 100%;
}

.mini-bar-track {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.mini-bar-fill {
  width: 100%;
  max-width: 10px;
  border-radius: 3px 3px 0 0;
  background-color: var(--md-sys-color-primary);
  opacity: 0.85;
}

.mini-bar-day {
  font-size: 10px;
  color: var(--md-sys-color-on-surface-variant);
}

.discovery-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.category-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.category-tab-btn,
.sort-opt-btn {
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-surface-container-low);
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
}

.category-tab-btn.is-active,
.sort-opt-btn.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}

.sort-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sort-label {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.sort-options {
  display: flex;
  gap: 6px;
}

.cards-skeleton-grid,
.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 1120px) {
  .cards-skeleton-grid,
  .capabilities-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .cards-skeleton-grid,
  .capabilities-grid {
    grid-template-columns: 1fr;
  }
}

.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-line {
  height: 14px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-high);
}

.skeleton-line.short {
  width: 45%;
}

.skeleton-line.medium {
  width: 70%;
}

.skeleton-line.long {
  width: 100%;
}

.empty-portal-state .empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
  padding: 24px 0;
  color: var(--md-sys-color-on-surface-variant);
}

.empty-portal-state h3 {
  margin: 0;
  color: var(--md-sys-color-on-surface);
  font-size: 16px;
}

.empty-portal-state p {
  margin: 0;
  font-size: 13px;
}

.cap-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cap-card__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.cap-card__avatar,
.detail-avatar {
  width: 44px;
  height: 44px;
  border-radius: var(--md-sys-shape-corner-medium);
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-primary-container);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cap-card__title-area {
  flex: 1;
  min-width: 0;
}

.cap-card__name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.cap-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-indicator {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-indicator.is-active {
  background-color: var(--sys-status-success-text);
}

.status-indicator.is-degraded {
  background-color: var(--sys-status-warning-text);
}

.cap-card__tags,
.detail-tags-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.category-pill,
.auth-pill,
.version-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 500;
}

.category-pill {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface-variant);
}

.auth-pill {
  background-color: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
}

.version-pill {
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface-variant);
}

.cap-card__desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--md-sys-color-on-surface-variant);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 40px;
}

.cap-card__metrics {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-top: 8px;
  border-top: 1px solid var(--md-sys-color-outline-variant);
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.metric-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.cap-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
}

.access-panel,
.apply-modal-body,
.edit-binding-content,
.guide-modal-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.aggregation-banner,
.user-binding-banner,
.auth-notice-card,
.credential-tip,
.credential-bound-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--md-sys-shape-corner-medium);
  font-size: 13px;
}

.aggregation-banner {
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
}

.banner-title {
  margin: 0 0 2px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.banner-text {
  margin: 0;
  line-height: 1.45;
}

.user-binding-banner.is-logged-in {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.user-binding-banner.is-guest {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
  justify-content: space-between;
}

.access-tabs {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  padding-bottom: 10px;
}

.access-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-surface-container-low);
  cursor: pointer;
}

.access-tab-btn.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
}

.field-copy-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface-variant);
}

.field-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
  border: 1px solid var(--md-sys-color-outline-variant);
}

.field-box.highlight-box {
  border-color: var(--md-sys-color-primary);
}

.field-val {
  font-size: 13px;
  color: var(--md-sys-color-on-surface);
}

.break-all {
  word-break: break-all;
}

.code-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface-variant);
}

.code-preview,
.natural-prompt-box,
.tool-schema-pre {
  margin: 0;
  padding: 12px 14px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  overflow-x: auto;
  white-space: pre-wrap;
}

.auth-notice-card {
  justify-content: space-between;
  background-color: var(--md-sys-color-surface-container-low);
}

.auth-notice-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.auth-notice-title {
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 2px;
}

.auth-notice-desc {
  margin: 0;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.modal-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.detail-loading-box,
.empty-drawer-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 48px 20px;
  text-align: center;
  color: var(--md-sys-color-on-surface-variant);
}

.empty-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.empty-desc {
  margin: 0;
  font-size: 13px;
}

.is-spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.detail-drawer-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--md-sys-color-on-surface);
}

.detail-desc {
  margin: 12px 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.5;
}

.detail-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.detail-stat-box {
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-lowest);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-num {
  font-size: 18px;
  font-weight: 700;
  color: var(--md-sys-color-on-surface);
}

.stat-sub {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.three-steps {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.three-steps.single-col {
  grid-template-columns: 1fr;
}

.step-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: var(--md-sys-shape-corner-medium);
  background-color: var(--md-sys-color-surface-container-low);
}

.step-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.step-text {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.45;
}

.examples-list,
.tools-list,
.my-requests-list,
.my-mcps-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.example-pill-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
  font-size: 13px;
  color: var(--md-sys-color-on-surface);
}

.tools-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.tools-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-item-card {
  padding: 12px;
  border-radius: var(--md-sys-shape-corner-medium);
  background-color: var(--md-sys-color-surface-container-low);
  border: 1px solid var(--md-sys-color-outline-variant);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tool-item-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.tool-checkbox {
  margin-top: 3px;
  width: 16px;
  height: 16px;
  accent-color: var(--md-sys-color-primary);
}

.tool-item-body {
  flex: 1;
  min-width: 0;
}

.tool-item-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tool-biz-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.tool-tech-name {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.risk-badge,
.granted-badge,
.mcp-status-pill,
.req-status-pill {
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
}

.risk-l0,
.granted-badge,
.tone-success,
.req-status-pill.status-approved,
.tool-chip.granted {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.risk-l1,
.tone-primary {
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-primary-container);
}

.risk-l2,
.tone-warning,
.req-status-pill.status-pending,
.tool-chip.pending {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.risk-l3,
.tone-danger,
.req-status-pill.status-rejected {
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
}

.tone-neutral {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface-variant);
}

.tool-biz-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.45;
}

.schema-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
  cursor: pointer;
}

.drawer-bottom-actions {
  display: flex;
  justify-content: flex-end;
}

.selected-tools-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-label,
.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.required-mark {
  color: var(--md-sys-color-error);
}

.selected-tools-tags,
.tool-chip-list,
.req-tools-box {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.selected-tool-chip,
.req-tool-tag,
.tool-chip {
  padding: 3px 10px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 12px;
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface);
}

.credential-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.credential-tip {
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
}

.credential-bound-card {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
  justify-content: space-between;
}

.credential-inputs-grid {
  display: grid;
  gap: 10px;
}

.form-item,
.credential-input-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 9px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  border: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}

.form-input:focus,
.form-textarea:focus {
  border-color: var(--md-sys-color-primary);
}

.req-card-header,
.my-mcp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.req-svc-title,
.my-mcp-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.req-id-tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface-variant);
}

.req-tools-label,
.sub-label,
.sub-empty {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.req-reason-text {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.req-comment-box {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-lowest);
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.req-comment-box p {
  margin: 4px 0 0;
}

.req-time-row {
  display: flex;
  gap: 14px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.my-mcp-tools {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}

.my-mcp-cred-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--md-sys-color-outline-variant);
  font-size: 12px;
}

.cred-info {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--md-sys-color-on-surface-variant);
}

.cred-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.cred-msg.success {
  color: var(--sys-status-success-text);
}

.cred-msg.primary {
  color: var(--md-sys-color-primary);
}

.cred-msg.warning {
  color: var(--sys-status-warning-text);
}

.cred-msg.danger {
  color: var(--sys-status-danger-text);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.cap-assembly-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
}

.assembly-label {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.my-mcp-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
