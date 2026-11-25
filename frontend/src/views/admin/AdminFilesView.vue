<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Download,
  Plus,
  Trash2,
  Edit2,
} from 'lucide-vue-next'
import { AdaptiveModal, MdButton } from '@/components/m3'
import { api } from '@/api'

interface SharedFileItem {
  id: number
  category: string
  title: string
  version?: string | null
  description?: string | null
  is_recommended: boolean
  file_name?: string
  original_filename?: string
  file_size?: number
  download_count?: number
  download_url?: string
  created_at?: string
}

const files = ref<SharedFileItem[]>([])
const loading = ref(false)

const showUploadModal = ref(false)
const uploadFile = ref<File | null>(null)
const uploadForm = ref({
  category: 'installer',
  title: '',
  version: '',
  description: '',
  is_recommended: false,
})
const isUploading = ref(false)

const showEditModal = ref(false)
const editForm = ref({
  id: 0,
  title: '',
  version: '',
  description: '',
  is_recommended: false,
})

async function loadFiles() {
  loading.value = true
  try {
    const res = await api.getFiles() as { data?: SharedFileItem[] }
    files.value = res.data || []
  } catch (e) {
    console.error('加载文件失败', e)
  } finally {
    loading.value = false
  }
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    uploadFile.value = file
    if (!uploadForm.value.title) {
      uploadForm.value.title = file.name.replace(/\.[^/.]+$/, '')
    }
  } else {
    uploadFile.value = null
  }
}

async function handleStartUpload() {
  if (!uploadFile.value || !uploadForm.value.title) {
    alert('请选择文件并填写资料标题')
    return
  }

  isUploading.value = true
  const fd = new FormData()
  fd.append('file', uploadFile.value)
  fd.append('category', uploadForm.value.category)
  fd.append('title', uploadForm.value.title)
  if (uploadForm.value.version) fd.append('version', uploadForm.value.version)
  if (uploadForm.value.description) fd.append('description', uploadForm.value.description)
  fd.append('is_recommended', String(uploadForm.value.is_recommended))

  try {
    await api.uploadFile(fd)
    showUploadModal.value = false
    uploadFile.value = null
    uploadForm.value = {
      category: 'installer',
      title: '',
      version: '',
      description: '',
      is_recommended: false,
    }
    loadFiles()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '上传失败')
  } finally {
    isUploading.value = false
  }
}

function openEditModal(f: SharedFileItem) {
  editForm.value = {
    id: f.id,
    title: f.title,
    version: f.version || '',
    description: f.description || '',
    is_recommended: f.is_recommended,
  }
  showEditModal.value = true
}

async function handleSaveEdit() {
  try {
    await api.updateFileMeta(editForm.value.id, editForm.value)
    showEditModal.value = false
    loadFiles()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '更新失败')
  }
}

async function handleDelete(f: SharedFileItem) {
  if (!confirm(`确定要彻底删除文件 ${f.title} 吗？磁盘物理文件将同步清理。`)) return
  try {
    await api.deleteFile(f.id)
    loadFiles()
  } catch (e: unknown) {
    const err = e as { message?: string }
    alert(err.message || '删除失败')
  }
}

