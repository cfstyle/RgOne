<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, type UsageRankingDimension, type UsageRankingRange } from '@/api'
import MdButton from '@/components/m3/MdButton.vue'
import MdTable, { type MdTableColumn } from '@/components/m3/MdTable.vue'

type RankingRow = {
  key: string
  name: string
  department: string | null
  total_tokens: number
  request_count: number
}

const props = defineProps<{ revision: number }>()
const tabs = [
  { value: 'user', label: '用户排行' },
  { value: 'model', label: '模型排行' },
] as const
const ranges = [
  { value: 'today', label: '今天' },
  { value: '7d', label: '近 7 天' },
  { value: '30d', label: '近 30 天' },
  { value: 'all', label: '全部时间' },
] as const

const dimension = ref<UsageRankingDimension>('user')
const range = ref<UsageRankingRange>('7d')
const rows = ref<RankingRow[]>([])
const loading = ref(false)
const error = ref(false)
const retry = ref(0)
const columns = computed<MdTableColumn<RankingRow>[]>(() => [
  { key: 'rank', title: '排名', width: '4.5rem', align: 'center', numeric: true },
  { key: 'name', title: dimension.value === 'user' ? '用户' : '模型' },
  { key: 'total_tokens', title: '总 Token', numeric: true },
  { key: 'request_count', title: '调用次数', numeric: true },
])
const formatNumber = new Intl.NumberFormat('zh-CN')

function isRankingRow(value: unknown): value is RankingRow {
  if (typeof value !== 'object' || value === null) return false
  const row = value as Partial<RankingRow>
  return typeof row.key === 'string' && typeof row.name === 'string' &&
    (row.department === null || typeof row.department === 'string') &&
    typeof row.total_tokens === 'number' && Number.isFinite(row.total_tokens) &&
    typeof row.request_count === 'number' && Number.isFinite(row.request_count)
}

function handleTabKey(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  if (event.key === 'Home') dimension.value = 'user'
  else if (event.key === 'End') dimension.value = 'model'
  else dimension.value = dimension.value === 'user' ? 'model' : 'user'
  document.getElementById(`usage-tab-${dimension.value}`)?.focus()
}

watch([dimension, range, () => props.revision, retry], async ([type, period], _, onCleanup) => {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 12000)
  let active = true
  onCleanup(() => {
    active = false
    clearTimeout(timeout)
    controller.abort()
  })

  error.value = false
  loading.value = true
  rows.value = []
  try {
    const response = await api.getAdminUsageRanking(type, period, controller.signal)
    if (!active) return
    if (!Array.isArray(response?.data) || !response.data.every(isRankingRow)) {
      throw new Error('无效的排行数据')
    }
    rows.value = response.data
  } catch {
    if (active) error.value = true
  } finally {
    clearTimeout(timeout)
    if (active) loading.value = false
  }
}, { immediate: true })
</script>

<template>
  <section class="ranking" aria-labelledby="usage-ranking-title">
    <div class="ranking-heading">
      <div>
        <h3 id="usage-ranking-title">Token 用量排行</h3>
        <p>输入与输出 Token 合计 · 前 20 名</p>
      </div>
      <div class="ranking-controls" role="group" aria-label="统计时间">
        <MdButton
          v-for="period in ranges"
          :key="period.value"
          :variant="range === period.value ? 'tonal' : 'text'"
          :aria-pressed="range === period.value"
          @click="range = period.value"
        >{{ period.label }}</MdButton>
      </div>
    </div>
    <div class="ranking-controls ranking-tabs" role="tablist" aria-label="排行类型" @keydown="handleTabKey">
      <MdButton
        v-for="tab in tabs"
        :id="`usage-tab-${tab.value}`"
        :key="tab.value"
        role="tab"
        aria-controls="usage-ranking-table"
        :aria-selected="dimension === tab.value"
        :tabindex="dimension === tab.value ? 0 : -1"
        :variant="dimension === tab.value ? 'filled' : 'text'"
        @click="dimension = tab.value"
      >{{ tab.label }}</MdButton>
    </div>
    <div
      id="usage-ranking-table"
      role="tabpanel"
      :aria-labelledby="`usage-tab-${dimension}`"
      :aria-busy="loading"
      tabindex="0"
    >
      <MdTable
        :columns="columns"
        :data="rows"
        :loading="loading"
        :skeleton-rows="3"
        :empty-text="error ? '排行榜加载失败' : '该时间段暂无 Token 用量'"
        row-key="key"
      >
        <template #cell-rank="{ index }">{{ index + 1 }}</template>
        <template #cell-name="{ row }">
          <strong class="ranking-name">{{ row.name }}</strong>
          <span v-if="dimension === 'user'" class="ranking-meta">
            工号 {{ row.key }}<template v-if="row.department"> · {{ row.department }}</template>
          </span>
        </template>
        <template #cell-total_tokens="{ row }">
          <strong>{{ formatNumber.format(row.total_tokens) }}</strong>
        </template>
        <template #cell-request_count="{ row }">{{ formatNumber.format(row.request_count) }}</template>
        <template v-if="error" #empty-action>
          <MdButton variant="outlined" @click="retry += 1">重试</MdButton>
        </template>
      </MdTable>
    </div>
  </section>
</template>

<style scoped>
.ranking {
  min-width: 0;
  padding: clamp(12px, 3vw, 24px);
  border: 1px solid var(--md-sys-color-outline-variant);
  border-radius: var(--md-sys-shape-corner-large);
  background-color: var(--md-sys-color-surface);
}

.ranking-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.ranking-heading h3 {
  margin: 0;
  font-size: 18px;
  color: var(--md-sys-color-on-surface);
}

.ranking-heading p,
.ranking-meta {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
}

.ranking-heading p {
  margin: 4px 0 0;
}

.ranking-controls {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.ranking-tabs {
  margin: 12px 0;
}

.ranking-controls :deep(button:focus-visible) {
  outline: 2px solid var(--md-sys-color-primary);
  outline-offset: 2px;
}

.ranking-name,
.ranking-meta {
  display: block;
  white-space: normal;
  overflow-wrap: anywhere;
}

.ranking-meta {
  margin-top: 2px;
}

@media (max-width: 600px) {
  .ranking-controls :deep(button) {
    min-height: 44px;
    padding-inline: 10px;
  }

  .ranking :deep(.m3-table-th),
  .ranking :deep(.m3-table-td) {
    padding-inline: 6px;
  }
}
</style>
