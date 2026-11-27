<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, RefreshCw, X } from 'lucide-vue-next'
import AdaptiveModal from '@/components/m3/AdaptiveModal.vue'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import {
  getAdminPermissionRequests,
  getMcpErrorMessage,
  isMcpEngineUnavailable,
  reviewAdminPermissionRequest,
} from '@/api/mcp'
import type { PermissionRequest } from '@/types/mcp'

const emit = defineEmits<{
  (e: 'engine-error', message: string): void
}>()

const toast = useToast()
const authStore = useAuthStore()
const loading = ref(true)
const requests = ref<PermissionRequest[]>([])
const statusFilter = ref<'pending' | 'approved' | 'rejected' | 'all'>('pending')

const reviewModalVisible = ref(false)
const reviewingReq = ref<PermissionRequest | null>(null)
const reviewAction = ref<'approved' | 'rejected'>('approved')
const reviewComment = ref('')
const submittingReview = ref(false)

let abortController: AbortController | null = null

const filteredRequests = computed(() => {
  if (statusFilter.value === 'all') return requests.value
  return requests.value.filter((item) => item.status === statusFilter.value)
})

async function fetchRequests() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  loading.value = true
  try {
    requests.value = await getAdminPermissionRequests(undefined, abortController.signal)
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const msg = getMcpErrorMessage(err, '获取权限审批单失败')
    if (isMcpEngineUnavailable(err)) emit('engine-error', msg)
    else toast.error(msg)
  } finally {
    loading.value = false
  }
}

function openReviewModal(req: PermissionRequest, action: 'approved' | 'rejected') {
  reviewingReq.value = req
  reviewAction.value = action
  reviewComment.value = action === 'approved' ? '同意开通授权' : ''
  reviewModalVisible.value = true
}

async function submitReview() {
  if (!reviewingReq.value) return
  if (reviewAction.value === 'rejected' && !reviewComment.value.trim()) {
    toast.warning('驳回申请时请填写驳回原因')
    return
  }
  submittingReview.value = true
  try {
    await reviewAdminPermissionRequest(reviewingReq.value.id, {
      status: reviewAction.value,
      reviewer: authStore.adminUsername || 'admin',
      comment: reviewComment.value.trim() || undefined,
    })
    toast.success(reviewAction.value === 'approved' ? '已批准该权限申请' : '已驳回该权限申请')
    reviewModalVisible.value = false
    await fetchRequests()
  } catch (err: unknown) {
    toast.error(getMcpErrorMessage(err, '审批提交失败'))
  } finally {
    submittingReview.value = false
  }
}

onMounted(() => {
  void fetchRequests()
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="mcp-permissions-tab">
    <div class="tab-toolbar">
      <div class="status-pills">
        <button
          v-for="tab in [
            { key: 'pending', label: '待审批' },
            { key: 'approved', label: '已通过' },
            { key: 'rejected', label: '已驳回' },
            { key: 'all', label: '全部记录' },
          ] as const"
          :key="tab.key"
          type="button"
          :class="['filter-pill', { 'is-active': statusFilter === tab.key }]"
          @click="statusFilter = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
      <MdButton variant="tonal" :disabled="loading" @click="fetchRequests">
        <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
        <span>刷新列表</span>
      </MdButton>
    </div>

    <MdCard variant="elevated">
      <div v-if="loading && !requests.length" class="empty-box">正在加载权限申请...</div>
      <div v-else-if="!filteredRequests.length" class="empty-box">当前筛选下暂无审批工单</div>
      <div v-else class="table-wrap">
        <table class="m3-native-table">
          <thead>
            <tr>
              <th>申请员工</th>
              <th>目标服务</th>
              <th>申请工具</th>
              <th>申请原因</th>
              <th>状态</th>
              <th>提交时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="req in filteredRequests" :key="req.id">
              <td>
                <div class="user-cell">
                  <strong>{{ req.user_name || req.user_id }}</strong>
                  <span class="mono sub-id">{{ req.user_id }}</span>
                </div>
              </td>
              <td>{{ req.service_name || req.service_id }}</td>
              <td>
                <div class="tool-chips">
                  <span v-for="tName in req.tool_names" :key="tName" class="tag-pill">
                    {{ tName }}
                  </span>
                </div>
              </td>
              <td class="reason-cell">{{ req.reason || '-' }}</td>
              <td>
                <span class="status-pill" :class="`st-${req.status}`">
                  {{
                    req.status === 'approved'
                      ? '已通过'
                      : req.status === 'rejected'
                        ? '已驳回'
                        : '待审批'
                  }}
                </span>
              </td>
              <td class="mono sub-id">
                {{ req.created_at ? req.created_at.slice(0, 19).replace('T', ' ') : '-' }}
              </td>
              <td>
                <div v-if="req.status === 'pending'" class="row-actions">
                  <MdButton variant="tonal" @click="openReviewModal(req, 'approved')">
                    <Check :size="14" />
                    <span>通过</span>
                  </MdButton>
                  <MdButton variant="text" @click="openReviewModal(req, 'rejected')">
                    <X :size="14" />
                    <span>驳回</span>
                  </MdButton>
                </div>
                <span v-else class="sub-id">{{ req.reviewed_by || '-' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </MdCard>

    <AdaptiveModal
      v-model="reviewModalVisible"
      :title="reviewAction === 'approved' ? '批准工具权限申请' : '驳回工具权限申请'"
      max-width="480px"
    >
      <div v-if="reviewingReq" class="review-body">
        <p class="review-summary">
          员工 <strong>{{ reviewingReq.user_name || reviewingReq.user_id }}</strong> 申请开通服务
          <strong>{{ reviewingReq.service_name }}</strong> 下 {{ reviewingReq.tool_names.length }} 个工具。
        </p>
        <div class="form-item">
          <label class="form-label">审批批注</label>
          <textarea
            v-model="reviewComment"
            rows="3"
            placeholder="请输入审批意见或驳回原因"
            class="form-textarea"
          ></textarea>
        </div>
      </div>
      <template #actions>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="reviewModalVisible = false">取消</MdButton>
          <MdButton variant="filled" :disabled="submittingReview" @click="submitReview">
            {{ submittingReview ? '处理中...' : '确认提交' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.mcp-permissions-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.status-pills {
  display: flex;
  gap: 6px;
}

.filter-pill {
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 12px;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.filter-pill.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}

.table-wrap {
  overflow-x: auto;
}

.m3-native-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.m3-native-table th,
.m3-native-table td {
  padding: 12px 10px;
  text-align: left;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.m3-native-table th {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sub-id {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.tool-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.tag-pill,
.status-pill {
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
}

.tag-pill {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface);
}

.status-pill.st-approved {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.status-pill.st-pending {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.status-pill.st-rejected {
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
}

.reason-cell {
  max-width: 240px;
  color: var(--md-sys-color-on-surface-variant);
}

.row-actions {
  display: flex;
  gap: 6px;
}

.review-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.review-summary {
  margin: 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
}

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

.modal-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.empty-box {
  padding: 28px;
  text-align: center;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.is-spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
