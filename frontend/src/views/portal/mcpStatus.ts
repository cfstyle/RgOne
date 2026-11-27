export interface McpStatusDisplayInput {
  requires_credentials: boolean
  credential_status: string
  service_status?: string
  downstream_status?: string
  approved_tools?: string[]
  pending_tools?: string[]
}

export type McpStatusTone = 'danger' | 'success' | 'primary' | 'warning' | 'neutral'

export function isServiceUnavailable(item: McpStatusDisplayInput): boolean {
  return (
    item.downstream_status === 'unavailable' ||
    item.service_status === 'degraded' ||
    item.service_status === 'inactive'
  )
}

export function getMyMcpStatusTone(item: McpStatusDisplayInput): McpStatusTone {
  if (isServiceUnavailable(item)) {
    return 'danger'
  }
  if (item.requires_credentials) {
    if (item.credential_status === 'invalid' || item.credential_status === 'unbound') {
      return 'danger'
    }
    if (item.credential_status === 'verified' && (item.approved_tools?.length ?? 0) > 0) {
      return 'success'
    }
    if (item.credential_status === 'saved') {
      return 'primary'
    }
    if ((item.approved_tools?.length ?? 0) > 0) {
      return 'warning'
    }
    if ((item.pending_tools?.length ?? 0) > 0) {
      return 'primary'
    }
    return 'neutral'
  }
  if ((item.approved_tools?.length ?? 0) > 0) {
    return 'success'
  }
  return 'primary'
}

export function getMyMcpStatusLabel(item: McpStatusDisplayInput): string {
  if (isServiceUnavailable(item)) {
    return '下游不可用'
  }
  if (item.requires_credentials) {
    if (item.credential_status === 'invalid') {
      return '登录失效'
    }
    if (item.credential_status === 'unbound') {
      return '凭据已解绑（调用已阻断）'
    }
    if (item.credential_status === 'verified') {
      if ((item.pending_tools?.length ?? 0) > 0 && (item.approved_tools?.length ?? 0) === 0) {
        return '审批中（已验证）'
      }
      return '已验证'
    }
    if (item.credential_status === 'saved') {
      if ((item.pending_tools?.length ?? 0) > 0 && (item.approved_tools?.length ?? 0) === 0) {
        return '已保存（审批中）'
      }
      return '已保存'
    }
    if ((item.approved_tools?.length ?? 0) > 0) {
      return '已批准，待配置凭据'
    }
    if ((item.pending_tools?.length ?? 0) > 0) {
      return '审批中'
    }
    return '待绑定凭据'
  }
  if ((item.approved_tools?.length ?? 0) > 0) {
    return '可使用'
  }
  return '审批中'
}

export interface PortalToolCredentialRef {
  id?: string
  name: string
  namespace_name?: string
  risk_level?: string
  requires_credentials?: boolean
}

export interface CredentialSchemaFieldLike {
  field_name: string
  label: string
  required?: boolean
}

export interface CapabilityDetailForApply {
  id: string
  credential_schema?: {
    enabled?: boolean
    fields?: CredentialSchemaFieldLike[]
  } | null
  tools?: PortalToolCredentialRef[]
}

/** 判断当前勾选拟申请的工具中，是否有至少一个工具实际需要绑定个人业务凭据 */
export function selectedToolsRequireCredentials(
  detail: CapabilityDetailForApply | null | undefined,
  selectedToolIds: Set<string> | string[]
): boolean {
  if (!detail?.credential_schema?.enabled) return false
  const selectedSet = selectedToolIds instanceof Set ? selectedToolIds : new Set(selectedToolIds)
  if (selectedSet.size === 0) return false
  const tools = detail.tools || []
  return tools.some((tool) => {
    const tid = tool.id || tool.namespace_name || tool.name
    return selectedSet.has(tid) && Boolean(tool.requires_credentials)
  })
}

export function validateCredentialFormForSelectedTools(
  detail: CapabilityDetailForApply | null | undefined,
  selectedToolIds: Set<string> | string[],
  hasExistingBinding: boolean,
  showCustomCredInApply: boolean,
  credentialForm: Record<string, string>
): { valid: boolean; missingFieldLabel?: string } {
  if (!selectedToolsRequireCredentials(detail, selectedToolIds)) {
    return { valid: true }
  }
  if (hasExistingBinding && !showCustomCredInApply) {
    return { valid: true }
  }
  for (const field of detail?.credential_schema?.fields || []) {
    if (field.required && !(credentialForm[field.field_name] || '').trim()) {
      return { valid: false, missingFieldLabel: field.label }
    }
  }
  return { valid: true }
}

export function buildPermissionRequestPayload(params: {
  userId: string
  userName?: string
  detail: CapabilityDetailForApply
  selectedToolIds: Set<string> | string[]
  reason: string
  hasExistingBinding: boolean
  showCustomCredInApply: boolean
  credentialForm: Record<string, string>
}): {
  user_id: string
  user_name?: string
  service_id: string
  tool_ids: string[]
  reason: string
  credentials?: Record<string, string>
} {
  const toolIds = Array.from(params.selectedToolIds)
  const payload: {
    user_id: string
    user_name?: string
    service_id: string
    tool_ids: string[]
    reason: string
    credentials?: Record<string, string>
  } = {
    user_id: params.userId,
    user_name: params.userName,
    service_id: params.detail.id,
    tool_ids: toolIds,
    reason: params.reason.trim(),
  }

  if (
    selectedToolsRequireCredentials(params.detail, toolIds) &&
    (!params.hasExistingBinding || params.showCustomCredInApply)
  ) {
    payload.credentials = { ...params.credentialForm }
  }

  return payload
}
