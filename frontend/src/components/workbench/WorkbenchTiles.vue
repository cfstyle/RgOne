<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, ExternalLink, EyeOff, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { AdaptiveModal, MdButton, MdCard, MdSwitch, useToast } from '@/components/m3'
import { safeTileLink, tileIcons, workbenchApi, type TileDraft, type TileList, type WorkbenchTile } from '@/api/workbench'
import { useAuthStore } from '@/stores/auth'
import { copyToClipboard } from '@/utils/clipboard'
import TileEditor from './TileEditor.vue'

const props = defineProps<{ admin?: boolean; embed?: boolean }>()
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()
const data = ref<TileList>({ tiles: [], hidden_presets: [] })
const personal = computed(() => data.value.tiles.filter(tile => tile.owner_emp_no !== null))
const loading = ref(false)
const busy = ref(false)
const loadError = ref('')
const actionError = ref('')
const editing = ref<{ tile?: WorkbenchTile }>()
const deleting = ref<WorkbenchTile>()
const showingHidden = ref(false)
let session = new AbortController()

async function load(signal = session.signal) {
  loading.value = true
  loadError.value = ''
  try {
    const result = await workbenchApi.list(!!props.admin, signal)
    if (!signal.aborted) data.value = result
  } catch {
    if (!signal.aborted) loadError.value = '磁贴加载失败，请重试'
  } finally {
    if (!signal.aborted) loading.value = false
  }
}

watch(() => props.admin ? auth.adminToken : auth.empToken, token => {
  session.abort()
  session = new AbortController()
  data.value = { tiles: [], hidden_presets: [] }
  editing.value = undefined
  deleting.value = undefined
  showingHidden.value = false
  busy.value = false
  loading.value = false
  loadError.value = ''
  actionError.value = ''
  if (token) void load()
}, { immediate: true })

onScopeDispose(() => session.abort())

async function change(
  send: (signal: AbortSignal) => Promise<unknown>, failure: string, success?: () => void,
) {
  if (busy.value || loading.value) return
  const { signal } = session
  busy.value = true
  actionError.value = ''
  try {
    await send(signal)
    if (signal.aborted) return
    success?.()
    await load(signal)
  } catch {
    if (!signal.aborted) actionError.value = failure
  } finally {
    if (!signal.aborted) busy.value = false
  }
}

function openEditor(tile?: WorkbenchTile) {
  actionError.value = ''
  editing.value = { tile }
}

function openDelete(tile: WorkbenchTile) {
  actionError.value = ''
  deleting.value = tile
}

function save(draft: TileDraft) {
  const id = editing.value?.tile?.id
  void change(signal => workbenchApi.save(!!props.admin, signal, draft, id), '保存失败，请检查磁贴内容后重试', () => {
    editing.value = undefined
    toast.success('磁贴已保存')
  })
}

function remove() {
  const tile = deleting.value
  if (!tile) return
  void change(signal => workbenchApi.remove(!!props.admin, tile.id, signal), '删除失败，请重试', () => {
    deleting.value = undefined
  })
}

function move(tile: WorkbenchTile, step: -1 | 1) {
  const nextOrder = [...personal.value]
  const index = nextOrder.findIndex(item => item.id === tile.id)
  const neighbor = nextOrder[index + step]
  if (index < 0 || !neighbor) return
  nextOrder[index] = neighbor
  nextOrder[index + step] = tile
  const items = nextOrder.flatMap((item, sort_order) => item.sort_order === sort_order ? [] : [{ id: item.id, sort_order }])
  void change(signal => workbenchApi.reorder(items, signal), '排序失败，请重试')
}

async function activate(tile: WorkbenchTile) {
  if (tile.tile_type === 'prompt') {
    if (props.embed) window.parent.postMessage({ type: 'RGONE_INSERT_PROMPT', title: tile.title, prompt: tile.payload }, '*')
    if (await copyToClipboard(tile.payload)) toast.success('提示词已复制，可直接粘贴到 DSH 对话')
    return
  }
  const link = safeTileLink(tile.payload)
  if (!link) {
    toast.error('磁贴链接无效')
    return
  }
  try {
    if (link.internal) await router.push(link.url)
    else window.open(link.url, '_blank', 'noopener,noreferrer')
  } catch {
    toast.error('无法打开磁贴链接')
  }
}
</script>

