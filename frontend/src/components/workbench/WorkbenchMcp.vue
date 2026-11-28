<script setup lang="ts">
import { onScopeDispose, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  getPortalCapabilityDetail, getPortalMyMcps, togglePortalServiceEnabled, updatePortalServiceBinding,
} from '@/api/mcp'
import { AdaptiveModal, MdButton, MdCard, MdInput, MdSwitch } from '@/components/m3'
import { useAuthStore } from '@/stores/auth'
import type { CredentialFieldSchema, UserMcpDetail } from '@/types/mcp'

defineProps<{ embed?: boolean }>()
const router = useRouter()
const auth = useAuthStore()
const services = ref<UserMcpDetail[]>([])
const loading = ref(false)
const unavailable = ref(false)
const pending = ref(false)
const actionError = ref('')
const editing = ref<UserMcpDetail>()
const fields = ref<CredentialFieldSchema[]>([])
const instructions = ref('')
const form = ref<Record<string, string>>({})
let session = new AbortController()

const accountFields: CredentialFieldSchema[] = [
  { field_name: 'username', label: '业务用户名', field_type: 'text', secret: false, required: true },
  { field_name: 'password', label: '业务密码', field_type: 'password', secret: true, required: true },
]

const configured = (item: UserMcpDetail) => ['saved', 'verified', 'active'].includes(item.credential_status)
const configAction = (item: UserMcpDetail) => configured(item) ? '修改配置' : '填写配置'

function credentialText(item: UserMcpDetail) {
  const summary = item.credential_summary
  if (!item.requires_credentials) return '无需专属配置'
  if (summary?.display_label && summary?.display_value) return `${summary.display_label}：${summary.display_value}`
  if (summary?.username) return `业务账号：${summary.username}`
  return '专属配置：待填写'
}

async function load(signal = session.signal) {
  loading.value = true
  unavailable.value = false
  try {
    const items = await getPortalMyMcps(false, signal, true)
    if (!Array.isArray(items) || items.some(item => !item || typeof item.service_id !== 'string' || typeof item.service_name !== 'string')) {
      throw new Error('MCP 服务数据格式异常')
    }
    if (!signal.aborted) services.value = items
  } catch {
    if (!signal.aborted) unavailable.value = true
  } finally {
    if (!signal.aborted) loading.value = false
  }
}

watch(() => auth.empToken, token => {
  session.abort()
  session = new AbortController()
  services.value = []
  loading.value = false
  unavailable.value = false
  pending.value = false
  closeBinding()
  if (token) void load()
}, { immediate: true })

onScopeDispose(() => session.abort())

function closeBinding() {
  editing.value = undefined
  fields.value = []
  form.value = {}
  instructions.value = ''
  actionError.value = ''
}

async function discover() {
  try {
    await router.push('/capabilities')
  } catch {
    actionError.value = '无法打开能力中心，请重试'
  }
}

async function toggle(item: UserMcpDetail, enabled: boolean) {
  if (pending.value) return
  const { signal } = session
  pending.value = true
  actionError.value = ''
  try {
    const result = await togglePortalServiceEnabled(item.service_id, enabled, { signal, isolateUnauthorized: true })
    if (!signal.aborted) {
      if (typeof result?.user_enabled !== 'boolean') throw new Error('MCP 服务状态格式异常')
      services.value = services.value.map(service => service.service_id === item.service_id
        ? { ...service, user_enabled: result.user_enabled } : service)
    }
  } catch {
    if (!signal.aborted) actionError.value = '暂时无法更新 MCP 服务状态，请重试'
  } finally {
    if (!signal.aborted) pending.value = false
  }
}

async function openBinding(item: UserMcpDetail) {
  if (pending.value) return
  closeBinding()
  const { signal } = session
  pending.value = true
  try {
    const detail = await getPortalCapabilityDetail(item.service_id, signal, true)
    if (signal.aborted) return
    const schema = detail?.credential_schema
    fields.value = schema?.enabled && Array.isArray(schema.fields) && schema.fields.length
      ? schema.fields.filter(field => field && typeof field.field_name === 'string' && typeof field.label === 'string')
      : accountFields
    if (!fields.value.length) throw new Error('MCP 配置格式异常')
    instructions.value = typeof schema?.instructions === 'string' ? schema.instructions : ''
    form.value = Object.fromEntries(fields.value.map(field => {
      const saved = item.credential_summary?.[field.field_name]
      return [field.field_name, field.secret || field.field_type === 'password' || typeof saved !== 'string' ? '' : saved]
    }))
    editing.value = item
  } catch {
    if (!signal.aborted) actionError.value = '暂时无法读取 MCP 配置，请重试'
  } finally {
    if (!signal.aborted) pending.value = false
  }
}

