import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import type {
  AuditLogsParams,
  AuditLogsResponse,
  ConnectionTestResponse,
  DashboardSummary,
  McpBindingResponse,
  McpService,
  McpToggleResponse,
  PermissionRequest,
  PermissionRequestCreate,
  PermissionRequestReview,
  PluginInspectResult,
  PluginInstallResponse,
  PortalCapabilitiesQuery,
  PortalCapabilityCard,
  PortalCapabilityDetail,
  PortalOverview,
  RefreshResponse,
  RegisteredTool,
  ServiceMetadataUpdateRequest,
  ServiceRegistrationRequest,
  ServiceStatus,
  ServiceUpdateRequest,
  SystemStatusResponse,
  ToolExecuteRequest,
  ToolExecuteResponse,
  ToolPolicyUpdateRequest,
  UserClientConfig,
  UserMcpDetail,
} from '@/types/mcp'

const MCP_API_BASE = '/mcp-api/v1'
const DEFAULT_TIMEOUT_MS = 15_000
const LONG_TIMEOUT_MS = 120_000
const ENGINE_DOWN_STATUS_CODES = new Set([502, 503, 504])

type McpAuthScope = 'portal' | 'admin'

export interface McpRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  params?: Record<string, string | number | boolean | undefined>
  body?: unknown
  formData?: FormData
  signal?: AbortSignal
  timeoutMs?: number
}

export class McpEngineError extends Error {
  status: number
  isEngineDown: boolean
  detail?: string

  constructor(
    message: string,
    status: number = 0,
    isEngineDown: boolean = false,
    detail?: string
  ) {
    super(message)
    this.name = 'McpEngineError'
    this.status = status
    this.isEngineDown = isEngineDown
    this.detail = detail
  }
}

export function isMcpEngineUnavailable(err: unknown): boolean {
  if (err instanceof McpEngineError) {
    return err.isEngineDown
  }
  return false
}

export function getMcpErrorMessage(err: unknown, fallback = '请求失败'): string {
  if (err instanceof McpEngineError) {
    return err.message || fallback
  }
  if (err instanceof Error) {
    return err.message || fallback
  }
  return fallback
}

function getScopedToken(scope: McpAuthScope): string {
  // 严格按路由作用域隔离 Token：门户只读员工 Token，管理端只读管理员 Token
  if (scope === 'admin') {
    return localStorage.getItem('rgone_admin_token') || ''
  }
  return localStorage.getItem('rgone_emp_token') || ''
}

function handleUnauthorized(scope: McpAuthScope): void {
  const authStore = useAuthStore()
  if (scope === 'admin') {
    authStore.logoutAdmin()
    if (router.currentRoute.value.path !== '/admin/dashboard') {
      void router.push('/admin/dashboard')
    }
    return
  }
  authStore.logoutEmployee()
  window.dispatchEvent(
    new CustomEvent('rgone:open-login', {
      detail: { mode: 'employee' },
    })
  )
}

function buildUrl(
  path: string,
  params?: Record<string, string | number | boolean | undefined>
): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const base = `${MCP_API_BASE}${normalizedPath}`
  if (!params) return base

  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  }
  const qs = search.toString()
  return qs ? `${base}?${qs}` : base
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === 'object' && payload !== null) {
    const obj = payload as Record<string, unknown>
    if (typeof obj.detail === 'string' && obj.detail.trim()) return obj.detail
    if (typeof obj.message === 'string' && obj.message.trim()) return obj.message
    if (typeof obj.error === 'string' && obj.error.trim()) return obj.error
  }
  return fallback
}

function createCombinedSignal(
  timeoutMs: number,
  externalSignal?: AbortSignal
): { signal: AbortSignal; cleanup: () => void; isTimeout: () => boolean } {
  const controller = new AbortController()
  let timedOut = false
  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  const onExternalAbort = () => {
    controller.abort()
  }

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort()
    } else {
      externalSignal.addEventListener('abort', onExternalAbort, { once: true })
    }
  }

  return {
    signal: controller.signal,
    isTimeout: () => timedOut,
    cleanup: () => {
      window.clearTimeout(timer)
      if (externalSignal) {
        externalSignal.removeEventListener('abort', onExternalAbort)
      }
    },
  }
}

