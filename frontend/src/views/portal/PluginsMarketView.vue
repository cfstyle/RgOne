<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  CheckCircle2,
  Clock,
  Copy,
  Download,
  ExternalLink,
  FolderGit2,
  Layers,
  Package,
  Plus,
  Puzzle,
  RefreshCw,
  Search,
  SearchX,
  Upload,
  User,
  X,
} from 'lucide-vue-next'
import AdaptiveModal from '@/components/m3/AdaptiveModal.vue'
import MdButton from '@/components/m3/MdButton.vue'
import MdCard from '@/components/m3/MdCard.vue'
import MdDrawer from '@/components/m3/MdDrawer.vue'
import { api } from '@/api'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { copyToClipboard } from '@/utils/clipboard'
import type { PluginItem } from '@/types/mcp'

const toast = useToast()
const authStore = useAuthStore()

const isLoggedIn = computed(() => authStore.isEmployeeLoggedIn)

const loading = ref(true)
const plugins = ref<PluginItem[]>([])
const categories = ref<string[]>([])
const registryUrl = ref('')
const marketUrl = ref('')
const selectedCategory = ref('全部')
const searchKeyword = ref('')

// 详情抽屉
const detailDrawerVisible = ref(false)
const loadingDetail = ref(false)
const activePlugin = ref<PluginItem | null>(null)

// 我的投稿抽屉
const mySubmissionsDrawerVisible = ref(false)
const loadingSubmissions = ref(false)
const mySubmissions = ref<PluginItem[]>([])

// 投稿弹窗
const submitModalVisible = ref(false)
const submitting = ref(false)
const submitForm = reactive<{
  submit_source: 'tgz' | 'git'
  display_name: string
  category: string
  tags: string
  description: string
  name: string
  version: string
  repo_url: string
  changelog: string
}>({
  submit_source: 'tgz',
  display_name: '',
  category: '效率工具',
  tags: '',
  description: '',
  name: '',
  version: '1.0.0',
  repo_url: '',
  changelog: '',
})
const tgzFile = ref<File | null>(null)

let abortController: AbortController | null = null

const availableCategories = computed(() => ['全部', ...categories.value])

const filteredPlugins = computed(() => {
  return plugins.value.filter((item) => {
    if (selectedCategory.value !== '全部' && item.category !== selectedCategory.value) {
      return false
    }
    const kw = searchKeyword.value.trim().toLowerCase()
    if (!kw) return true
    return (
      item.name.toLowerCase().includes(kw) ||
      item.display_name.toLowerCase().includes(kw) ||
      (item.description || '').toLowerCase().includes(kw) ||
      item.tags.some((t) => t.toLowerCase().includes(kw))
    )
  })
})

function openEmployeeLogin() {
  window.dispatchEvent(
    new CustomEvent('rgone:open-login', {
      detail: { mode: 'employee' },
    })
  )
}

async function fetchPlugins() {
  if (abortController) abortController.abort()
  abortController = new AbortController()
  loading.value = true
  try {
    const res = await api.getMarketPlugins()
    plugins.value = res.items || []
    categories.value = res.categories || []
    registryUrl.value = res.registry || ''
    marketUrl.value = res.market_url || ''
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '加载插件市场失败')
  } finally {
    loading.value = false
  }
}

async function openDetail(plugin: PluginItem) {
  detailDrawerVisible.value = true
  loadingDetail.value = true
  activePlugin.value = plugin
  try {
    activePlugin.value = await api.getMarketPluginDetail(plugin.id)
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '获取插件详情失败')
  } finally {
    loadingDetail.value = false
  }
}

async function handleCopyInstall(plugin: PluginItem) {
  const cmd =
    plugin.install_command ||
    `dsh plugin install ${plugin.name}${registryUrl.value ? ` --registry ${registryUrl.value}` : ''}`
  const ok = await copyToClipboard(cmd)
  if (ok) {
    toast.success('安装命令已复制到剪贴板')
    void api.recordPluginDownloadHit(plugin.id).then((res) => {
      plugin.downloads = res.downloads
    }).catch(() => undefined)
  } else {
    toast.error('复制失败，请手动复制')
  }
}

function openSubmitModal() {
  if (!isLoggedIn.value) {
    toast.info('投稿插件需先登录小秘书工号')
    openEmployeeLogin()
    return
  }
  submitForm.submit_source = 'tgz'
  submitForm.display_name = ''
  submitForm.category = '效率工具'
  submitForm.tags = ''
  submitForm.description = ''
  submitForm.name = ''
  submitForm.version = '1.0.0'
  submitForm.repo_url = ''
  submitForm.changelog = ''
  tgzFile.value = null
  submitModalVisible.value = true
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  tgzFile.value = input.files?.[0] || null
}