<template>
  <section :class="['tiles', { 'tiles--compact': embed }]" :aria-label="admin ? '全行推荐磁贴' : '业务磁贴'">
    <header class="tiles__header">
      <h2>{{ admin ? '全行推荐磁贴' : '业务磁贴' }}</h2>
      <div class="tiles__actions">
        <MdButton v-if="!admin" variant="text" :disabled="loading || busy" @click="actionError = ''; showingHidden = true">
          恢复隐藏预置<span v-if="data.hidden_presets.length">（{{ data.hidden_presets.length }}）</span>
        </MdButton>
        <MdButton :disabled="loading || busy" @click="openEditor()">
          <template #icon><Plus :size="18" /></template>
          新增磁贴
        </MdButton>
      </div>
    </header>

    <p v-if="loadError" role="status">
      {{ loadError }} <MdButton variant="text" :disabled="loading || busy" @click="load()">重试</MdButton>
    </p>
    <p v-else-if="loading && !data.tiles.length" role="status">正在加载磁贴…</p>
    <p v-else-if="!data.tiles.length">{{ admin ? '暂无全行推荐磁贴' : '暂无业务磁贴' }}</p>
    <p v-if="actionError && !editing && !deleting && !showingHidden" class="tiles__error" role="alert">{{ actionError }}</p>

    <div class="tiles__grid">
      <MdCard v-for="tile in data.tiles" :key="tile.id" :variant="tile.owner_emp_no === null ? 'tonal' : 'elevated'">
        <div class="tiles__metadata">
          <span v-if="!admin && tile.owner_emp_no === null" class="tiles__badge">推荐</span>
          <span v-if="tile.category">{{ tile.category }}</span>
          <span>{{ tile.tile_type === 'prompt' ? '提示词' : '直达链接' }}</span>
          <span v-if="!tile.is_enabled">已停用</span>
          <span v-if="admin">排序 {{ tile.sort_order }}</span>
        </div>
        <button v-if="!admin" type="button" class="tiles__launch md-state-layer"
          :disabled="!tile.is_enabled" @click="activate(tile)">
          <component :is="tileIcons[tile.icon]" :size="22" aria-hidden="true" />
          <span><strong>{{ tile.title }}</strong><small v-if="tile.subtitle">{{ tile.subtitle }}</small></span>
          <ExternalLink v-if="tile.tile_type === 'link'" :size="16" aria-hidden="true" />
        </button>
        <div v-else class="tiles__launch">
          <component :is="tileIcons[tile.icon]" :size="22" aria-hidden="true" />
          <div><h3>{{ tile.title }}</h3><small v-if="tile.subtitle">{{ tile.subtitle }}</small></div>
        </div>
        <div class="tiles__actions">
          <template v-if="!admin && tile.owner_emp_no === null">
            <MdButton variant="text" :disabled="busy || loading" :aria-label="`隐藏 ${tile.title}`"
              @click="change(signal => workbenchApi.setHidden(tile.id, true, signal), '隐藏失败，请重试')">
              <template #icon><EyeOff :size="16" /></template>隐藏
            </MdButton>
          </template>
          <template v-else>
            <MdSwitch v-if="admin" :model-value="tile.is_enabled" :disabled="busy || loading"
              :aria-label="`启用 ${tile.title}`"
              @update:model-value="enabled => change(signal => workbenchApi.save(true, signal, { is_enabled: enabled }, tile.id), '启停失败，请重试')"
            />
            <MdButton variant="text" :disabled="busy || loading" :aria-label="`编辑 ${tile.title}`" @click="openEditor(tile)">
              <Pencil :size="17" />
            </MdButton>
            <template v-if="!admin">
              <MdButton variant="text" :disabled="busy || loading || personal[0]?.id === tile.id"
                :aria-label="`上移 ${tile.title}`" @click="move(tile, -1)"><ArrowUp :size="17" /></MdButton>
              <MdButton variant="text" :disabled="busy || loading || personal.at(-1)?.id === tile.id"
                :aria-label="`下移 ${tile.title}`" @click="move(tile, 1)"><ArrowDown :size="17" /></MdButton>
            </template>
            <MdButton variant="text" :disabled="busy || loading" :aria-label="`删除 ${tile.title}`" @click="openDelete(tile)">
              <Trash2 :size="17" />
            </MdButton>
          </template>
        </div>
      </MdCard>
    </div>

    <TileEditor v-if="editing" :tile="editing.tile" :admin="admin" :busy="busy" :error="actionError"
      @close="editing = undefined; actionError = ''" @save="save" />

    <AdaptiveModal :model-value="!!deleting" title="删除磁贴"
      @update:model-value="!busy && (deleting = undefined, actionError = '')">
      <p>确定删除「{{ deleting?.title }}」？</p>
      <p v-if="actionError" class="tiles__error" role="alert">{{ actionError }}</p>
      <template #actions>
        <MdButton variant="text" :disabled="busy" @click="deleting = undefined; actionError = ''">取消</MdButton>
        <MdButton :disabled="busy" @click="remove">{{ busy ? '删除中…' : '删除' }}</MdButton>
      </template>
    </AdaptiveModal>

    <AdaptiveModal v-model="showingHidden" title="已隐藏的预置磁贴">
      <p v-if="!data.hidden_presets.length">暂无已隐藏的预置磁贴。</p>
      <p v-if="actionError" class="tiles__error" role="alert">{{ actionError }}</p>
      <div v-for="tile in data.hidden_presets" :key="tile.id" class="tiles__hidden">
        <span>{{ tile.title }}<small v-if="!tile.is_enabled">（全行已停用）</small></span>
        <MdButton variant="tonal" :disabled="busy || loading" :aria-label="`恢复 ${tile.title}`"
          @click="change(signal => workbenchApi.setHidden(tile.id, false, signal), '恢复失败，请重试')">恢复</MdButton>
      </div>
      <template #actions>
        <MdButton variant="text" @click="showingHidden = false; actionError = ''">关闭</MdButton>
      </template>
    </AdaptiveModal>
  </section>
