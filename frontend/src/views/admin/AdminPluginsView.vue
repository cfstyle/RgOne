<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  AlertTriangle,
  Archive,
  Check,
  Eye,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-vue-next'
import AdaptiveModal from '@/components/m3/AdaptiveModal.vue'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import MdSwitch from '@/components/m3/MdSwitch.vue'
import { api } from '@/api'
import { useToast } from '@/composables/useToast'
import type { PluginItem, PluginVersionItem } from '@/types/mcp'

const toast = useToast()
const loading = ref(true)
const plugins = ref<PluginItem[]>([])
const statusFilter = ref<'pending' | 'published' | 'all' | 'rejected' | 'deprecated'>('pending')

// package.json 快照预览弹窗
const snapshotModalVisible = ref(false)
const activeVersion = ref<PluginVersionItem | null>(null)
const activePlugin = ref<PluginItem | null>(null)

// 审核弹窗
const reviewModalVisible = ref(false)
const reviewMode = ref<'approve' | 'reject'>('approve')
const reviewComment = ref('')
const allowLifecycle = ref(false)
const submittingReview = ref(false)

// 权重/上架状态调整弹窗
const editModalVisible = ref(false)
const savingEdit = ref(false)
const editForm = reactive({
  sort_weight: 0,
  status: 'published',
  category: '',
})

let isMounted = true

async function fetchPlugins() {
  loading.value = true
  try {
    const res = await api.getAdminPlugins(statusFilter.value)
    if (isMounted) {
      plugins.value = res.items || []
    }
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '获取插件列表失败')
  } finally {
    if (isMounted) loading.value = false
  }
}

function getLatestVersion(plugin: PluginItem): PluginVersionItem | undefined {
  return plugin.versions?.[0]
}

function openSnapshot(plugin: PluginItem, version: PluginVersionItem) {
  activePlugin.value = plugin
  activeVersion.value = version
  snapshotModalVisible.value = true
}

function openReviewModal(plugin: PluginItem, version: PluginVersionItem, mode: 'approve' | 'reject') {
  activePlugin.value = plugin
  activeVersion.value = version
  reviewMode.value = mode
  reviewComment.value = mode === 'approve' ? '代码安全核验通过，同意发布上架' : ''
  allowLifecycle.value = false
  reviewModalVisible.value = true
}

async function submitReview() {
  if (!activeVersion.value) return
  if (reviewMode.value === 'reject' && !reviewComment.value.trim()) {
    toast.warning('驳回时请填写具体原因')
    return
  }

  submittingReview.value = true
  try {
    if (reviewMode.value === 'approve') {
      const res = await api.approvePluginVersion(activeVersion.value.id, {
        comment: reviewComment.value.trim(),
        allow_lifecycle_scripts: allowLifecycle.value,
      })
      toast.success(`${res.message}（${res.publish_status}）`)
    } else {
      const res = await api.rejectPluginVersion(activeVersion.value.id, reviewComment.value.trim())
      toast.success(res.message)
    }
    reviewModalVisible.value = false
    await fetchPlugins()
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '审核处理失败')
  } finally {
    submittingReview.value = false
  }
}

function openEditModal(plugin: PluginItem) {
  activePlugin.value = plugin
  editForm.sort_weight = plugin.sort_weight
  editForm.status = plugin.status
  editForm.category = plugin.category
  editModalVisible.value = true
}

async function saveEdit() {
  if (!activePlugin.value) return
  savingEdit.value = true
  try {
    await api.updateAdminPlugin(activePlugin.value.id, {
      sort_weight: Number(editForm.sort_weight) || 0,
      status: editForm.status,
      category: editForm.category.trim() || undefined,
    })
    toast.success('插件治理配置已更新')
    editModalVisible.value = false
    await fetchPlugins()
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '更新失败')
  } finally {
    savingEdit.value = false
  }
}

async function deprecatePlugin(plugin: PluginItem) {
  const nextStatus = plugin.status === 'deprecated' ? 'published' : 'deprecated'
  const label = nextStatus === 'deprecated' ? '下架' : '重新上架'
  if (!window.confirm(`确定要${label}插件「${plugin.name}」吗？`)) return
  try {
    await api.updateAdminPlugin(plugin.id, { status: nextStatus })
    toast.success(`已${label}插件`)
    await fetchPlugins()
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '操作失败')
  }
}

