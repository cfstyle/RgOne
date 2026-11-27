// 前端统一 API 客户端封装（离线无 CDN，标准 fetch）
const API_BASE = '/api/v1'

export interface ApiResult<T = unknown> {
  success?: boolean
  data?: T
  message?: string
  detail?: string
  total?: number
  items?: T
}

export type UsageRankingDimension = 'user' | 'model'
export type UsageRankingRange = 'today' | '7d' | '30d' | 'all'

export interface EmployeeTokenDetail {
  emp_no: string
  name: string
  department: string
  token_name: string
  api_key: string
  masked_key: string
  base_url: string
  provider_id: string
  provider_name: string
  api_protocol: string
  default_model: string
  status: string
  reset_count: number
  created_at: string
}

function getEmployeeToken(): string {
  return localStorage.getItem('rgone_emp_token') || ''
}

function getAdminToken(): string {
  return localStorage.getItem('rgone_admin_token') || ''
}

export async function request<T = unknown>(
  endpoint: string,
  options: RequestInit = {},
  useAdminAuth: boolean = false
): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  const headers = new Headers(options.headers || {})

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const token = useAdminAuth ? getAdminToken() : getEmployeeToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const res = await fetch(url, {
    ...options,
    headers,
  })

  // 如果返回 401 且是管理员端，清理 token
  if (res.status === 401 && useAdminAuth) {
    localStorage.removeItem('rgone_admin_token')
  }

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const errorMsg = data.detail || data.message || `请求失败 (${res.status})`
    throw new Error(errorMsg)
  }
  return data
}