</template>

<style scoped>
.tiles { display: grid; gap: 14px; min-width: 0; }
.tiles--compact { --md-card-padding: 12px; }
.tiles h2 { font-size: 1.25rem; }
.tiles h3 { font-size: 1rem; }
.tiles__header, .tiles__metadata, .tiles__actions, .tiles__hidden {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.tiles__header, .tiles__hidden { justify-content: space-between; }
.tiles__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(250px, 100%), 1fr)); gap: 12px; }
.tiles--compact .tiles__grid { grid-template-columns: repeat(auto-fit, minmax(min(195px, 100%), 1fr)); }
.tiles__metadata { color: var(--md-sys-color-on-surface-variant); font-size: .8rem; overflow-wrap: anywhere; }
.tiles__badge {
  background: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
  border-radius: var(--md-sys-shape-corner-full);
  padding: 2px 8px;
}
.tiles__launch {
  display: flex;
  align-items: center;
  text-align: start;
  gap: 10px;
  width: 100%;
  min-height: 44px;
  padding: 8px 0;
  margin: 4px 0;
  overflow-wrap: anywhere;
  border-radius: var(--md-sys-shape-corner-small);
}
.tiles__launch svg { flex: none; }
.tiles__launch small { display: block; color: var(--md-sys-color-on-surface-variant); }
button.tiles__launch:disabled { cursor: default; opacity: .65; }
.tiles__actions :deep(.m3-button) { min-height: 44px; }
.tiles__actions :deep(.m3-button[aria-label]) { min-width: 44px; padding-inline: 10px; }
.tiles__hidden { padding-block: 6px; }
.tiles__error { color: var(--md-sys-color-error); }
</style>
