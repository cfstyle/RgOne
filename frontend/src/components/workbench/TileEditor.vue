<script setup lang="ts">
import { computed, ref } from 'vue'
import { AdaptiveModal, MdButton, MdInput, MdSelect, MdSwitch } from '@/components/m3'
import { newTile, safeTileLink, tileIcons, type TileDraft, type WorkbenchTile } from '@/api/workbench'

const props = defineProps<{ tile?: WorkbenchTile; admin?: boolean; busy: boolean; error: string }>()
const emit = defineEmits<{ close: []; save: [draft: TileDraft] }>()
const tile = props.tile
const draft = ref<TileDraft>(tile ? {
  title: tile.title, subtitle: tile.subtitle, tile_type: tile.tile_type, icon: tile.icon,
  payload: tile.payload, category: tile.category, sort_order: tile.sort_order, is_enabled: tile.is_enabled,
} : newTile())
const iconOptions = Object.keys(tileIcons).map(value => ({ label: value, value }))
const typeOptions = [{ label: '快捷提示词', value: 'prompt' }, { label: '系统直达链接', value: 'link' }]
const order = ref(String(draft.value.sort_order))
const category = ref(draft.value.category ?? '')
const validation = ref('')
const title = computed(() => `${tile ? '编辑' : '新增'}${props.admin ? '推荐' : ''}磁贴`)

function submit() {
  const values = draft.value
  const sortOrder = order.value.trim() ? Number(order.value) : 0
  if (!values.title.trim() || !values.payload.trim()) {
    validation.value = '请填写标题与磁贴内容'
  } else if (values.tile_type === 'link' && !safeTileLink(values.payload)) {
    validation.value = '请输入 HTTP(S) 地址或以 / 开头的站内路径'
  } else if (!Number.isInteger(sortOrder) || sortOrder < -2147483648 || sortOrder > 2147483647) {
    validation.value = '请输入有效的整数排序值'
  } else {
    validation.value = ''
    emit('save', { ...values, category: category.value.trim() || null, sort_order: sortOrder })
  }
}
</script>

<template>
  <AdaptiveModal :model-value="true" :title="title" @update:model-value="!busy && emit('close')">
    <form id="workbench-tile-editor" class="tile-editor" @submit.prevent="submit">
      <label>标题 <MdInput v-model="draft.title" :maxlength="100" :disabled="busy" /></label>
      <label>副标题 <MdInput v-model="draft.subtitle" :maxlength="240" :disabled="busy" /></label>
      <div class="tile-editor__choices">
        <div>
          <span id="tile-type-label">类型</span>
          <MdSelect v-model="draft.tile_type" :options="typeOptions" :disabled="busy" aria-labelledby="tile-type-label" />
        </div>
        <div>
          <span id="tile-icon-label">图标</span>
          <MdSelect v-model="draft.icon" :options="iconOptions" :disabled="busy" aria-labelledby="tile-icon-label" />
        </div>
      </div>
      <label v-if="draft.tile_type === 'prompt'">提示词模板
        <textarea v-model="draft.payload" rows="5" maxlength="10000" :disabled="busy" />
      </label>
      <label v-else>目标地址
        <MdInput v-model="draft.payload" placeholder="/capabilities" :maxlength="10000" :disabled="busy" />
      </label>
      <label>分类 <MdInput v-model="category" :maxlength="64" :disabled="busy" /></label>
      <label v-if="admin">排序值（从小到大）
        <MdInput v-model="order" type="number" :disabled="busy" />
      </label>
      <label class="tile-editor__switch">启用磁贴
        <MdSwitch v-model="draft.is_enabled" :disabled="busy" aria-label="启用磁贴" />
      </label>
      <p v-if="validation || error" class="tile-editor__error" role="alert">{{ validation || error }}</p>
    </form>
    <template #actions>
      <MdButton variant="text" :disabled="busy" @click="emit('close')">取消</MdButton>
      <MdButton type="submit" form="workbench-tile-editor" :disabled="busy">{{ busy ? '保存中…' : '保存' }}</MdButton>
    </template>
  </AdaptiveModal>
</template>

<style scoped>
.tile-editor, .tile-editor label, .tile-editor__choices > div {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.tile-editor { gap: 14px; }
.tile-editor__choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.tile-editor .tile-editor__switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
textarea {
  width: 100%;
  background: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  border: 1px solid var(--md-sys-color-outline);
  border-radius: var(--md-sys-shape-corner-small);
  padding: 10px;
  resize: vertical;
}
.tile-editor__error { color: var(--md-sys-color-error); }
</style>