// ---------------- 员工与公共接口 ----------------
export const api = {
  // 引导与模型
  getModels: () => request('/guide/models'),
  getGatewayStatus: () => request('/guide/status'),
  getRecommendedInstaller: () => request('/guide/recommended-installer'),
  getCordisPatchUrl: () => `${API_BASE}/guide/cordis-patch-yml`,

  // 统一认证与验证码
  sendVerifyCode: (account: string) =>
    request('/auth/send-code', {
      method: 'POST',
      body: JSON.stringify({ account }),
    }),
  unifiedLogin: (data: { account: string; password?: string; code?: string }) =>
    request('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // 认证与核验（兼容旧接口）
  lookupEmployee: (emp_no: string) =>
    request('/auth/emp/lookup', {
      method: 'POST',
      body: JSON.stringify({ emp_no }),
    }),
  verifyEmployee: (emp_no: string, name: string) =>
    request('/auth/emp/verify', {
      method: 'POST',
      body: JSON.stringify({ emp_no, name }),
    }),

  // 我的工作台
  getMyToken: (signal?: AbortSignal) => request<EmployeeTokenDetail>('/me/token', { signal }),
  claimMyToken: (signal?: AbortSignal) => request<EmployeeTokenDetail>('/me/token/claim', { method: 'POST', signal }),
  resetMyToken: (signal?: AbortSignal) => request<EmployeeTokenDetail>('/me/token/reset', { method: 'POST', signal }),

  // 极细用量看板
  getUsageOverview: (range: string = '7d') => request(`/me/usage/overview?range=${range}`),
  getUsageTrend: (range: string = '7d') => request(`/me/usage/trend?range=${range}`),
  getUsageModels: (range: string = '7d') => request(`/me/usage/models?range=${range}`),
  getUsageLogs: (page: number = 1, page_size: number = 15, model_name?: string) => {
    let q = `/me/usage/logs?page=${page}&page_size=${page_size}`
    if (model_name) q += `&model_name=${encodeURIComponent(model_name)}`
    return request(q)
  },
  triggerUsageSync: () => request('/me/usage/sync', { method: 'POST' }),

  // 资料与安装包
  getFiles: (category?: string) => request(category ? `/files?category=${category}` : '/files'),
  getFileDownloadUrl: (id: number) => `${API_BASE}/files/download/${id}`,

  // 案例文章
  getArticles: (category?: string, keyword?: string, page: number = 1) => {
    let q = `/articles?page=${page}&page_size=12`
    if (category) q += `&category=${encodeURIComponent(category)}`
    if (keyword) q += `&keyword=${encodeURIComponent(keyword)}`
    return request(q)
  },
  getArticleDetail: (id: number) => request(`/articles/${id}`),

  // ---------------- 管理员接口 ----------------
  adminLogin: (username: string, password: string) =>
    request(
      '/auth/admin/login',
      {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      },
      false
    ),

  getAdminOverview: () => request('/admin/overview', {}, true),
  getAdminUsageRanking: (dimension: UsageRankingDimension, range: UsageRankingRange, signal: AbortSignal) =>
    request<ApiResult<unknown>>(`/admin/usage/ranking?dimension=${dimension}&range=${range}`, { signal }, true),
  adminSyncLogs: () =>
    request(
      '/admin/logs/sync',
      {
        method: 'POST',
      },
      true
    ),
  getAdminSettings: () => request('/admin/settings', {}, true),
  updateAdminSettings: (data: Record<string, unknown>) =>
    request(
      '/admin/settings',
      {
        method: 'PUT',
        body: JSON.stringify(data),
      },
      true
    ),
  testGateway: (data: Record<string, unknown> = {}) =>
    request(
      '/admin/test-gateway',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      true
    ),

  // 员工管理
  getAdminEmployees: (page: number = 1, keyword?: string) => {
    let q = `/admin/employees?page=${page}&page_size=15`
    if (keyword) q += `&keyword=${encodeURIComponent(keyword)}`
    return request(q, {}, true)
  },
  createEmployee: (data: Record<string, unknown>) =>
    request(
      '/admin/employees',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      true
    ),
  updateEmployee: (id: number, data: Record<string, unknown>) =>
    request(
      `/admin/employees/${id}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      },
      true
    ),
  deleteEmployee: (id: number) =>
    request(
      `/admin/employees/${id}`,
      {
        method: 'DELETE',
      },
      true
    ),
  retryDisableEmployeeToken: (id: number) =>
    request(
      `/admin/employees/${id}/retry-disable-token`,
      {
        method: 'POST',
      },
      true
    ),
  retryHubSync: (id: number) =>
    request(
      `/admin/employees/${id}/retry-hub-sync`,
      {
        method: 'POST',
      },
      true
    ),
  getEmployeeTemplateUrl: () => `${API_BASE}/admin/employees/template`,
  importEmployees: (formData: FormData) =>
    request(
      '/admin/employees/import',
      {
        method: 'POST',
        body: formData,
      },
      true
    ),

  // Token 管理
  getAdminTokens: (page: number = 1, keyword?: string, status_filter?: string) => {
    let q = `/admin/tokens?page=${page}&page_size=15`
    if (keyword) q += `&keyword=${encodeURIComponent(keyword)}`
    if (status_filter) q += `&status_filter=${status_filter}`
    return request(q, {}, true)
  },
  toggleTokenStatus: (id: number, status: string) =>
    request(
      `/admin/tokens/${id}/status`,
      {
        method: 'PUT',
        body: JSON.stringify({ status }),
      },
      true
    ),
  adminResetToken: (id: number) =>
    request(
      `/admin/tokens/${id}/reset`,
      {
        method: 'POST',
      },
      true
    ),

  // 资料上传与删除
  uploadFile: (formData: FormData) =>
    request(
      '/admin/files/upload',
      {
        method: 'POST',
        body: formData,
      },
      true
    ),
  updateFileMeta: (id: number, data: Record<string, unknown>) =>
    request(
      `/admin/files/${id}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      },
      true
    ),
  deleteFile: (id: number) =>
    request(
      `/admin/files/${id}`,
      {
        method: 'DELETE',
      },
      true
    ),

  // 案例文章管理
  getAdminArticles: (page: number = 1, keyword?: string) => {
    let q = `/admin/articles?page=${page}&page_size=15`
    if (keyword) q += `&keyword=${encodeURIComponent(keyword)}`
    return request(q, {}, true)
  },
  createArticle: (data: Record<string, unknown>) =>
    request(
      '/admin/articles',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      true
    ),
  updateArticle: (id: number, data: Record<string, unknown>) =>
    request(
      `/admin/articles/${id}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      },
      true
    ),
  deleteArticle: (id: number) =>
    request(
      `/admin/articles/${id}`,
      {
        method: 'DELETE',
      },
      true
    ),
  uploadArticleImage: (formData: FormData) =>
    request(
      '/admin/articles/upload-image',
      {
        method: 'POST',
        body: formData,
      },
      true
    ),
}
