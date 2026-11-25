<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Search,
  Plus,
  Upload,
  Download,
  Edit2,
  Trash2,
  AlertCircle,
  RotateCcw,
} from 'lucide-vue-next'
import { AdaptiveModal, MdButton } from '@/components/m3'
import { api } from '@/api'

interface EmployeeItem {
  id: number
  emp_no: string
  name: string
  department: string
  phone_last4?: string | null
  is_active: boolean
  has_token?: boolean
  token_status?: string | null
  created_at?: string
  updated_at?: string
}

interface EmployeeEditForm {
  id: number
  emp_no: string
  name: string
  department: string
  phone_last4: string
  is_active: boolean
}

interface ImportReport {
  total?: number
  created?: number
  updated?: number
  skipped?: number
  errors?: string[]
}

const employees = ref<EmployeeItem[]>([])
const total = ref(0)
const page = ref(1)
const keyword = ref('')
const loading = ref(false)

// 单条编辑/新增弹窗
const showEditModal = ref(false)
const isEditing = ref(false)
const editForm = ref<EmployeeEditForm>({
  id: 0,
  emp_no: '',
  name: '',
  department: '',
  phone_last4: '',
  is_active: true,
})

// 批量导入弹窗
const showImportModal = ref(false)
const importFile = ref<File | null>(null)
const importing = ref(false)
const importReport = ref<ImportReport | null>(null)

async function loadList() {
  loading.value = true
  try {
    const res = await api.getAdminEmployees(page.value, keyword.value || undefined) as { items?: EmployeeItem[]; total?: number }
    employees.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载名单失败', e)
  } finally {
    loading.value = false
  }
}

function openAddModal() {
  isEditing.value = false
  editForm.value = {
    id: 0,
    emp_no: '',
    name: '',
    department: '金融科技部',
    phone_last4: '',
    is_active: true,
  }
  showEditModal.value = true
}

function openEditModal(emp: EmployeeItem) {
  isEditing.value = true
  editForm.value = {
    id: emp.id,
    emp_no: emp.emp_no,
    name: emp.name,
    department: emp.department,
    phone_last4: emp.phone_last4 || '',
    is_active: emp.is_active,
  }
  showEditModal.value = true
}

async function handleSaveEmployee() {
  if (!editForm.value.emp_no || !editForm.value.name || !editForm.value.department) {
    alert('请将必填字段填写完整')
    return
  }

  try {
    if (isEditing.value) {
      await api.updateEmployee(editForm.value.id, {
        name: editForm.value.name,
        department: editForm.value.department,
        phone_last4: editForm.value.phone_last4 || null,
        is_active: editForm.value.is_active,
      })
    } else {
      await api.createEmployee(editForm.value as unknown as Record<string, unknown>)
    }
    showEditModal.value = false
    loadList()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '保存失败')
  }
}

async function handleDeleteEmployee(emp: EmployeeItem) {
  if (!confirm(`确定要删除工号 ${emp.emp_no} (${emp.name}) 吗？`)) return
  try {
    await api.deleteEmployee(emp.id)
    loadList()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '删除失败')
  }
}

async function handleRetryDisableToken(emp: EmployeeItem) {
  try {
    const res = await api.retryDisableEmployeeToken(emp.id) as { message?: string }
    alert(res.message || '网关 Token 吊销重试成功')
    loadList()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '网关吊销重试失败')
  }
}

function handleFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  importFile.value = file || null
}

async function handleStartImport() {
  if (!importFile.value) {
    alert('请选择要导入的 .xlsx 或 .csv 文件')
    return
  }

  importing.value = true
  importReport.value = null
  const fd = new FormData()
  fd.append('file', importFile.value)

  try {
    const res = await api.importEmployees(fd) as { data?: ImportReport }
    importReport.value = res.data || null
    loadList()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '导入失败')
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  loadList()
})
</script>