async function mcpFetch<T>(
  scope: McpAuthScope,
  path: string,
  options: McpRequestOptions = {}
): Promise<T> {
  const method = options.method || 'GET'
  const url = buildUrl(path, options.params)
  const headers = new Headers()

  if (!options.formData && options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }

  const token = getScopedToken(scope)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const { signal, cleanup, isTimeout } = createCombinedSignal(
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    options.signal
  )

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: options.formData
        ? options.formData
        : options.body !== undefined
          ? JSON.stringify(options.body)
          : undefined,
      signal,
    })

    if (response.status === 401) {
      handleUnauthorized(scope)
      throw new McpEngineError('登录状态已失效，请重新登录', 401, false)
    }

    if (ENGINE_DOWN_STATUS_CODES.has(response.status)) {
      throw new McpEngineError(
        `能力引擎暂不可用 (HTTP ${response.status})`,
        response.status,
        true
      )
    }

    if (response.status === 204) {
      return undefined as T
    }

    const contentType = (response.headers.get('content-type') || '').toLowerCase()
    if (response.ok && contentType.includes('text/html')) {
      throw new McpEngineError(
        '未命中能力引擎代理，请确认通过 Nginx 或 Vite 5173 访问',
        502,
        true
      )
    }

    const payload = contentType.includes('application/json')
      ? await response.json().catch(() => null)
      : await response.text().catch(() => '')

    if (!response.ok) {
      const msg = extractErrorMessage(
        payload,
        typeof payload === 'string' && payload.trim()
          ? payload
          : `请求失败 (${response.status})`
      )
      throw new McpEngineError(msg, response.status, false, msg)
    }

    return payload as T
  } catch (err: unknown) {
    if (err instanceof McpEngineError) {
      throw err
    }
    if (err instanceof DOMException && err.name === 'AbortError') {
      if (isTimeout()) {
        throw new McpEngineError('连接能力引擎超时，请稍后重试', 504, true)
      }
      throw err
    }
    throw new McpEngineError('无法连接能力引擎服务，请确认 hub-core 是否已启动', 503, true)
  } finally {
    cleanup()
  }
}

async function mcpFetchBlob(scope: McpAuthScope, path: string): Promise<Blob> {
  const url = buildUrl(path)
  const headers = new Headers()
  const token = getScopedToken(scope)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const { signal, cleanup, isTimeout } = createCombinedSignal(LONG_TIMEOUT_MS)
  try {
    const response = await fetch(url, { method: 'GET', headers, signal })
    if (response.status === 401) {
      handleUnauthorized(scope)
      throw new McpEngineError('登录状态已失效，请重新登录', 401, false)
    }
    if (ENGINE_DOWN_STATUS_CODES.has(response.status)) {
      throw new McpEngineError(`能力引擎暂不可用 (HTTP ${response.status})`, response.status, true)
    }
    if (!response.ok) {
      throw new McpEngineError(`下载失败 (${response.status})`, response.status, false)
    }
    return await response.blob()
  } catch (err: unknown) {
    if (err instanceof McpEngineError) throw err
    if (err instanceof DOMException && err.name === 'AbortError' && isTimeout()) {
      throw new McpEngineError('下载模板超时', 504, true)
    }
    throw new McpEngineError('无法连接能力引擎服务', 503, true)
  } finally {
    cleanup()
  }
}

// ============================================================================
// 门户接口 (Portal Track - 只读 rgone_emp_token)
// ============================================================================

export function getPortalOverview(signal?: AbortSignal): Promise<PortalOverview> {
  return mcpFetch<PortalOverview>('portal', '/portal/overview', { signal })
}

