<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { AlertTriangle, CheckCircle2, Copy, Play, RefreshCw, XCircle } from 'lucide-vue-next'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import MdSelect, { type SelectOption } from '@/components/m3/MdSelect.vue'
import MdSwitch from '@/components/m3/MdSwitch.vue'
import { useToast } from '@/composables/useToast'
import { copyToClipboard } from '@/utils/clipboard'
import {
  executeTool,
  getMcpErrorMessage,
  getServices,
  isMcpEngineUnavailable,
  listTools,
} from '@/api/mcp'
import type { McpService, RegisteredTool, ToolExecuteResponse } from '@/types/mcp'
import { formatDebugResponse, highlightDebugJson } from './responseFormat'

interface SchemaProperty {
  type?: string
  description?: string
  default?: unknown
  enum?: Array<string | number>
}

const props = defineProps<{
  initialServiceId?: string
  initialToolName?: string
}>()

const emit = defineEmits<{
  (e: 'engine-error', message: string): void
}>()

const toast = useToast()
const services = ref<McpService[]>([])
const tools = ref<RegisteredTool[]>([])
const selectedServiceId = ref('')
const selectedToolName = ref('')
const inputMode = ref<'form' | 'json'>('form')
const rawJsonArgs = ref('{}')
const formArgs = reactive<Record<string, unknown>>({})
const confirmed = ref(false)
const executing = ref(false)
const execResponse = ref<ToolExecuteResponse | null>(null)

let abortController: AbortController | null = null

const serviceTools = computed(() =>
  tools.value.filter((t) => !selectedServiceId.value || t.service_id === selectedServiceId.value)
)

const serviceOptions = computed<SelectOption[]>(() => [
  { label: '请选择服务', value: '' },
  ...services.value.map((svc) => ({ label: svc.name, value: svc.id })),
])

const toolOptions = computed<SelectOption[]>(() => [
  { label: '请选择工具', value: '' },
  ...serviceTools.value.map((t) => ({ label: `${t.name} (${t.risk_level})`, value: t.name })),
])

function buildEnumOptions(values?: unknown[]): SelectOption[] {
  const base: SelectOption[] = [{ label: '请选择', value: '' }]
  if (!values?.length) return base
  return [
    ...base,
    ...values.map((opt) => ({
      label: String(opt),
      value: typeof opt === 'number' ? opt : String(opt),
    })),
  ]
}

const currentTool = computed<RegisteredTool | undefined>(() =>
  tools.value.find(
    (t) => t.service_id === selectedServiceId.value && t.name === selectedToolName.value
  )
)

const schemaProperties = computed<Record<string, SchemaProperty>>(() => {
  const schema = currentTool.value?.input_schema
  if (schema && typeof schema.properties === 'object' && schema.properties !== null) {
    return schema.properties as Record<string, SchemaProperty>
  }
  return {}
})

const requiredFields = computed<Set<string>>(() => {
  const schema = currentTool.value?.input_schema
  if (schema && Array.isArray(schema.required)) {
    return new Set(schema.required.map((v) => String(v)))
  }
  return new Set()
})

const needsSafetyConfirm = computed(() => {
  if (!currentTool.value) return false
  return (
    currentTool.value.requires_confirmation ||
    currentTool.value.risk_level === 'L2' ||
    currentTool.value.risk_level === 'L3'
  )
})

const formattedResponseText = computed(() => {
  if (!execResponse.value) return ''
  return formatDebugResponse(execResponse.value.result ?? execResponse.value)
})

const highlightedResponseHtml = computed(() =>
  highlightDebugJson(formattedResponseText.value)
)

function resetToolArgs(tool: RegisteredTool | undefined) {
  for (const key of Object.keys(formArgs)) {
    delete formArgs[key]
  }
  const defaults: Record<string, unknown> = {}
  const propsObj =
    tool?.input_schema && typeof tool.input_schema.properties === 'object'
      ? (tool.input_schema.properties as Record<string, SchemaProperty>)
      : {}
  for (const [key, prop] of Object.entries(propsObj)) {
    if (prop.default !== undefined) {
      formArgs[key] = prop.default
      defaults[key] = prop.default
    } else if (prop.type === 'boolean') {
      formArgs[key] = false
    } else if (prop.type === 'number' || prop.type === 'integer') {
      formArgs[key] = 0
    } else if (prop.type === 'array' || prop.type === 'object') {
      formArgs[key] = prop.type === 'array' ? '[]' : '{}'
    } else {
      formArgs[key] = ''
    }
  }
  rawJsonArgs.value = JSON.stringify(defaults, null, 2)
  confirmed.value = false
  execResponse.value = null
}