<template>
  <div class="admin-employees-view">
    <div class="page-top-bar">
      <div>
        <h2 class="page-title">行内员工白名单管理</h2>
        <p class="page-desc">维护已获授权接入大模型平台的员工底表，支持 Excel/CSV 批量增量导入</p>
      </div>

      <div class="top-actions">
        <a :href="api.getEmployeeTemplateUrl()" class="action-btn outline md-state-layer">
          <Download :size="16" />
          <span>下载导入模板</span>
        </a>
        <button class="action-btn outline md-state-layer" @click="showImportModal = true; importReport = null">
          <Upload :size="16" />
          <span>批量导入名单</span>
        </button>
        <button class="action-btn primary md-state-layer" @click="openAddModal">
          <Plus :size="16" />
          <span>新增单个员工</span>
        </button>
      </div>
    </div>

    <!-- 检索工具栏 -->
    <div class="search-toolbar">
      <div class="search-input-wrap">
        <Search :size="16" class="s-icon" />
        <input
          v-model="keyword"
          type="text"
          class="s-input"
          placeholder="搜索工号、姓名或部门..."
          @keyup.enter="page = 1; loadList()"
        />
      </div>
      <button class="filter-btn md-state-layer" @click="page = 1; loadList()">
        查询
      </button>
    </div>

    <!-- 数据表格 -->
    <div class="table-card studio-elevated-card">
      <table class="m3-admin-table">
        <thead>
          <tr>
            <th>工号</th>
            <th>姓名</th>
            <th>所属部门</th>
            <th>手机尾号</th>
            <th>白名单状态</th>
            <th>是否已领 Key</th>
            <th>录入时间</th>
            <th style="text-align: right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="employees.length === 0">
            <td colspan="8" class="empty-cell">未找到员工名单数据</td>
          </tr>
          <tr v-for="emp in employees" :key="emp.id">
            <td class="mono font-bold">{{ emp.emp_no }}</td>
            <td>{{ emp.name }}</td>
            <td>{{ emp.department }}</td>
            <td class="mono">{{ emp.phone_last4 || '-' }}</td>
            <td>
              <span class="status-pill" :class="{ active: emp.is_active }">
                {{ emp.is_active ? '有效' : '已停用' }}
              </span>
            </td>
            <td>
              <span v-if="emp.token_status === 'gateway_disable_pending'" class="token-pill warning">
                网关吊销待重试
              </span>
              <span v-else class="token-pill" :class="{ claimed: emp.has_token }">
                {{ emp.has_token ? '已申领' : '未申领' }}
              </span>
            </td>
            <td class="time-cell">{{ emp.created_at }}</td>
            <td style="text-align: right">
              <div class="row-actions">
                <button
                  v-if="emp.token_status === 'gateway_disable_pending'"
                  class="row-btn warning"
                  title="重试网关吊销"
                  @click="handleRetryDisableToken(emp)"
                >
                  <RotateCcw :size="15" />
                </button>
                <button class="row-btn" title="编辑" @click="openEditModal(emp)">
                  <Edit2 :size="15" />
                </button>
                <button class="row-btn danger" title="删除" @click="handleDeleteEmployee(emp)">
                  <Trash2 :size="15" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 分页 -->
      <div v-if="total > 15" class="table-pagination">
        <button class="p-btn md-state-layer" :disabled="page <= 1" @click="page--; loadList()">上一页</button>
        <span class="p-info">第 {{ page }} 页 / 共 {{ Math.ceil(total / 15) }} 页 (总计 {{ total }} 人)</span>
        <button class="p-btn md-state-layer" :disabled="page >= Math.ceil(total / 15)" @click="page++; loadList()">下一页</button>
      </div>
    </div>

    <!-- 单条编辑/新增弹窗 -->
    <AdaptiveModal
      :model-value="showEditModal"
      :title="isEditing ? '修改员工信息' : '录入新员工白名单'"
      max-width="480px"
      @update:model-value="showEditModal = $event"
    >
      <div class="modal-form">
        <div class="f-group">
          <label class="f-label">员工工号*</label>
          <input
            v-model="editForm.emp_no"
            type="text"
            class="m3-modal-input"
            placeholder="例如：06700956 或 06701099"
            :disabled="isEditing"
          />
        </div>

        <div class="f-group">
          <label class="f-label">真实姓名*</label>
          <input
            v-model="editForm.name"
            type="text"
            class="m3-modal-input"
            placeholder="员工真实姓名"
          />
        </div>

        <div class="f-group">
          <label class="f-label">所属部门*</label>
          <input
            v-model="editForm.department"
            type="text"
            class="m3-modal-input"
            placeholder="例如：金融科技部 · 架构组"
          />
        </div>

        <div class="f-group">
          <label class="f-label">手机后4位 (可选)</label>
          <input
            v-model="editForm.phone_last4"
            type="text"
            class="m3-modal-input"
            placeholder="4位数字"
            maxlength="4"
          />
        </div>

        <div class="f-group checkbox-group">
          <label class="checkbox-label">
            <input v-model="editForm.is_active" type="checkbox" />
            <span>是否激活白名单</span>
          </label>
        </div>

        <div class="modal-actions">
          <MdButton variant="text" @click="showEditModal = false">取消</MdButton>
          <MdButton variant="filled" @click="handleSaveEmployee">保存</MdButton>
        </div>
      </div>
    </AdaptiveModal>

    <!-- 批量导入弹窗 -->
    <AdaptiveModal
      :model-value="showImportModal"
      title="批量导入员工白名单"
      max-width="520px"
      @update:model-value="showImportModal = $event"
    >
      <div class="import-modal-body">
        <p class="import-tip">
          请上传包含 <strong>工号、姓名、所属部门、手机后4位</strong> 的 Excel (<code>.xlsx</code>) 或 CSV 文件。已有工号将自动覆盖更新。
        </p>

        <div class="file-drop-area">
          <input type="file" accept=".xlsx,.xls,.csv" @change="handleFileSelect" />
          <div class="file-drop-text">
            <Upload :size="28" style="color: var(--md-sys-color-primary); margin-bottom: 8px" />
            <span>{{ importFile ? importFile.name : '点击或拖拽上传 Excel / CSV 文件' }}</span>
          </div>
        </div>

        <!-- 导入报告 -->
        <div v-if="importReport" class="report-box">
          <div class="report-title">导入执行报告：</div>
          <div class="report-stats">
            <span class="r-stat green">新增: {{ importReport.created }} 条</span>
            <span class="r-stat blue">更新: {{ importReport.updated }} 条</span>
            <span class="r-stat orange">跳过: {{ importReport.skipped }} 条</span>
          </div>
          <div v-if="importReport.errors?.length" class="report-errors">
            <div v-for="err in importReport.errors" :key="err" class="err-line">
              <AlertCircle :size="12" />
              <span>{{ err }}</span>
            </div>
          </div>
        </div>

        <div class="modal-actions">
          <MdButton variant="text" @click="showImportModal = false">关闭</MdButton>
          <MdButton variant="filled" :disabled="importing || !importFile" @click="handleStartImport">
            {{ importing ? '正在导入解析...' : '开始导入' }}
          </MdButton>
        </div>
      </div>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.admin-employees-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
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