onMounted(() => {
  void fetchPlugins()
})

onBeforeUnmount(() => {
  isMounted = false
})
</script>

<template>
  <section class="admin-plugins-page" aria-label="插件市场治理">
    <div class="page-head">
      <div>
        <h2>DSH 插件市场治理</h2>
        <p>审核员工投稿插件（安全校验与生命周期脚本把关），一键发布至离线 Verdaccio 私有仓库</p>
      </div>
      <MdButton variant="tonal" :disabled="loading" @click="fetchPlugins">
        <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
        <span>刷新队列</span>
      </MdButton>
    </div>

    <div class="status-tabs">
      <button
        v-for="tab in [
          { key: 'pending', label: '待审核队列' },
          { key: 'published', label: '已上架' },
          { key: 'rejected', label: '已驳回' },
          { key: 'deprecated', label: '已下架' },
          { key: 'all', label: '全部插件' },
        ] as const"
        :key="tab.key"
        type="button"
        :class="['tab-pill', { 'is-active': statusFilter === tab.key }]"
        @click="
          () => {
            statusFilter = tab.key
            void fetchPlugins()
          }
        "
      >
        {{ tab.label }}
      </button>
    </div>

    <MdCard variant="elevated">
      <div v-if="loading && !plugins.length" class="empty-box">正在加载插件投稿列表...</div>
      <div v-else-if="!plugins.length" class="empty-box">当前状态下暂无插件记录</div>
      <div v-else class="table-wrap">
        <table class="m3-native-table">
          <thead>
            <tr>
              <th>插件包与版本</th>
              <th>投稿人</th>
              <th>安全检测</th>
              <th>当前状态 / 权重</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plugin in plugins" :key="plugin.id">
              <td>
                <div class="pkg-cell">
                  <strong>{{ plugin.display_name || plugin.name }}</strong>
                  <span class="mono sub-text">
                    {{ plugin.name }} · 最新待审/已审: v{{
                      getLatestVersion(plugin)?.version || plugin.latest_version || '-'
                    }}
                  </span>
                </div>
              </td>
              <td>
                <div class="pkg-cell">
                  <span>{{ plugin.author_name || plugin.author_emp_no }}</span>
                  <span class="mono sub-text">{{ plugin.author_emp_no }}</span>
                </div>
              </td>
              <td>
                <div v-if="getLatestVersion(plugin)" class="sec-badges">
                  <span
                    v-if="getLatestVersion(plugin)?.has_lifecycle_scripts"
                    class="sec-pill danger"
                  >
                    <AlertTriangle :size="12" />
                    <span>含生命周期脚本</span>
                  </span>
                  <span v-else class="sec-pill safe">
                    <ShieldCheck :size="12" />
                    <span>无脚本风险 ({{ getLatestVersion(plugin)?.submit_source }})</span>
                  </span>
                </div>
              </td>
              <td>
                <div class="pkg-cell">
                  <span class="status-pill" :class="`st-${plugin.status}`">{{ plugin.status }}</span>
                  <span class="sub-text">权重: {{ plugin.sort_weight }} · 下载: {{ plugin.downloads }}</span>
                </div>
              </td>
              <td>
                <div class="row-actions">
                  <MdButton
                    v-if="getLatestVersion(plugin)"
                    variant="text"
                    @click="openSnapshot(plugin, getLatestVersion(plugin)!)"
                  >
                    <Eye :size="14" />
                    <span>package.json</span>
                  </MdButton>
                  <template v-if="getLatestVersion(plugin)?.review_status === 'pending'">
                    <MdButton
                      variant="filled"
                      @click="openReviewModal(plugin, getLatestVersion(plugin)!, 'approve')"
                    >
                      <Check :size="14" />
                      <span>通过并推包</span>
                    </MdButton>
                    <MdButton
                      variant="text"
                      @click="openReviewModal(plugin, getLatestVersion(plugin)!, 'reject')"
                    >
                      <X :size="14" />
                      <span>驳回</span>
                    </MdButton>
                  </template>
                  <MdButton variant="tonal" @click="openEditModal(plugin)">权重/分类</MdButton>
                  <MdButton
                    v-if="plugin.status === 'published' || plugin.status === 'deprecated'"
                    variant="text"
                    @click="deprecatePlugin(plugin)"
                  >
                    <Archive :size="14" />
                    <span>{{ plugin.status === 'deprecated' ? '重上架' : '下架' }}</span>
                  </MdButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </MdCard>

    <!-- package.json 快照弹窗 -->
    <AdaptiveModal
      v-model="snapshotModalVisible"
      :title="`package.json 摘要: ${activePlugin?.name || ''}@${activeVersion?.version || ''}`"
      max-width="640px"
    >
      <div v-if="activeVersion" class="snapshot-body">
        <div class="sha-line">
          <span>SHA-256:</span>
          <code class="mono">{{ activeVersion.tarball_sha256 || 'Git 投稿无压缩包哈希' }}</code>
        </div>
        <pre class="code-pre"><code>{{ JSON.stringify(activeVersion.package_json || {}, null, 2) }}</code></pre>
      </div>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="filled" @click="snapshotModalVisible = false">关闭</MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- 审核确认弹窗 -->
    <AdaptiveModal
      v-model="reviewModalVisible"
      :title="
        reviewMode === 'approve'
          ? '审核通过并推送至 Verdaccio'
          : '驳回插件投稿'
      "
      max-width="500px"
    >
      <div v-if="activePlugin && activeVersion" class="review-body">
        <p class="review-desc">
          插件: <strong>{{ activePlugin.name }}@{{ activeVersion.version }}</strong>
        </p>
        <div v-if="reviewMode === 'approve' && activeVersion.has_lifecycle_scripts" class="warn-box">
          <div class="warn-text">
            <AlertTriangle :size="16" />
            <span>该版本包含 npm 生命周期脚本，需管理员明确确认安全风险后放行：</span>
          </div>
          <MdSwitch v-model="allowLifecycle" />
        </div>
        <div class="form-item">
          <label class="form-label">审核意见 / 批注</label>
          <textarea
            v-model="reviewComment"
            rows="3"
            placeholder="填写审核说明（将通过小秘书推送给作者）"
            class="form-textarea"
          ></textarea>
        </div>
      </div>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="reviewModalVisible = false">取消</MdButton>
          <MdButton variant="filled" :disabled="submittingReview" @click="submitReview">
            {{ submittingReview ? '正在处理...' : '确认提交' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>

    <!-- 排序权重调整弹窗 -->
    <AdaptiveModal v-model="editModalVisible" title="调整插件展示权重与分类" max-width="440px">
      <div class="review-body">
        <div class="form-item">
          <label class="form-label">排序权重（数值越大越靠前）</label>
          <input v-model.number="editForm.sort_weight" type="number" class="form-input" />
        </div>
        <div class="form-item">
          <label class="form-label">插件分类</label>
          <input v-model="editForm.category" type="text" class="form-input" />
        </div>
      </div>
      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="editModalVisible = false">取消</MdButton>
          <MdButton variant="filled" :disabled="savingEdit" @click="saveEdit">
            {{ savingEdit ? '保存中...' : '保存修改' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>
  </section>
</template>

<style scoped>
.admin-plugins-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-head h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.page-head p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.status-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tab-pill {
  padding: 7px 15px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.tab-pill.is-active {
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

.pkg-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sub-text {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.sec-pill,
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
  width: fit-content;
}

.sec-pill.safe,
.status-pill.st-published {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.status-pill.st-pending {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.sec-pill.danger,
.status-pill.st-rejected {
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
}

.status-pill.st-deprecated {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface-variant);
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.snapshot-body,
.review-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sha-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  word-break: break-all;
}

.code-pre {
  margin: 0;
  padding: 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  max-height: 420px;
  overflow: auto;
}

.review-desc {
  margin: 0;
  font-size: 13px;
}

.warn-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
  font-size: 12px;
}

.warn-text {
  display: flex;
  align-items: center;
  gap: 6px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
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

.modal-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.empty-box {
  padding: 32px;
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
