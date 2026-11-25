<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Plus,
  Edit2,
  Trash2,
  Pin,
  Image as ImageIcon,
} from 'lucide-vue-next'
import { AdaptiveModal } from '@/components/m3'
import { api } from '@/api'

export interface ArticleItem {
  id: number
  title: string
  category: string
  summary: string
  author_name: string
  content_md: string
  view_count?: number
  is_pinned?: boolean
  is_published?: boolean
  created_at?: string
  updated_at?: string
}

const articles = ref<ArticleItem[]>([])
const loading = ref(false)

const showEditorModal = ref(false)
const isEditing = ref(false)
const editorForm = ref<ArticleItem>({
  id: 0,
  title: '',
  category: '代码实践',
  summary: '',
  author_name: 'AI 赋能工作组',
  content_md: '',
  is_pinned: false,
  is_published: true,
})

const imageInputRef = ref<HTMLInputElement | null>(null)
const uploadingImg = ref(false)

async function loadArticles() {
  loading.value = true
  try {
    const res = await api.getAdminArticles() as { items?: ArticleItem[] }
    articles.value = res.items || []
  } catch (e) {
    console.error('加载文章失败', e)
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  isEditing.value = false
  editorForm.value = {
    id: 0,
    title: '',
    category: '代码实践',
    summary: '',
    author_name: 'AI 赋能工作组',
    content_md: '# 实践标题\n\n## 背景与场景\n\n简要介绍金融场景。\n\n## 实施步骤\n\n1. 第一步\n2. 第二步\n\n## 提示词与代码\n\n```python\n# 核心代码\n```',
    is_pinned: false,
    is_published: true,
  }
  showEditorModal.value = true
}

async function openEditModal(art: ArticleItem) {
  isEditing.value = true
  try {
    const full = await api.getArticleDetail(art.id) as { data?: ArticleItem }
    const d = (full.data || art) as ArticleItem
    editorForm.value = {
      id: d.id,
      title: d.title,
      category: d.category,
      summary: d.summary || '',
      author_name: d.author_name,
      content_md: d.content_md,
      is_pinned: d.is_pinned,
      is_published: true,
    }
    showEditorModal.value = true
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '获取文章详情失败'
    alert(msg)
  }
}

async function handleSaveArticle() {
  if (!editorForm.value.title || !editorForm.value.content_md) {
    alert('请填写文章标题与 Markdown 正文')
    return
  }

  try {
    if (isEditing.value) {
      await api.updateArticle(editorForm.value.id, editorForm.value)
    } else {
      await api.createArticle(editorForm.value)
    }
    showEditorModal.value = false
    loadArticles()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '保存失败'
    alert(msg)
  }
}

async function handleDeleteArticle(art: ArticleItem) {
  if (!confirm(`确定要删除文章《${art.title}》吗？`)) return
  try {
    await api.deleteArticle(art.id)
    loadArticles()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '删除失败'
    alert(msg)
  }
}

function triggerUploadImage() {
  imageInputRef.value?.click()
}

async function handleImageSelected(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  uploadingImg.value = true
  const fd = new FormData()
  fd.append('file', file)

  try {
    const res = await api.uploadArticleImage(fd) as { url: string; original_filename?: string }
    const imgUrl = res.url
    const mdSnippet = `\n\n![${res.original_filename || 'image'}](${imgUrl})\n\n`
    editorForm.value.content_md += mdSnippet
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '图片上传失败'
    alert(msg)
  } finally {
    uploadingImg.value = false
    if (imageInputRef.value) imageInputRef.value.value = ''
  }
}

onMounted(() => {
  loadArticles()
})
</script>

<template>
  <div class="admin-articles-view">
    <div class="page-top-bar">
      <div>
        <h2 class="page-title">案例广场与实践文章管理</h2>
        <p class="page-desc">发布最佳实践经验文章，支持 Markdown 编写与本地配图托管</p>
      </div>

      <button class="primary-btn md-state-layer" @click="openCreateModal">
        <Plus :size="16" />
        <span>发布新文章</span>
      </button>
    </div>

    <!-- 文章列表 -->
    <div class="table-card studio-elevated-card">
      <table class="m3-admin-table">
        <thead>
          <tr>
            <th>文章标题</th>
            <th>分类</th>
            <th>作者</th>
            <th>阅读量</th>
            <th>置顶状态</th>
            <th>发布状态</th>
            <th>发布时间</th>
            <th style="text-align: right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="articles.length === 0">
            <td colspan="8" class="empty-cell">暂无案例文章</td>
          </tr>
          <tr v-for="art in articles" :key="art.id">
            <td class="font-bold">{{ art.title }}</td>
            <td>
              <span class="cat-pill">{{ art.category }}</span>
            </td>
            <td>{{ art.author_name }}</td>
            <td>{{ art.view_count }} 次</td>
            <td>
              <span v-if="art.is_pinned" class="pinned-tag">
                <Pin :size="11" /> 置顶
              </span>
              <span v-else class="text-muted">普通</span>
            </td>
            <td>
              <span class="pub-tag" :class="{ pub: art.is_published }">
                {{ art.is_published ? '已发布' : '草稿' }}
              </span>
            </td>
            <td class="time-cell">{{ art.created_at }}</td>
            <td style="text-align: right">
              <div class="row-actions">
                <button class="row-btn" title="编辑" @click="openEditModal(art)">
                  <Edit2 :size="14" />
                </button>
                <button class="row-btn danger" title="删除" @click="handleDeleteArticle(art)">
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 文章编辑器全屏/大弹窗 -->
    <AdaptiveModal
      :model-value="showEditorModal"
      :title="isEditing ? '编辑案例文章' : '撰写新案例文章'"
      max-width="840px"
      @update:model-value="showEditorModal = $event"
    >
      <div class="editor-modal-form">
        <div class="form-row">
          <div class="f-group" style="flex: 2">
            <label class="f-label">文章标题*</label>
            <input v-model="editorForm.title" type="text" class="m3-input" placeholder="输入鲜明的标题" />
          </div>
          <div class="f-group" style="flex: 1">
            <label class="f-label">所属分类</label>
            <select v-model="editorForm.category" class="m3-input">
              <option value="入门指南">入门指南</option>
              <option value="提效秘籍">提效秘籍</option>
              <option value="代码实践">代码实践</option>
              <option value="风控合规">风控合规</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="f-group" style="flex: 1">
            <label class="f-label">作者署名</label>
            <input v-model="editorForm.author_name" type="text" class="m3-input" />
          </div>
          <div class="f-group checkbox-row" style="flex: 1">
            <label class="cb-label">
              <input v-model="editorForm.is_pinned" type="checkbox" />
              <span>置顶推荐</span>
            </label>
            <label class="cb-label">
              <input v-model="editorForm.is_published" type="checkbox" />
              <span>正式发布</span>
            </label>
          </div>
        </div>

        <div class="f-group">
          <label class="f-label">文章简要摘要 (可选)</label>
          <input v-model="editorForm.summary" type="text" class="m3-input" placeholder="1-2句话概述亮点" />
        </div>

        <!-- Markdown 工具栏 -->
        <div class="md-editor-wrap">
          <div class="md-toolbar">
            <span class="md-tip">Markdown 正文编辑区</span>
            <button type="button" class="img-upload-btn md-state-layer" @click="triggerUploadImage">
              <ImageIcon :size="14" />
              <span>{{ uploadingImg ? '正在上传图片...' : '插入本地配图' }}</span>
            </button>
            <input
              ref="imageInputRef"
              type="file"
              accept="image/*"
              style="display: none"
              @change="handleImageSelected"
            />
          </div>
          <textarea
            v-model="editorForm.content_md"
            class="m3-textarea"
            rows="12"
            placeholder="支持标准 Markdown 语法排版..."
          />
        </div>

        <div class="modal-actions">
          <MdButton variant="text" @click="showEditorModal = false">取消</MdButton>
          <MdButton variant="filled" @click="handleSaveArticle">保存并发布</MdButton>
        </div>
      </div>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.admin-articles-view {
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

.primary-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
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

.font-bold { font-weight: 600; }
.time-cell { font-size: 12px; color: var(--md-sys-color-outline); }
.text-muted { color: var(--md-sys-color-outline); font-size: 12px; }

.cat-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
}

.pinned-tag {
  font-size: 11px;
  font-weight: 500;
  color: #B45309;
  background-color: #FEF3C7;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
}

.pub-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-outline);
}

.pub-tag.pub {
  background-color: #E6F4EA;
  color: #137333;
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
}

.row-btn:hover { background-color: var(--md-sys-color-surface-container-highest); }
.row-btn.danger:hover { color: var(--md-sys-color-error); }

.empty-cell {
  text-align: center;
  padding: 40px;
  color: var(--md-sys-color-outline);
}

/* 编辑器弹窗 */
.editor-modal-form {
  padding: 8px 4px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-row {
  display: flex;
  gap: 14px;
  align-items: flex-end;
}

.checkbox-row {
  display: flex;
  gap: 16px;
  padding-bottom: 8px;
}

.cb-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
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

.m3-input {
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  border: 1px solid var(--md-sys-color-outline);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 14px;
  outline: none;
}

.md-editor-wrap {
  border: 1px solid var(--md-sys-color-outline);
  border-radius: var(--md-sys-shape-corner-small);
  overflow: hidden;
}

.md-toolbar {
  padding: 8px 12px;
  background-color: var(--md-sys-color-surface-container);
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.md-tip {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface-variant);
}

.img-upload-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.m3-textarea {
  width: 100%;
  padding: 12px;
  border: none;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  resize: vertical;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
}
</style>