export function getPortalCapabilities(
  params?: PortalCapabilitiesQuery,
  signal?: AbortSignal
): Promise<PortalCapabilityCard[]> {
  return mcpFetch<PortalCapabilityCard[]>('portal', '/portal/capabilities', {
    params: params ? { ...params } : undefined,
    signal,
  })
}

export function getPortalCapabilityDetail(
  id: string,
  signal?: AbortSignal
): Promise<PortalCapabilityDetail> {
  return mcpFetch<PortalCapabilityDetail>(
    'portal',
    `/portal/capabilities/${encodeURIComponent(id)}`,
    { signal }
  )
}

export function getPortalMyConfig(
  userId?: string,
  signal?: AbortSignal
): Promise<UserClientConfig> {
  return mcpFetch<UserClientConfig>('portal', '/portal/my-config', {
    params: { user_id: userId },
    signal,
  })
}

export function getPortalMyGrants(
  userId?: string,
  signal?: AbortSignal
): Promise<{ user_id: string; granted_tool_ids: string[] }> {
  return mcpFetch<{ user_id: string; granted_tool_ids: string[] }>(
    'portal',
    '/portal/my-grants',
    {
      params: { user_id: userId },
      signal,
    }
  )
}

export function createPortalPermissionRequest(
  data: PermissionRequestCreate
): Promise<PermissionRequest> {
  return mcpFetch<PermissionRequest>('portal', '/portal/permission-requests', {
    method: 'POST',
    body: data,
  })
}

export function getPortalMyRequests(
  userId?: string,
  signal?: AbortSignal
): Promise<PermissionRequest[]> {
  return mcpFetch<PermissionRequest[]>('portal', '/portal/my-requests', {
    params: { user_id: userId },
    signal,
  })
}

export function getPortalMyMcps(
  probe: boolean = true,
  signal?: AbortSignal
): Promise<UserMcpDetail[]> {
  return mcpFetch<UserMcpDetail[]>('portal', '/portal/my-mcps', {
    params: { probe },
    signal,
    timeoutMs: probe ? 30_000 : DEFAULT_TIMEOUT_MS,
  })
}

export function updatePortalServiceBinding(
  serviceId: string,
  credentials: Record<string, string>
): Promise<McpBindingResponse> {
  return mcpFetch<McpBindingResponse>(
    'portal',
    `/portal/my-mcps/${encodeURIComponent(serviceId)}/binding`,
    {
      method: 'POST',
      body: { credentials },
    }
  )
}

export function unbindPortalServiceBinding(serviceId: string): Promise<McpBindingResponse> {
  return mcpFetch<McpBindingResponse>(
    'portal',
    `/portal/my-mcps/${encodeURIComponent(serviceId)}/binding`,
    {
      method: 'DELETE',
    }
  )
}

export function togglePortalServiceEnabled(
  serviceId: string,
  enabled: boolean
): Promise<McpToggleResponse> {
  return mcpFetch<McpToggleResponse>(
    'portal',
    `/portal/my-mcps/${encodeURIComponent(serviceId)}/toggle`,
    {
      method: 'PUT',
      body: { enabled },
    }
  )
}

// ============================================================================
// 管理端接口 (Admin Track - 只读 rgone_admin_token)
// ============================================================================

export function getDashboardSummary(signal?: AbortSignal): Promise<DashboardSummary> {
  return mcpFetch<DashboardSummary>('admin', '/dashboard/summary', { signal })
}

export function getServices(
  params?: { status?: string; transport?: string; q?: string },
  signal?: AbortSignal
): Promise<McpService[]> {
  return mcpFetch<McpService[]>('admin', '/services', {
    params,
    signal,
  })
}

export function getService(id: string, signal?: AbortSignal): Promise<McpService> {
  return mcpFetch<McpService>('admin', `/services/${encodeURIComponent(id)}`, { signal })
}

export function registerService(data: ServiceRegistrationRequest): Promise<McpService> {
  return mcpFetch<McpService>('admin', '/services', {
    method: 'POST',
    body: data,
    timeoutMs: 30_000,
  })
}

