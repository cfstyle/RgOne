export type ServiceStatus = 'active' | 'inactive' | 'degraded' | 'pending'

export type RiskLevel = 'L0' | 'L1' | 'L2' | 'L3'

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
  help_text?: string
}

export interface McpService {
  id: string
  name: string
  description: string
  endpoint_url: string
  version: string
  owner: string
  status: ServiceStatus
  category?: string
  auth_mode?: AuthMode
  auth_label?: string
  auth_guide?: string
  auth_entry_url?: string
  usage_examples?: string[]
  credential_schema?: ServiceCredentialSchema | null
  trusted_credential_recipient?: boolean
  trusted_credential_version?: string | null
  trusted_credential_endpoint_url?: string | null
  trusted_confirmed_by?: string | null
  trusted_confirmed_at?: string | null
  downstream_status?: 'available' | 'unavailable' | string
  downstream_error?: string | null
  created_at: string
  updated_at: string
  tools_count?: number
}

export interface ServiceRegistrationRequest {
  service_id: string
  name: string
  endpoint_url: string
  version?: string
  description?: string
  owner?: string
  category?: string
  auth_mode?: AuthMode
  auth_label?: string
  auth_guide?: string
  auth_entry_url?: string
  usage_examples?: string[]
  credential_schema?: ServiceCredentialSchema | null
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
}

export interface RefreshResponse {
  service_id: string
  tools_discovered: number
  status: string
}

export interface ConnectionTestResponse {
  service_id: string
  endpoint_url?: string
  success: boolean
  latency_ms: number
  tools_count?: number
  error?: string
  message: string
}

export interface RegisteredTool {
  id: string
  service_id: string
  name: string
  namespace_name: string
  description: string
  input_schema: ToolInputSchema
  risk_level: RiskLevel
  requires_confirmation: boolean
  requires_credentials?: boolean
  created_at?: string
}

export interface ToolPolicyUpdateRequest {
  risk_level: RiskLevel
  requires_confirmation: boolean
}

export interface ToolExecuteRequest {
  arguments: Record<string, unknown>
}

export interface ToolExecuteResponse {
  tool_name: string
  service_id: string
  status: 'success' | 'tool_error' | 'exception'
  duration_ms: number
  result?: unknown
  error?: string
}

export interface PortalTrendItem {
  date: string
  calls: number
  success_calls: number
}

export interface DashboardSummary {
  servers_total: number
  servers_active: number
  servers_inactive: number
  servers_degraded: number
  tools_total: number
  calls_total: number
  calls_success: number
  calls_failed: number
  health_rate?: number
  daily_trends?: PortalTrendItem[]
}

export interface AuditLog {
  id: string
  timestamp: string
  user_id: string
  client_id: string
  service_id: string
  tool_name: string
  params_summary: Record<string, unknown>
  result_status: string
  duration_ms: number
  client_ip?: string
  trace_id?: string
}

export interface AuditLogsResponse {
  items: AuditLog[]
  total: number
}

export interface AuditLogsParams {
  service_id?: string
  tool_name?: string
  status?: string
  limit?: number
  offset?: number
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
  valid: boolean
  service_id: string
  name: string
  version: string
  description: string
  author: string
  port: number
  tools: Array<{
    name: string
    description?: string
    risk_level?: string
    requires_credentials?: boolean
  }>
  file_count: number
  prefix: string
  manifest: Record<string, unknown>
}

export interface DeveloperGuideResponse {
  content: string
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

