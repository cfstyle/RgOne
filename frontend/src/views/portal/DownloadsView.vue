<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Download,
  Layers,
  FileText,
  Package,
  Check,
  Copy,
  Sparkles,
} from 'lucide-vue-next'
import { api } from '@/api'

interface DownloadFileItem {
  id: number
  category: string
  title: string
  version?: string | null
  description?: string | null
  file_name: string
  file_size: number
  sha256?: string | null
  download_count: number
  download_url?: string
  created_at?: string
  is_recommended?: boolean
}

const activeCategory = ref<string>('')
const files = ref<DownloadFileItem[]>([])
const loading = ref(false)
const copiedSha = ref<string>('')

const categories = [
  { label: '全部资料', val: '' },
  { label: '客户端安装包', val: 'installer' },
  { label: '使用手册', val: 'manual' },
  { label: '插件工具', val: 'plugin' },
  { label: '其他文件', val: 'other' },
]

async function loadFiles() {
  loading.value = true
  try {
    const res = await api.getFiles(activeCategory.value || undefined) as { data?: DownloadFileItem[] }
    files.value = res.data || []
  } catch (e) {
    console.error('加载文件失败', e)
  } finally {
    loading.value = false
  }
}

function handleCategoryChange(cat: string) {
  activeCategory.value = cat
  loadFiles()
}

async function copySha(sha: string) {
  if (!sha) return
  await navigator.clipboard.writeText(sha)
  copiedSha.value = sha
  setTimeout(() => {
    copiedSha.value = ''
  }, 2000)
}

function formatBytes(bytes: number) {
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
  <div class="downloads-view">
    <!-- 顶部介绍 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">资料与安装包下载中心</h2>
        <p class="page-desc">
          汇聚官方定制 DeepSeek Harness 客户端安装包、内网离线补丁、最佳实践操作手册与配套辅助工具
        </p>
      </div>

      <!-- 分类药丸按钮 -->
      <div class="category-pills">
        <button
          v-for="c in categories"
          :key="c.val"
          type="button"
          class="cat-pill"
          :class="{ active: activeCategory === c.val }"
          @click="handleCategoryChange(c.val)"
        >
          {{ c.label }}
        </button>
      </div>
    </div>

    <!-- 文件卡片网格 -->
    <div v-if="loading" class="loading-state">
      <span>正在检索资料列表...</span>
    </div>
    <div v-else-if="files.length === 0" class="empty-state">
      <span>当前分类下暂无已发布的资料</span>
    </div>
    <div v-else class="files-grid">
      <div
        v-for="item in files"
        :key="item.id"
        class="file-card studio-elevated-card"
        :class="{ 'is-recommended': item.is_recommended }"
      >
        <div class="file-card-top">
          <div class="file-icon-box">
            <Layers v-if="item.category === 'installer'" :size="20" />
            <FileText v-else-if="item.category === 'manual'" :size="20" />
            <Package v-else :size="20" />
          </div>
          <div class="file-badges">
            <span v-if="item.is_recommended" class="badge-rec">
              <Sparkles :size="12" />
              <span>官方主推</span>
            </span>
            <span v-if="item.version" class="badge-ver tabular-nums">{{ item.version }}</span>
          </div>
        </div>

        <div class="file-card-body">
          <h3 class="file-title">{{ item.title }}</h3>
          <p class="file-desc">{{ item.description || '暂无更新描述' }}</p>

          <div class="file-meta-row tabular-nums">
            <span>大小: {{ formatBytes(item.file_size) }}</span>
            <span>·</span>
            <span>已下载: {{ item.download_count }} 次</span>
            <span>·</span>
            <span>发布: {{ item.created_at ? item.created_at.substring(0, 10) : '-' }}</span>
          </div>

          <div v-if="item.sha256" class="sha-box">
            <span class="sha-label">SHA256:</span>
            <code class="sha-text">{{ item.sha256.substring(0, 16) }}...</code>
            <button class="sha-copy" title="复制完整 SHA256" @click="copySha(item.sha256)">
              <Check v-if="copiedSha === item.sha256" :size="12" />
              <Copy v-else :size="12" />
            </button>
          </div>
        </div>

        <div class="file-card-footer">
          <a :href="item.download_url" class="download-action-btn md-state-layer">
            <Download :size="15" />
            <span>立即高速下载</span>
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.downloads-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 4px;
}

.page-desc {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
}

.category-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.cat-pill {
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-primary-container);
  cursor: pointer;
  transition: all 0.2s;
}

.cat-pill.active {
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-weight: 600;
}

:root[data-theme="dark"] .cat-pill.active {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.loading-state,
.empty-state {
  padding: 80px 24px;
  text-align: center;
  color: var(--md-sys-color-outline);
  font-size: 14px;
}

.files-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.file-card {
  padding: 22px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
}

.file-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.file-icon-box {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-badges {
  display: flex;
  gap: 6px;
}

.badge-rec {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-size: 11px;
  font-weight: 600;
}

:root[data-theme="dark"] .badge-rec {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.badge-ver {
  padding: 3px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  font-size: 11px;
  font-weight: 500;
}

.file-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.file-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  line-height: 1.3;
}

.file-desc {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.5;
  flex: 1;
}

.file-meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--md-sys-color-outline);
}

.sha-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background-color: var(--md-sys-color-primary-container);
  border-radius: 6px;
  font-size: 11px;
}

.sha-label {
  color: var(--md-sys-color-outline);
}

.sha-text {
  font-family: "Cascadia Mono", monospace;
  color: var(--md-sys-color-on-surface);
}

.sha-copy {
  display: flex;
  align-items: center;
  color: var(--md-sys-color-outline);
  cursor: pointer;
}

.sha-copy:hover {
  color: var(--md-sys-color-on-surface);
}

.file-card-footer {
  margin-top: 8px;
}

.download-action-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: opacity 0.2s;
}

.download-action-btn:hover {
  opacity: 0.9;
}

:root[data-theme="dark"] .download-action-btn {
  background-color: #FFFFFF;
  color: #1F1F1F;
}
</style>
