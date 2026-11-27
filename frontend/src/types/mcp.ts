export type ServiceStatus = 'active' | 'inactive' | 'degraded' | 'pending'

export type RiskLevel = 'L0' | 'L1' | 'L2' | 'L3'

export type TransportType = 'http' | 'sse' | 'stdio' | 'internal_rest'

export type AuthMode = 'public' | 'platform_sso' | 'user_credential' | 'token' | 'none' | string

export type CredentialStatus =
  | 'not_required'
  | 'saved'
  | 'verified'
  | 'invalid'
  | 'unbound'
  | 'missing'
  | 'active'
  | string

export type ToolInputSchema = Record<string, unknown>

export interface CredentialFieldSchema {
  field_name: string
  label: string
  field_type: 'text' | 'password'
  required: boolean
  secret: boolean
  description?: string
  placeholder?: string
}

export interface ServiceCredentialSchema {
  enabled: boolean
  auth_type: string
  instructions: string
  fields: CredentialFieldSchema[]
}

export interface McpService {
  id: string
  name: string
  description: string
  transport: TransportType
  endpoint: string
  owner: string
  category?: string
  version?: string
  status: ServiceStatus
  tools_count: number
  last_health_check_at?: string
  created_at: string
  auth_mode?: AuthMode
  auth_label?: string
  auth_guide?: string
  auth_entry_url?: string
  usage_examples?: string[]
  credential_schema?: ServiceCredentialSchema | null
  trust_hub_credentials?: boolean
  plugin_dir?: string | null
  health_check_url?: string
}

export interface ServiceRegistrationRequest {
  name: string
  description?: string
  transport?: TransportType
  endpoint: string
  owner?: string
  category?: string
  auth_mode?: AuthMode
  auth_label?: string
  auth_guide?: string
  auth_entry_url?: string
  usage_examples?: string[]
  credential_schema?: ServiceCredentialSchema | null
  trust_hub_credentials?: boolean
}

export interface ServiceUpdateRequest {
  name?: string
  description?: string
  endpoint?: string
  owner?: string
  status?: ServiceStatus
  trust_hub_credentials?: boolean
}

export interface ServiceMetadataUpdateRequest {
  name?: string
  description?: string
  owner?: string
  category?: string
  auth_mode?: AuthMode
  auth_label?: string
  auth_guide?: string
  auth_entry_url?: string
  usage_examples?: string[]
  trust_hub_credentials?: boolean
}

export interface RefreshResponse {
  service_id: string
  tools_discovered: number
  status: string
  message?: string
}

export interface ConnectionTestResponse {
  service_id: string
  success: boolean
  latency_ms: number
  message: string
  tools_discovered?: number
}

export interface RegisteredTool {
  id: string
  service_id: string
  service_name?: string
  name: string
  namespace_name: string
  description: string
  risk_level: RiskLevel
  requires_confirmation: boolean
  requires_credentials?: boolean
  enabled: boolean
  input_schema: ToolInputSchema
  created_at?: string
}

export interface ToolPolicyUpdateRequest {
  risk_level?: RiskLevel
  requires_confirmation?: boolean
  requires_credentials?: boolean
  enabled?: boolean
}

export interface ToolExecuteRequest {
  service_id: string
  tool_name: string
  arguments: Record<string, unknown>
  confirmed?: boolean
}

export interface ToolExecuteResponse {
  success: boolean
  result: unknown
  execution_time_ms: number
  error?: string
  raw?: unknown
}

export interface DashboardSummary {
  services_count: number
  active_services_count: number
  tools_count: number
  enabled_tools_count: number
  calls_total: number
  calls_success: number
  calls_failed: number
}

export interface AuditLog {
  id: string
  trace_id: string
  service_id: string
  service_name?: string
  tool_name: string
  namespace_name: string
  caller: string
  risk_level: RiskLevel
  result_status: 'success' | 'error' | 'denied'
  duration_ms: number
  request_args?: string | Record<string, unknown>
  response_summary?: string
  error_message?: string
  created_at: string
}

export interface AuditLogsResponse {
  items: AuditLog[]
  total: number
  page: number
  page_size: number
}

export interface AuditLogsParams {
  service_id?: string
  tool_name?: string
  result_status?: string
  page?: number
  page_size?: number
}

export interface SystemStatusResponse {
  hub_name: string
  hub_version: string
  status: 'ok' | 'ready' | 'degraded'
  database: string
  mcp_endpoint: string
  upstream_services_count: number
}