function buildArguments(): Record<string, unknown> {
  if (inputMode.value === 'json') {
    const parsed = JSON.parse(rawJsonArgs.value || '{}') as unknown
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      throw new Error('JSON 参数必须是对象格式')
    }
    return parsed as Record<string, unknown>
  }

  const out: Record<string, unknown> = {}
  for (const [key, prop] of Object.entries(schemaProperties.value)) {
    const val = formArgs[key]
    if (val === '' || val === undefined) continue
    if (prop.type === 'number' || prop.type === 'integer') {
      const n = Number(val)
      if (!Number.isNaN(n)) out[key] = n
    } else if (prop.type === 'array' || prop.type === 'object') {
      if (typeof val === 'string') {
        out[key] = JSON.parse(val) as unknown
      } else {
        out[key] = val
      }
    } else {
      out[key] = val
    }
  }
  return out
}

async function handleExecute() {
  if (!selectedServiceId.value || !selectedToolName.value || !currentTool.value) {
    toast.warning('请先选择目标服务和工具')
    return
  }
  if (needsSafetyConfirm.value && !confirmed.value) {
    toast.warning('此工具涉及高风险操作，请先勾选安全确认')
    return
  }

  let args: Record<string, unknown>
  try {
    args = buildArguments()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '参数解析失败'))
    return
  }

  const toolId =
    currentTool.value.id ||
    currentTool.value.namespace_name ||
    `${selectedServiceId.value}__${selectedToolName.value}`

  executing.value = true
  try {
    execResponse.value = await executeTool(toolId, args)
    if (execResponse.value.status === 'success') {
      toast.success(`执行成功 (${execResponse.value.duration_ms} ms)`)
    } else {
      toast.warning(execResponse.value.error || `执行返回状态: ${execResponse.value.status}`)
    }
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '执行调用失败'))
  } finally {
    executing.value = false
  }
}

async function loadMeta() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  try {
    const [svcRes, toolRes] = await Promise.all([
      getServices(undefined, abortController.signal),
      listTools(undefined, abortController.signal),
    ])
    services.value = svcRes
    tools.value = toolRes
    if (props.initialServiceId) {
      selectedServiceId.value = props.initialServiceId
    } else if (!selectedServiceId.value && svcRes[0]) {
      selectedServiceId.value = svcRes[0].id
    }
    if (props.initialToolName) {
      selectedToolName.value = props.initialToolName
    } else if (!selectedToolName.value) {
      const first = toolRes.find((t) => t.service_id === selectedServiceId.value)
      if (first) selectedToolName.value = first.name
    }
    resetToolArgs(currentTool.value)
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = getMcpErrorMessage(err, '加载调试元数据失败')
    if (isMcpEngineUnavailable(err)) emit('engine-error', msg)
    else toast.error(msg)
  }
}

watch(
  () => [props.initialServiceId, props.initialToolName],
  ([sid, tname]) => {
    if (sid) selectedServiceId.value = sid
    if (tname) selectedToolName.value = tname
    resetToolArgs(currentTool.value)
  }
)

watch(currentTool, (tool) => {
  resetToolArgs(tool)
})

