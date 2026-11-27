<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Search,
  RotateCcw,
  Power,
} from 'lucide-vue-next'
import { MdSelect, type SelectOption } from '@/components/m3'
import { api } from '@/api'

const tokenStatusOptions: SelectOption[] = [
  { label: '全部状态', value: '' },
  { label: '正常启用 (active)', value: 'active' },
  { label: '已被停用 (disabled)', value: 'disabled' },
]

interface AdminTokenItem {
  id: number
  employee_id: number
  emp_no: string
  employee_name: string
  department: string
  masked_key: string
  status: string
  reset_count: number
  token_name?: string
  total_requests?: number
  total_tokens?: number
  created_at?: string
  last_used_at?: string
}

const tokens = ref<AdminTokenItem[]>([])
const total = ref(0)
const page = ref(1)
const keyword = ref('')
const statusFilter = ref('')
const loading = ref(false)

async function loadTokens() {
  loading.value = true
  try {
    const res = await api.getAdminTokens(
      page.value,
      keyword.value || undefined,
      statusFilter.value || undefined
    ) as { items?: AdminTokenItem[]; total?: number }
    tokens.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载 Tokens 失败', e)
  } finally {
    loading.value = false
  }
}

async function handleToggleStatus(t: AdminTokenItem) {
  const nextStatus = t.status === 'active' ? 'disabled' : 'active'
  const actionText = nextStatus === 'active' ? '启用' : '禁用'
  if (!confirm(`确定要${actionText}员工 ${t.employee_name} (${t.emp_no}) 的 API Key 吗？`)) return

  try {
    await api.toggleTokenStatus(t.id, nextStatus)
    t.status = nextStatus
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '操作失败')
  }
}

async function handleForceReset(t: AdminTokenItem) {
  if (
    !confirm(
      `确定要强制重置员工 ${t.employee_name} 的专属 Key 吗？\n原 Key 将即刻失效并重新生成，历史用量持续关联。`
    )
  )
    return

  try {
    const res = await api.adminResetToken(t.id) as { new_masked_key?: string }
    alert(`Key 已重置！新密钥前缀: ${res.new_masked_key}`)
    loadTokens()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '重置失败')
  }
}

onMounted(() => {
  loadTokens()
})
</script>