async function handleSubmitPlugin() {
  if (submitForm.submit_source === 'tgz' && !tgzFile.value) {
    toast.warning('请选择打包好的 .tgz 插件包')
    return
  }
  if (
    submitForm.submit_source === 'git' &&
    (!submitForm.name.trim() || !submitForm.version.trim() || !submitForm.repo_url.trim())
  ) {
    toast.warning('Git 投稿需填写合法的包名、版本号及仓库地址')
    return
  }

  const fd = new FormData()
  fd.append('submit_source', submitForm.submit_source)
  fd.append('display_name', submitForm.display_name.trim())
  fd.append('category', submitForm.category.trim() || '效率工具')
  fd.append('tags', submitForm.tags.trim())
  fd.append('description', submitForm.description.trim())
  fd.append('changelog', submitForm.changelog.trim())
  if (submitForm.submit_source === 'tgz' && tgzFile.value) {
    fd.append('file', tgzFile.value)
  } else {
    fd.append('name', submitForm.name.trim())
    fd.append('version', submitForm.version.trim())
    fd.append('repo_url', submitForm.repo_url.trim())
  }

  submitting.value = true
  try {
    const res = await api.submitPlugin(fd)
    toast.success(res.message || '投稿已提交，等待审核')
    submitModalVisible.value = false
    await loadMySubmissions()
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '投稿失败')
  } finally {
    submitting.value = false
  }
}

async function loadMySubmissions() {
  if (!isLoggedIn.value) {
    mySubmissions.value = []
    return
  }
  loadingSubmissions.value = true
  try {
    const res = await api.getMyPluginSubmissions()
    mySubmissions.value = res.items || []
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : '加载我的投稿失败')
  } finally {
    loadingSubmissions.value = false
  }
}

function openMySubmissionsDrawer() {
  if (!isLoggedIn.value) {
    openEmployeeLogin()
    return
  }
  mySubmissionsDrawerVisible.value = true
  void loadMySubmissions()
}

watch(
  () => authStore.empToken,
  () => {
    void loadMySubmissions()
  }
)