export interface PluginInspectResult {
  id: string
  name: string
  version: string
  description: string
  category?: string
  owner?: string
  auth_mode?: string
  auth_label?: string
  auth_guide?: string
  auth_entry_url?: string
  runtime?: {
    type?: string
    command?: string[]
    port?: number
    health_check_path?: string
    [key: string]: unknown
  }
  tools_count?: number
  tools?: Array<{
    name: string
    description?: string
    risk_level?: string
    requires_credentials?: boolean
  }>
  usage_examples?: string[]
  credential_schema?: ServiceCredentialSchema | null
  trust_hub_credentials?: boolean
  manifest?: Record<string, unknown>
}

export interface PluginInstallResponse {
  success: boolean
  message: string
  service_id: string
  service?: McpService
}

export interface PortalTrendItem {
  date: string
  calls: number
  success_calls: number
}

export interface PortalOverview {
  services_count: number
  tools_count: number
  total_calls: number
  active_services_count: number
  health_rate: number
  daily_trends: PortalTrendItem[]
}

export interface UserMcpDetail {
  service_id: string
  service_name: string
  category: string
  endpoint_url: string
  requires_credentials: boolean
  credential_status: CredentialStatus
  service_status?: ServiceStatus | string
  downstream_status?: 'available' | 'unavailable' | string
  downstream_error?: string | null
  credential_summary: Record<string, string | undefined>
  credential_version: number
  approved_tools: string[]
  pending_tools: string[]
  user_enabled?: boolean
  updated_at?: string
}

export interface PortalCapabilityCard {
  id: string
  name: string
  description: string
  category: string
  tools_count: number
  status: ServiceStatus
  auth_mode: AuthMode
  auth_label: string
  auth_guide?: string
  auth_entry_url?: string
  credential_schema?: ServiceCredentialSchema | null
  user_enabled?: boolean
  call_count: number
  recent_calls_7d: number
  last_active_at: string | null
  created_at: string
}

export interface PortalToolItem {
  id?: string
  name: string
  namespace_name: string
  description: string
  risk_level: string
  requires_confirmation: boolean
  requires_credentials?: boolean
  input_schema: ToolInputSchema
}

export interface PermissionRequest {
  id: string
  user_id: string
  user_name: string
  service_id: string
  service_name: string
  tool_ids: string[]
  tool_names: string[]
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  reviewed_by?: string | null
  reviewed_at?: string | null
  comment?: string | null
}

export interface PermissionRequestCreate {
  user_id: string
  user_name?: string
  service_id: string
  tool_ids: string[]
  reason: string
  credentials?: Record<string, string>
}

export interface PermissionRequestReview {
  status: 'approved' | 'rejected'
  reviewer?: string
  comment?: string
}

export interface UserClientConfig {
  user_id: string
  token: string
  gateway_url: string
  config_templates: {
    cursor: {
      mcpServers: Record<
        string,
        {
          url: string
          headers: {
            Authorization: string
          }
        }
      >
    }
    claude: {
      mcpServers: Record<
        string,
        {
          url: string
          headers: {
            Authorization: string
          }
        }
      >
    }
  }
}

export interface PortalCapabilityDetail {
  id: string
  name: string
  description: string
  category: string
  version: string
  status: ServiceStatus
  created_at: string
  auth_mode: AuthMode
  auth_label: string
  auth_guide: string
  auth_entry_url: string
  credential_schema?: ServiceCredentialSchema | null
  usage_examples: string[]
  gateway_url: string
  protocol: string
  tools: PortalToolItem[]
  total_calls: number
  recent_calls_7d: number
  daily_trends: PortalTrendItem[]
  last_active_at: string | null
}

export interface PortalCapabilitiesQuery {
  q?: string
  category?: string
  sort_by?: 'popular' | 'recent_active' | 'newest' | 'name'
}

export interface McpBindingResponse {
  success: boolean
  message?: string
  credential_status?: CredentialStatus
}

export interface McpToggleResponse {
  status: string
  service_id: string
  user_enabled: boolean
  updated_at?: string
}

export interface PluginVersionItem {
  id: number
  plugin_id: number
  version: string
  tarball_sha256: string
  package_json: Record<string, unknown>
  changelog: string
  submit_source: 'tgz' | 'git' | string
  review_status: 'pending' | 'approved' | 'rejected' | string
  has_lifecycle_scripts: boolean
  reviewed_by: string
  review_comment: string
  published_at?: string | null
  created_at?: string | null
}

export interface PluginItem {
  id: number
  name: string
  display_name: string
  description: string
  category: string
  tags: string[]
  icon: string
  author_emp_no: string
  author_name: string
  repo_url: string
  status: 'pending' | 'published' | 'rejected' | 'deprecated' | string
  latest_version: string
  downloads: number
  sort_weight: number
  install_command?: string
  created_at?: string | null
  updated_at?: string | null
  versions?: PluginVersionItem[]
}

export interface PluginMarketListResponse {
  registry: string
  market_url: string
  categories: string[]
  items: PluginItem[]
}