<template>
  <div class="admin-tokens-view">
    <div class="page-top-bar">
      <div>
        <h2 class="page-title">员工专属 API Key 集中运维</h2>
        <p class="page-desc">
          查看全行已签发的 Token 绑定关系、累计消耗量，支持单点启停与强制重置
        </p>
      </div>
    </div>

    <!-- 筛选工具栏 -->
    <div class="filter-toolbar">
      <div class="search-wrap">
        <Search :size="16" class="s-icon" />
        <input
          v-model="keyword"
          type="text"
          class="s-input"
          placeholder="搜索工号、姓名或 Token 名称..."
          @keyup.enter="page = 1; loadTokens()"
        />
      </div>

      <MdSelect
        v-model="statusFilter"
        :options="tokenStatusOptions"
        size="sm"
        @change="page = 1; loadTokens()"
      />

      <button class="filter-btn md-state-layer" @click="page = 1; loadTokens()">查询</button>
    </div>

    <!-- 数据表 -->
    <div class="table-card studio-elevated-card">
      <table class="m3-admin-table">
        <thead>
          <tr>
            <th>工号</th>
            <th>员工姓名</th>
            <th>所属部门</th>
            <th>Token 名称</th>
            <th>API Key (掩码)</th>
            <th>累计请求</th>
            <th>总消耗 Token</th>
            <th>重置次数</th>
            <th>状态</th>
            <th style="text-align: right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="tokens.length === 0">
            <td colspan="10" class="empty-cell">暂无 API Key 记录</td>
          </tr>
          <tr v-for="t in tokens" :key="t.id">
            <td class="mono font-bold">{{ t.emp_no }}</td>
            <td>{{ t.employee_name }}</td>
            <td>{{ t.department }}</td>
            <td class="mono font-12">{{ t.token_name }}</td>
            <td class="mono font-12 highlight-key">{{ t.masked_key }}</td>
            <td>{{ (t.total_requests ?? 0).toLocaleString() }} 次</td>
            <td><strong>{{ (t.total_tokens ?? 0).toLocaleString() }}</strong></td>
            <td>{{ t.reset_count }} 次</td>
            <td>
              <span class="status-badge" :class="t.status">
                {{ t.status === 'active' ? '正常' : '已停用' }}
              </span>
            </td>
            <td style="text-align: right">
              <div class="row-actions">
                <button
                  class="action-pill"
                  :class="{ warn: t.status === 'active', success: t.status === 'disabled' }"
                  :title="t.status === 'active' ? '点击禁用' : '点击启用'"
                  @click="handleToggleStatus(t)"
                >
                  <Power :size="13" />
                  <span>{{ t.status === 'active' ? '停用' : '启用' }}</span>
                </button>
                <button
                  class="action-pill neutral"
                  title="强制重置 Key"
                  @click="handleForceReset(t)"
                >
                  <RotateCcw :size="13" />
                  <span>重置</span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 分页 -->
      <div v-if="total > 15" class="table-pagination">
        <button class="p-btn md-state-layer" :disabled="page <= 1" @click="page--; loadTokens()">上一页</button>
        <span class="p-info">第 {{ page }} 页 / 共 {{ Math.ceil(total / 15) }} 页 (总计 {{ total }} 个 Key)</span>
        <button class="p-btn md-state-layer" :disabled="page >= Math.ceil(total / 15)" @click="page++; loadTokens()">下一页</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-tokens-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.page-desc {
  font-size: 13px;
  color: var(--md-sys-color-outline);
}

.filter-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.s-icon {
  position: absolute;
  left: 12px;
  color: var(--md-sys-color-outline);
}

.s-input {
  width: 320px;
  padding: 8px 14px 8px 36px;
  border-radius: var(--md-sys-shape-corner-full);
  border: 1px solid rgba(0, 0, 0, 0.06);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  font-family: var(--md-sys-typescale-font-family-brand);
  outline: none;
}

.s-input:focus {
  border-color: var(--md-sys-color-primary);
}

.filter-btn {
  padding: 8px 18px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container-highest);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.table-card {
  background-color: var(--md-sys-color-surface-container-lowest);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.03), 0 1px 2px rgba(0, 0, 0, 0.02);
  overflow-x: auto;
}

.m3-admin-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.m3-admin-table th {
  padding: 12px 14px;
  background-color: var(--md-sys-color-surface-container-low);
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.m3-admin-table td {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  color: var(--md-sys-color-on-surface);
  font-variant-numeric: tabular-nums;
}

.mono { font-family: var(--md-sys-typescale-font-family-code); }
.font-bold { font-weight: 600; }
.font-12 { font-size: 12px; }

.highlight-key {
  color: var(--md-sys-color-primary);
  font-weight: 500;
}

.status-badge {
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 500;
}

.status-badge.active {
  background-color: #E6F4EA;
  color: #137333;
}

.status-badge.disabled {
  background-color: #FEE2E2;
  color: #B91C1C;
}

.row-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.action-pill {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-pill.warn {
  background-color: #FEE2E2;
  color: #B91C1C;
}

.action-pill.success {
  background-color: #E6F4EA;
  color: #137333;
}

.action-pill.neutral {
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
}

.empty-cell {
  text-align: center;
  padding: 40px;
  color: var(--md-sys-color-outline);
}

.table-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 16px;
}

.p-btn {
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-size: 12px;
  cursor: pointer;
}

.p-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.p-info {
  font-size: 12px;
  color: var(--md-sys-color-outline);
}
</style>