onMounted(() => {
  void fetchPlugins()
  if (isLoggedIn.value) {
    void loadMySubmissions()
  }
})

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="market-page">
    <!-- 顶部检索与发布栏 -->
    <div class="market-toolbar">
      <div class="toolbar-search">
        <Search :size="16" class="search-icon" />
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索插件名称、@rgone/* 包名、标签..."
          class="search-input"
        />
        <button
          v-if="searchKeyword"
          type="button"
          class="search-clear-btn"
          @click="searchKeyword = ''"
        >
          <X :size="14" />
        </button>
      </div>

      <div class="toolbar-actions">
        <MdButton variant="filled" @click="openSubmitModal">
          <Plus :size="15" />
          <span>发布 / 投稿插件</span>
        </MdButton>
        <MdButton v-if="isLoggedIn" variant="tonal" @click="openMySubmissionsDrawer">
          <Layers :size="15" />
          <span>我的投稿</span>
          <span v-if="mySubmissions.length > 0" class="count-pill">{{ mySubmissions.length }}</span>
        </MdButton>
        <MdButton v-else variant="tonal" @click="openEmployeeLogin">
          <User :size="15" />
          <span>登录投稿</span>
        </MdButton>
        <MdButton variant="text" :disabled="loading" @click="fetchPlugins">
          <RefreshCw :size="15" :class="{ 'is-spinning': loading }" />
          <span>刷新</span>
        </MdButton>
      </div>
    </div>

    <!-- Hero 介绍卡片 -->
    <MdCard variant="tonal" class="market-hero">
      <div class="hero-row">
        <div class="hero-copy">
          <div class="hero-badge">
            <Puzzle :size="14" />
            <span>企业内部 DSH 离线插件市场</span>
          </div>
          <h1>发现并安装行内专属 Harness 插件</h1>
          <p>
            所有插件托管于内网离线 Verdaccio 私有源（zero-internet），经小秘书安全审核后自动发布；下载四合一
            <code>cordis.patch.yml</code> 即可在客户端直接浏览与一键安装。
          </p>
        </div>
        <div v-if="marketUrl" class="endpoint-badges">
          <div class="endpoint-item">
            <span class="ep-label">Market Index</span>
            <code class="mono ep-val">{{ marketUrl }}</code>
          </div>
          <div class="endpoint-item">
            <span class="ep-label">Registry</span>
            <code class="mono ep-val">{{ registryUrl }}</code>
          </div>
        </div>
      </div>
    </MdCard>

    <!-- 分类过滤 -->
    <div class="category-bar">
      <button
        v-for="cat in availableCategories"
        :key="cat"
        type="button"
        :class="['cat-pill', { 'is-active': selectedCategory === cat }]"
        @click="selectedCategory = cat"
      >
        {{ cat }}
      </button>
    </div>

    <!-- 插件网格 -->
    <div v-if="loading && !plugins.length" class="empty-box">
      <RefreshCw :size="24" class="is-spinning" />
      <span>正在加载插件市场...</span>
    </div>

    <MdCard v-else-if="!filteredPlugins.length" variant="filled">
      <div class="empty-box">
        <SearchX :size="36" />
        <h3>暂无匹配的已发布插件</h3>
        <p>您可以点击右上角「发布 / 投稿插件」成为首位企业插件贡献者</p>
      </div>
    </MdCard>

    <div v-else class="plugins-grid">
      <MdCard v-for="plugin in filteredPlugins" :key="plugin.id" variant="elevated" class="plugin-card">
        <div class="plugin-head">
          <div class="plugin-avatar">
            <Package :size="22" />
          </div>
          <div class="plugin-title-col">
            <div class="plugin-title-row">
              <h3>{{ plugin.display_name || plugin.name }}</h3>
              <span class="ver-badge">v{{ plugin.latest_version }}</span>
            </div>
            <div class="mono pkg-name">{{ plugin.name }}</div>
          </div>
        </div>

        <p class="plugin-desc">{{ plugin.description || '企业级 DeepSeek Harness 扩展插件' }}</p>

        <div class="plugin-tags">
          <span class="cat-tag">{{ plugin.category }}</span>
          <span v-for="tag in plugin.tags.slice(0, 3)" :key="tag" class="tag-chip">{{ tag }}</span>
        </div>

        <div class="plugin-meta">
          <span>作者: {{ plugin.author_name || plugin.author_emp_no }}</span>
          <span><Download :size="13" /> {{ plugin.downloads }}</span>
        </div>

        <div class="plugin-footer">
          <MdButton variant="tonal" @click="openDetail(plugin)">查看详情</MdButton>
          <MdButton variant="filled" @click="handleCopyInstall(plugin)">
            <Copy :size="14" />
            <span>复制安装指令</span>
          </MdButton>
        </div>
      </MdCard>
    </div>

    <!-- 插件详情抽屉 -->
    <MdDrawer
      v-model="detailDrawerVisible"
      :title="activePlugin ? activePlugin.display_name || activePlugin.name : '插件详情'"
      width="640px"
    >
      <div v-if="loadingDetail && !activePlugin" class="empty-box">加载中...</div>
      <div v-else-if="activePlugin" class="drawer-body">
        <MdCard variant="tonal">
          <div class="detail-top">
            <div>
              <h3>{{ activePlugin.display_name }}</h3>
              <div class="mono pkg-name">{{ activePlugin.name }} · v{{ activePlugin.latest_version }}</div>
            </div>
            <span class="cat-tag">{{ activePlugin.category }}</span>
          </div>
          <p class="detail-desc">{{ activePlugin.description || '暂无说明' }}</p>
          <div v-if="activePlugin.repo_url" class="repo-row">
            <FolderGit2 :size="14" />
            <a :href="activePlugin.repo_url" target="_blank" rel="noopener noreferrer">
              <span>{{ activePlugin.repo_url }}</span>
              <ExternalLink :size="12" />
            </a>
          </div>
        </MdCard>

        <div class="install-box">
          <div class="box-head">
            <strong>CLI 安装指令</strong>
            <MdButton variant="tonal" @click="handleCopyInstall(activePlugin)">
              <Copy :size="14" />
              <span>复制</span>
            </MdButton>
          </div>
          <pre class="code-pre"><code>{{
            activePlugin.install_command || `dsh plugin install ${activePlugin.name}`
          }}</code></pre>
        </div>

        <div v-if="activePlugin.versions?.length" class="versions-box">
          <h4>历史已发布版本</h4>
          <div v-for="ver in activePlugin.versions" :key="ver.id" class="ver-row">
            <div class="ver-row-head">
              <strong>v{{ ver.version }}</strong>
              <span class="mono sub-text">{{
                ver.published_at ? ver.published_at.slice(0, 10) : ''
              }}</span>
            </div>
            <p class="ver-changelog">{{ ver.changelog || '标准版本发布' }}</p>
          </div>
        </div>
      </div>
    </MdDrawer>

    <!-- 我的投稿抽屉 -->
    <MdDrawer v-model="mySubmissionsDrawerVisible" title="我的插件投稿与审核状态" width="600px">
      <div v-if="loadingSubmissions" class="empty-box">加载中...</div>
      <div v-else-if="!mySubmissions.length" class="empty-box">暂无投稿记录</div>
      <div v-else class="sub-list">
        <MdCard v-for="item in mySubmissions" :key="item.id" variant="filled">
          <div class="sub-head">
            <div>
              <strong>{{ item.display_name || item.name }}</strong>
              <div class="mono pkg-name">{{ item.name }}</div>
            </div>
            <span class="status-pill" :class="`st-${item.status}`">{{ item.status }}</span>
          </div>
          <div v-if="item.versions?.length" class="sub-versions">
            <div v-for="v in item.versions" :key="v.id" class="sub-ver-item">
              <div class="sub-ver-top">
                <span>v{{ v.version }} ({{ v.submit_source }})</span>
                <span class="review-pill" :class="`rv-${v.review_status}`">
                  <CheckCircle2 v-if="v.review_status === 'approved'" :size="12" />
                  <Clock v-else :size="12" />
                  <span>{{ v.review_status }}</span>
                </span>
              </div>
              <p v-if="v.review_comment" class="rv-comment">审核意见: {{ v.review_comment }}</p>
            </div>
          </div>
        </MdCard>
      </div>
    </MdDrawer>

    <!-- 发布/投稿插件弹窗 -->
    <AdaptiveModal
      v-model="submitModalVisible"
      title="投稿插件至企业市场"
      description="支持直接上传合法 @rgone/* .tgz 插件包或提交内网 Git 仓库地址，审核通过后将自动推送至 Verdaccio。"
      max-width="600px"
    >
      <div class="submit-form">
        <div class="source-tabs">
          <button
            type="button"
            :class="['source-btn', { 'is-active': submitForm.submit_source === 'tgz' }]"
            @click="submitForm.submit_source = 'tgz'"
          >
            上传 .tgz 压缩包（推荐）
          </button>
          <button
            type="button"
            :class="['source-btn', { 'is-active': submitForm.submit_source === 'git' }]"
            @click="submitForm.submit_source = 'git'"
          >
            内网 Git 仓库投稿
          </button>
        </div>

        <label v-if="submitForm.submit_source === 'tgz'" class="upload-box">
          <Upload :size="22" />
          <span>{{ tgzFile ? tgzFile.name : '选择符合 npm 结构的 @rgone/*.tgz 文件（<= 20MB）' }}</span>
          <input type="file" accept=".tgz,.tar.gz" class="hidden-input" @change="handleFileSelect" />
        </label>

        <template v-else>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">npm 包名 *</label>
              <input
                v-model="submitForm.name"
                type="text"
                placeholder="@rgone/dsh-my-plugin"
                class="form-input mono"
              />
            </div>
            <div class="form-item">
              <label class="form-label">SemVer 版本号 *</label>
              <input
                v-model="submitForm.version"
                type="text"
                placeholder="1.0.0"
                class="form-input mono"
              />
            </div>
          </div>
          <div class="form-item">
            <label class="form-label">内网 Git 仓库地址 *</label>
            <input
              v-model="submitForm.repo_url"
              type="text"
              placeholder="https://gitlab.internal/team/dsh-my-plugin.git"
              class="form-input"
            />
          </div>
        </template>

        <div class="form-row-2">
          <div class="form-item">
            <label class="form-label">展示名称</label>
            <input
              v-model="submitForm.display_name"
              type="text"
              placeholder="留空默认取包名"
              class="form-input"
            />
          </div>
          <div class="form-item">
            <label class="form-label">插件分类</label>
            <input
              v-model="submitForm.category"
              type="text"
              placeholder="效率工具 / 研发协作 / 数据分析"
              class="form-input"
            />
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">标签（逗号分隔）</label>
          <input
            v-model="submitForm.tags"
            type="text"
            placeholder="例如：代码审查, 快捷键, MCP"
            class="form-input"
          />
        </div>

        <div class="form-item">
          <label class="form-label">插件简介</label>
          <textarea
            v-model="submitForm.description"
            rows="2"
            placeholder="简述核心功能与适用场景"
            class="form-textarea"
          ></textarea>
        </div>

        <div class="form-item">
          <label class="form-label">更新日志 (Changelog)</label>
          <textarea
            v-model="submitForm.changelog"
            rows="2"
            placeholder="本次版本变更要点"
            class="form-textarea"
          ></textarea>
        </div>
      </div>

      <template #footer>
        <div class="modal-footer-actions">
          <MdButton variant="text" @click="submitModalVisible = false">取消</MdButton>
          <MdButton variant="filled" :disabled="submitting" @click="handleSubmitPlugin">
            {{ submitting ? '正在校验与提交...' : '提交审核' }}
          </MdButton>
        </div>
      </template>
    </AdaptiveModal>
  </div>
</template>

<style scoped>
.market-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.market-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.toolbar-search {
  position: relative;
  flex: 1;
  min-width: 260px;
  max-width: 440px;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 14px;
  color: var(--md-sys-color-on-surface-variant);
}

.search-input {
  width: 100%;
  height: 40px;
  padding: 0 36px 0 40px;
  border-radius: var(--md-sys-shape-corner-full);
  border: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface);
  font-size: 14px;
  outline: none;
}

.search-clear-btn {
  position: absolute;
  right: 10px;
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.count-pill {
  padding: 0 6px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-size: 11px;
  font-weight: 700;
}

.hero-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}

.hero-copy {
  flex: 1;
  min-width: 280px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-primary);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 10px;
}

.hero-copy h1 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 700;
}

.hero-copy p {
  margin: 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.endpoint-badges {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.endpoint-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-lowest);
}

.ep-label {
  font-size: 11px;
  color: var(--md-sys-color-on-surface-variant);
}

.ep-val {
  font-size: 12px;
}

.category-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.cat-pill {
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.cat-pill.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}

.plugins-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 1100px) {
  .plugins-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .plugins-grid {
    grid-template-columns: 1fr;
  }
}

.plugin-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plugin-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.plugin-avatar {
  width: 42px;
  height: 42px;
  border-radius: var(--md-sys-shape-corner-medium);
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-primary-container);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.plugin-title-col {
  flex: 1;
  min-width: 0;
}

.plugin-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.plugin-title-row h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.ver-badge,
.cat-tag,
.tag-chip,
.status-pill,
.review-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 11px;
  font-weight: 600;
}

.ver-badge {
  background-color: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
}

.pkg-name {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.plugin-desc {
  margin: 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.5;
  min-height: 38px;
}

.plugin-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.cat-tag {
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface);
}

.tag-chip {
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
}

.plugin-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  padding-top: 8px;
  border-top: 1px solid var(--md-sys-color-outline-variant);
}

.plugin-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.plugin-footer {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.drawer-body,
.sub-list,
.submit-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-top,
.sub-head,
.sub-ver-top,
.ver-row-head,
.box-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.detail-top h3 {
  margin: 0 0 2px;
}

.detail-desc {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.repo-row {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.repo-row a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--md-sys-color-primary);
}

.code-pre {
  margin: 8px 0 0;
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  overflow-x: auto;
}

.versions-box h4 {
  margin: 0 0 8px;
  font-size: 14px;
}

.ver-row,
.sub-ver-item {
  padding: 10px 12px;
  border-radius: var(--md-sys-shape-corner-small);
  background-color: var(--md-sys-color-surface-container-low);
}

.ver-changelog,
.rv-comment {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
}

.status-pill.st-published,
.review-pill.rv-approved {
  background-color: var(--sys-status-success-bg);
  color: var(--sys-status-success-text);
}

.status-pill.st-pending,
.review-pill.rv-pending {
  background-color: var(--sys-status-warning-bg);
  color: var(--sys-status-warning-text);
}

.status-pill.st-rejected,
.review-pill.rv-rejected {
  background-color: var(--sys-status-danger-bg);
  color: var(--sys-status-danger-text);
}

.source-tabs {
  display: flex;
  gap: 8px;
}

.source-btn {
  padding: 7px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 12px;
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
}

.source-btn.is-active {
  background-color: var(--md-sys-color-primary);
  color: var(--md-sys-color-on-primary);
  font-weight: 600;
}

.upload-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  border-radius: var(--md-sys-shape-corner-medium);
  border: 1px dashed var(--md-sys-color-outline);
  background-color: var(--md-sys-color-surface-container-low);
  color: var(--md-sys-color-on-surface-variant);
  font-size: 13px;
  cursor: pointer;
}

.hidden-input {
  display: none;
}

.form-row-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
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
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 36px 16px;
  text-align: center;
  color: var(--md-sys-color-on-surface-variant);
}

.empty-box h3 {
  margin: 0;
  font-size: 16px;
  color: var(--md-sys-color-on-surface);
}

.empty-box p {
  margin: 0;
  font-size: 13px;
}

.sub-text {
  font-size: 11px;
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