function formatBytes(bytes?: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

onMounted(() => {
  loadFiles()
})
</script>

<template>
  <div class="admin-files-view">
    <div class="page-top-bar">
      <div>
        <h2 class="page-title">安装包与共享资料托管</h2>
        <p class="page-desc">
          管理 DeepSeek Harness 安装包与内网资料，文件安全存储于 <code>data/storage/downloads/</code>
        </p>
      </div>

      <button class="upload-btn primary md-state-layer" @click="showUploadModal = true">
        <Plus :size="16" />
        <span>上传新文件</span>
      </button>
    </div>

    <!-- 文件列表表格 -->
    <div class="table-card studio-elevated-card">
      <table class="m3-admin-table">
        <thead>
          <tr>
            <th>资料标题</th>
            <th>分类</th>
            <th>版本号</th>
            <th>文件大小</th>
            <th>累计下载</th>
            <th>首页主推</th>
            <th>发布时间</th>
            <th style="text-align: right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="files.length === 0">
            <td colspan="8" class="empty-cell">暂无上传的文件资料</td>
          </tr>
          <tr v-for="f in files" :key="f.id">
            <td>
              <div class="title-cell">
                <span class="f-title">{{ f.title }}</span>
                <span class="f-orig">{{ f.original_filename }}</span>
              </div>
            </td>
            <td>
              <span class="cat-tag">{{ f.category }}</span>
            </td>
            <td class="mono">{{ f.version || '-' }}</td>
            <td class="mono">{{ formatBytes(f.file_size) }}</td>
            <td>{{ f.download_count }} 次</td>
            <td>
              <span v-if="f.is_recommended" class="rec-pill">主推</span>
              <span v-else class="normal-pill">普通</span>
            </td>
            <td class="time-cell">{{ f.created_at }}</td>
            <td style="text-align: right">
              <div class="row-actions">
                <a :href="f.download_url" class="row-btn" title="直接下载">
                  <Download :size="14" />
                </a>
                <button class="row-btn" title="编辑属性" @click="openEditModal(f)">
                  <Edit2 :size="14" />
                </button>
                <button class="row-btn danger" title="删除" @click="handleDelete(f)">
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 上传弹窗 -->
    <AdaptiveModal
      :model-value="showUploadModal"
      title="分块流式上传资料/安装包"
      max-width="500px"
      @update:model-value="showUploadModal = $event"
    >
      <div class="modal-form">
        <div class="f-group">
          <label class="f-label">选择本地文件*</label>
          <input type="file" @change="handleFileChange" />
        </div>

        <div class="f-group">
          <label class="f-label">资料类别</label>
          <select v-model="uploadForm.category" class="m3-modal-input">
            <option value="installer">客户端安装包 (installer)</option>
            <option value="manual">使用手册 (manual)</option>
            <option value="plugin">插件工具 (plugin)</option>
            <option value="other">其他资料 (other)</option>
          </select>
        </div>

        <div class="f-group">
          <label class="f-label">资料展示标题*</label>
          <input
            v-model="uploadForm.title"
            type="text"
            class="m3-modal-input"
            placeholder="例如：DeepSeek Harness Windows 客户端"
          />
        </div>

        <div class="f-group">
          <label class="f-label">版本号 (可选)</label>
          <input
            v-model="uploadForm.version"
            type="text"
            class="m3-modal-input"
            placeholder="例如：v1.4.2"
          />
        </div>

        <div class="f-group">
          <label class="f-label">更新说明或描述 (可选)</label>
          <textarea
            v-model="uploadForm.description"
            class="m3-modal-input"
            rows="3"
            placeholder="输入简要更新说明"
          />
        </div>

        <div class="f-group checkbox-group" v-if="uploadForm.category === 'installer'">
          <label class="checkbox-label">
            <input v-model="uploadForm.is_recommended" type="checkbox" />
            <span>设为首页第 1 步主推的安装包</span>
          </label>
        </div>

        <div class="modal-actions">
          <MdButton variant="text" @click="showUploadModal = false">取消</MdButton>
          <MdButton variant="filled" :disabled="isUploading || !uploadFile" @click="handleStartUpload">
            {{ isUploading ? '分块流式上传中...' : '开始上传' }}
          </MdButton>
        </div>
      </div>
    </AdaptiveModal>

    <!-- 编辑元数据弹窗 -->
    <AdaptiveModal
      :model-value="showEditModal"
      title="修改资料元数据"
      max-width="480px"
      @update:model-value="showEditModal = $event"
    >
      <div class="modal-form">
        <div class="f-group">
          <label class="f-label">资料标题</label>
          <input v-model="editForm.title" type="text" class="m3-modal-input" />
        </div>

        <div class="f-group">
          <label class="f-label">版本号</label>
          <input v-model="editForm.version" type="text" class="m3-modal-input" />
        </div>

        <div class="f-group">
          <label class="f-label">更新说明</label>
          <textarea v-model="editForm.description" class="m3-modal-input" rows="3" />
        </div>

        <div class="f-group checkbox-group">
          <label class="checkbox-label">
            <input v-model="editForm.is_recommended" type="checkbox" />
            <span>设为主推安装包</span>
          </label>
        </div>

        <div class="modal-actions">
          <MdButton variant="text" @click="showEditModal = false">取消</MdButton>
          <MdButton variant="filled" @click="handleSaveEdit">保存修改</MdButton>
        </div>
      </div>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.admin-files-view {
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

.page-desc code {
  background-color: var(--md-sys-color-surface-container);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--md-sys-typescale-font-family-code);
}

.upload-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.upload-btn.primary {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
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

.title-cell {
  display: flex;
  flex-direction: column;
}

.f-title {
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.f-orig {
  font-size: 11px;
  color: var(--md-sys-color-outline);
  font-family: var(--md-sys-typescale-font-family-code);
}

.cat-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
}

.mono { font-family: var(--md-sys-typescale-font-family-code); }
.time-cell { font-size: 12px; color: var(--md-sys-color-outline); }

.rec-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
}

.normal-pill {
  font-size: 11px;
  color: var(--md-sys-color-outline);
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container);
}

.row-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
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
  text-decoration: none;
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
</style>