async function saveBinding() {
  const item = editing.value
  if (!item || pending.value) return
  const { signal } = session
  const credentials: Record<string, string> = Object.create(null)
  for (const field of fields.value) {
    const secret = field.secret || field.field_type === 'password'
    const entered = form.value[field.field_name] ?? ''
    const value = secret ? entered : entered.trim()
    if (field.required && !value && !(secret && configured(item))) {
      actionError.value = `请填写${field.label}`
      return
    }
    if (value) credentials[field.field_name] = value
  }
  pending.value = true
  actionError.value = ''
  try {
    await updatePortalServiceBinding(item.service_id, credentials, { signal, isolateUnauthorized: true })
    if (signal.aborted) return
    closeBinding()
    await load(signal)
  } catch {
    if (!signal.aborted) actionError.value = '暂时无法保存 MCP 配置，请核对参数后重试'
  } finally {
    if (!signal.aborted) pending.value = false
  }
}
</script>

<template>
  <section :class="['mcp-workbench', { 'mcp-workbench--compact': embed }]" aria-label="我的 MCP 快捷装配">
    <header class="mcp-workbench__row">
      <h2>我的 MCP 快捷装配</h2>
      <MdButton variant="text" @click="discover">前往能力中心发现更多</MdButton>
    </header>
    <p v-if="unavailable" class="mcp-workbench__hint" role="status">
      MCP 能力暂不可用 <MdButton variant="text" :disabled="loading || pending" @click="load()">重试</MdButton>
    </p>
    <p v-else-if="loading && !services.length" class="mcp-workbench__hint" role="status">正在加载 MCP 服务…</p>
    <p v-else-if="!services.length" class="mcp-workbench__hint">暂无已开通的 MCP 服务。</p>
    <p v-if="actionError && !editing" class="mcp-workbench__error" role="alert">{{ actionError }}</p>

    <template v-if="!unavailable">
      <MdCard v-for="service in services" :key="service.service_id" variant="filled">
        <div class="mcp-workbench__row">
          <div>
            <h3>{{ service.service_name }}</h3>
            <p class="mcp-workbench__hint">{{ credentialText(service) }}</p>
          </div>
          <div class="mcp-workbench__actions">
            <MdButton v-if="service.requires_credentials" variant="tonal" :disabled="pending || loading"
              :aria-label="`${configAction(service)} ${service.service_name}`"
              @click="openBinding(service)">{{ configAction(service) }}</MdButton>
            <MdSwitch :model-value="service.user_enabled !== false" :disabled="pending || loading"
              :aria-label="`启用 ${service.service_name}`"
              @update:model-value="enabled => toggle(service, enabled)" />
          </div>
        </div>
      </MdCard>
    </template>

    <AdaptiveModal :model-value="!!editing" :title="editing ? configAction(editing) : '个人配置'"
      @update:model-value="!pending && closeBinding()">
      <form id="workbench-mcp-binding" class="mcp-workbench__form" @submit.prevent="saveBinding">
        <strong>{{ editing?.service_name }}</strong>
        <p v-if="instructions" class="mcp-workbench__hint">{{ instructions }}</p>
        <label v-for="field in fields" :key="field.field_name">
          {{ field.label }}
          <MdInput v-model="form[field.field_name]" :type="field.secret || field.field_type === 'password' ? 'password' : 'text'"
            :placeholder="field.placeholder" :disabled="pending" />
          <small v-if="field.description" class="mcp-workbench__hint">{{ field.description }}</small>
        </label>
        <p v-if="actionError" class="mcp-workbench__error" role="alert">{{ actionError }}</p>
      </form>
      <template #actions>
        <MdButton variant="text" :disabled="pending" @click="closeBinding">取消</MdButton>
        <MdButton type="submit" form="workbench-mcp-binding" :disabled="pending">{{ pending ? '保存中…' : '保存' }}</MdButton>
      </template>
    </AdaptiveModal>
  </section>
</template>

<style scoped>
.mcp-workbench { display: grid; gap: 10px; min-width: 0; }
.mcp-workbench--compact { --md-card-padding: 12px; }
.mcp-workbench__row, .mcp-workbench__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.mcp-workbench__row { justify-content: space-between; overflow-wrap: anywhere; }
.mcp-workbench h2 { font-size: 1.25rem; }
.mcp-workbench h3 { font-size: 1rem; margin-bottom: 4px; }
.mcp-workbench__hint { color: var(--md-sys-color-on-surface-variant); }
.mcp-workbench__error { color: var(--md-sys-color-error); }
.mcp-workbench__form, .mcp-workbench__form label { display: grid; gap: 6px; }
.mcp-workbench__form { gap: 14px; }
</style>