onMounted(() => {
  void loadMeta()
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="mcp-debug-tab">
    <div class="debug-grid">
      <MdCard variant="elevated">
        <div class="card-head">
          <h3>调用参数配置</h3>
          <MdButton variant="text" @click="loadMeta">
            <RefreshCw :size="14" />
            <span>重载契约</span>
          </MdButton>
        </div>

        <div class="form-stack">
          <div class="form-item">
            <label class="form-label">目标服务</label>
            <MdSelect v-model="selectedServiceId" :options="serviceOptions" style="width: 100%" />
          </div>

          <div class="form-item">
            <label class="form-label">目标工具</label>
            <MdSelect v-model="selectedToolName" :options="toolOptions" style="width: 100%" />
          </div>

          <div class="mode-switch">
            <button
              type="button"
              :class="['mode-btn', { 'is-active': inputMode === 'form' }]"
              @click="inputMode = 'form'"
            >
              动态表单模式
            </button>
            <button
              type="button"
              :class="['mode-btn', { 'is-active': inputMode === 'json' }]"
              @click="inputMode = 'json'"
            >
              JSON 源码模式
            </button>
          </div>

          <div v-if="inputMode === 'form'" class="dynamic-form">
            <div v-if="!Object.keys(schemaProperties).length" class="empty-inline">
              当前工具无参数或未声明 properties
            </div>
            <div v-for="(prop, key) in schemaProperties" :key="key" class="form-item">
              <label class="form-label">
                {{ key }}
                <span v-if="requiredFields.has(key)" class="required-mark">*</span>
                <span class="prop-type">({{ prop.type || 'string' }})</span>
              </label>
              <MdSelect
                v-if="prop.enum?.length"
                :model-value="formArgs[key] === undefined ? '' : (formArgs[key] as string | number)"
                :options="buildEnumOptions(prop.enum)"
                style="width: 100%"
                @update:model-value="(val) => (formArgs[key] = val)"
              />
              <div v-else-if="prop.type === 'boolean'" class="bool-row">
                <span>{{ prop.description || key }}</span>
                <MdSwitch
                  :model-value="Boolean(formArgs[key])"
                  @update:model-value="(v) => (formArgs[key] = v)"
                />
              </div>
              <textarea
                v-else-if="prop.type === 'object' || prop.type === 'array'"
                :value="String(formArgs[key] ?? '')"
                rows="3"
                class="form-textarea mono"
                :placeholder="prop.description || '请输入 JSON'"
                @input="formArgs[key] = ($event.target as HTMLTextAreaElement).value"
              ></textarea>
              <input
                v-else
                :value="String(formArgs[key] ?? '')"
                :type="prop.type === 'number' || prop.type === 'integer' ? 'number' : 'text'"
                :placeholder="prop.description || `请输入 ${key}`"
                class="form-input"
                @input="formArgs[key] = ($event.target as HTMLInputElement).value"
              />
            </div>
          </div>

          <div v-else class="form-item">
            <label class="form-label">Arguments JSON</label>
            <textarea v-model="rawJsonArgs" rows="8" class="form-textarea mono"></textarea>
          </div>

          <div v-if="needsSafetyConfirm" class="safety-box">
            <AlertTriangle :size="16" />
            <label class="confirm-label">
              <MdSwitch v-model="confirmed" />
              <span>已知悉该工具为受控/高风险等级（{{ currentTool?.risk_level }}），确认受控执行</span>
            </label>
          </div>

          <MdButton variant="filled" :disabled="executing" @click="handleExecute">
            <Play :size="15" />
            <span>{{ executing ? '执行中...' : '发起测试调用' }}</span>
          </MdButton>
        </div>
      </MdCard>

      <MdCard variant="elevated">
        <div class="card-head">
          <div class="resp-title">
            <h3>调用响应结果</h3>
            <span v-if="execResponse" class="latency-pill">
              <CheckCircle2 v-if="execResponse.status === 'success'" :size="13" />
              <XCircle v-else :size="13" />
              <span>{{ execResponse.status }} · {{ execResponse.duration_ms }} ms</span>
            </span>
          </div>
          <MdButton
            v-if="execResponse"
            variant="text"
            @click="copyToClipboard(formattedResponseText)"
          >
            <Copy :size="14" />
            <span>复制结果</span>
          </MdButton>
        </div>

        <div v-if="!execResponse" class="empty-inline">选择服务与工具并点击「发起测试调用」查看输出</div>
        <div v-else class="resp-body">
          <div v-if="execResponse.error" class="error-banner">{{ execResponse.error }}</div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <pre class="resp-pre"><code v-html="highlightedResponseHtml"></code></pre>
        </div>
      </MdCard>
    </div>
  </div>
</template>

<style scoped>
.debug-grid {
  display: grid;
  grid-template-columns: 1fr 1.15fr;
  gap: 16px;
}

@media (max-width: 1020px) {
  .debug-grid {
    grid-template-columns: 1fr;
  }
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}

.card-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.form-stack,
.dynamic-form,
.resp-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.required-mark {
  color: var(--md-sys-color-error);
}

.prop-type {
  font-weight: 400;
  color: var(--md-sys-color-on-surface-variant);
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

.mode-switch {
  display: flex;
  gap: 6px;
}

.mode-btn {
  padding: 6px 12px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 12px;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.mode-btn.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}

.bool-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.safety-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
  font-size: 12px;
}

.confirm-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.resp-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.latency-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  background-color: var(--md-sys-color-surface-container-high);
}

.error-banner {
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
  font-size: 13px;
}

.resp-pre {
  margin: 0;
  padding: 14px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  overflow: auto;
  max-height: 520px;
}

.resp-pre :deep(.json-key) {
  color: var(--md-sys-color-primary);
  font-weight: 600;
}

.resp-pre :deep(.json-string) {
  color: var(--sys-status-success-text);
}

.resp-pre :deep(.json-number),
.resp-pre :deep(.json-boolean) {
  color: var(--sys-status-warning-text);
}

.resp-pre :deep(.json-null) {
  color: var(--md-sys-color-on-surface-variant);
}

.empty-inline {
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