.top-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.2s ease;
}

.action-btn.outline {
  border: 1px solid rgba(0, 0, 0, 0.08);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
}

.action-btn.primary {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
}

.search-toolbar {
  display: flex;
  gap: 10px;
}

.search-input-wrap {
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
  padding: 12px 16px;
  background-color: var(--md-sys-color-surface-container-low);
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.m3-admin-table td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  color: var(--md-sys-color-on-surface);
  font-variant-numeric: tabular-nums;
}

.mono { font-family: var(--md-sys-typescale-font-family-code); }
.font-bold { font-weight: 600; }
.time-cell { font-size: 12px; color: var(--md-sys-color-outline); }

.status-pill {
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 500;
  background-color: #FEE2E2;
  color: #B91C1C;
}

.status-pill.active {
  background-color: #E6F4EA;
  color: #137333;
}

.token-pill {
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 500;
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-outline);
}

.token-pill.claimed {
  background-color: var(--md-sys-color-surface-container-highest);
  color: var(--md-sys-color-on-surface);
}

.row-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.row-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-surface-container);
  cursor: pointer;
}

.row-btn:hover {
  background-color: var(--md-sys-color-surface-container-highest);
}

.row-btn.danger:hover {
  color: var(--md-sys-color-error);
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

/* 弹窗表单 */
.modal-form {
  padding: 8px 4px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.f-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.f-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.m3-modal-input {
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  border: 1px solid var(--md-sys-color-outline);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 14px;
  outline: none;
}

.checkbox-group {
  margin-top: 6px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}

/* 导入区域 */
.import-modal-body {
  padding: 8px 4px 16px;
}

.import-tip {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.5;
  margin-bottom: 16px;
}

.file-drop-area {
  position: relative;
  border: 2px dashed var(--md-sys-color-outline);
  border-radius: var(--md-sys-shape-corner-medium);
  padding: 30px;
  text-align: center;
  margin-bottom: 16px;
}

.file-drop-area input {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.file-drop-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 14px;
  color: var(--md-sys-color-on-surface);
}

.report-box {
  padding: 12px 16px;
  background-color: var(--md-sys-color-surface-container);
  border-radius: var(--md-sys-shape-corner-small);
  font-size: 13px;
  margin-bottom: 16px;
}

.report-title {
  font-weight: 700;
  margin-bottom: 6px;
}

.report-stats {
  display: flex;
  gap: 12px;
  font-weight: 600;
}

.r-stat.green { color: #059669; }
.r-stat.blue { color: #2563eb; }
.r-stat.orange { color: #d97706; }

.report-errors {
  margin-top: 8px;
  font-size: 12px;
  color: var(--md-sys-color-error);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.err-line {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