export function updateService(id: string, data: ServiceUpdateRequest): Promise<McpService> {
  return mcpFetch<McpService>('admin', `/services/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: data,
  })
}

export function updateServiceMetadata(
  id: string,
  data: ServiceMetadataUpdateRequest
): Promise<McpService> {
  return mcpFetch<McpService>('admin', `/services/${encodeURIComponent(id)}/metadata`, {
    method: 'PATCH',
    body: data,
  })
}

export function updateServiceStatus(id: string, status: ServiceStatus): Promise<McpService> {
  return mcpFetch<McpService>('admin', `/services/${encodeURIComponent(id)}/status`, {
    method: 'PATCH',
    body: { status },
  })
}

export function deleteService(id: string): Promise<void> {
  return mcpFetch<void>('admin', `/services/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

export function refreshServiceTools(id: string): Promise<RefreshResponse> {
  return mcpFetch<RefreshResponse>('admin', `/services/${encodeURIComponent(id)}/refresh`, {
    method: 'POST',
    timeoutMs: 60_000,
  })
}

export function testServiceConnection(id: string): Promise<ConnectionTestResponse> {
  return mcpFetch<ConnectionTestResponse>(
    'admin',
    `/services/${encodeURIComponent(id)}/test-connection`,
    {
      method: 'POST',
      timeoutMs: 30_000,
    }
  )
}

export function downloadDeveloperGuide(): Promise<Blob> {
  return mcpFetchBlob('admin', '/plugins/developer-guide')
}

export function inspectPluginZip(file: File): Promise<PluginInspectResult> {
  const formData = new FormData()
  formData.append('file', file)
  return mcpFetch<PluginInspectResult>('admin', '/plugins/inspect', {
    method: 'POST',
    formData,
    timeoutMs: LONG_TIMEOUT_MS,
  })
}

export function installPluginZip(file: File): Promise<PluginInstallResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return mcpFetch<PluginInstallResponse>('admin', '/plugins/install', {
    method: 'POST',
    formData,
    timeoutMs: LONG_TIMEOUT_MS,
  })
}

export function listTools(serviceId?: string, signal?: AbortSignal): Promise<RegisteredTool[]> {
  return mcpFetch<RegisteredTool[]>('admin', '/tools', {
    params: serviceId ? { service_id: serviceId } : undefined,
    signal,
  })
}

export function updateToolPolicy(
  id: string,
  data: ToolPolicyUpdateRequest
): Promise<RegisteredTool> {
  return mcpFetch<RegisteredTool>('admin', `/tools/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: data,
  })
}

export function executeTool(data: ToolExecuteRequest): Promise<ToolExecuteResponse> {
  return mcpFetch<ToolExecuteResponse>('admin', '/tools/execute', {
    method: 'POST',
    body: data,
    timeoutMs: 60_000,
  })
}

export function getAdminPermissionRequests(
  params?: { user_id?: string; status?: string },
  signal?: AbortSignal
): Promise<PermissionRequest[]> {
  return mcpFetch<PermissionRequest[]>('admin', '/admin/permission-requests', {
    params,
    signal,
  })
}

export function reviewAdminPermissionRequest(
  id: string,
  data: PermissionRequestReview
): Promise<PermissionRequest> {
  return mcpFetch<PermissionRequest>(
    'admin',
    `/admin/permission-requests/${encodeURIComponent(id)}/review`,
    {
      method: 'POST',
      body: data,
    }
  )
}

export function getAuditLogs(
  params?: AuditLogsParams,
  signal?: AbortSignal
): Promise<AuditLogsResponse> {
  return mcpFetch<AuditLogsResponse>('admin', '/audit-logs', {
    params: params ? { ...params } : undefined,
    signal,
  })
}

export function getSystemStatus(signal?: AbortSignal): Promise<SystemStatusResponse> {
  return mcpFetch<SystemStatusResponse>('admin', '/system/status', { signal })
}
