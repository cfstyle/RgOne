<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Pin,
  Eye,
  Calendar,
  User,
  Search,
  ArrowLeft,
} from 'lucide-vue-next'
import { api } from '@/api'

export interface ArticleItem {
  id: number
  title: string
  category: string
  summary: string
  content_md: string
  author_name: string
  cover_image?: string
  tags?: string[]
  view_count: number
  is_pinned?: boolean
  created_at: string
}

const articles = ref<ArticleItem[]>([])
const activeCategory = ref<string>('')
const keyword = ref<string>('')
const loading = ref(false)

// 当前正在查看的文章详情
const currentArticle = ref<ArticleItem | null>(null)
const loadingDetail = ref(false)

const categories = ['全部', '入门指南', '提效秘籍', '代码实践', '风控合规']

async function loadArticles() {
  loading.value = true
  try {
    const cat = activeCategory.value === '全部' ? undefined : activeCategory.value
    const res = await api.getArticles(cat, keyword.value || undefined) as { items?: ArticleItem[] }
    articles.value = res.items || []
  } catch (e) {
    console.error('加载文章失败', e)
  } finally {
    loading.value = false
  }
}

async function viewArticle(id: number) {
  loadingDetail.value = true
  try {
    const res = await api.getArticleDetail(id) as { data?: ArticleItem }
    currentArticle.value = res.data || null
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '加载详情失败'
    alert(msg)
  } finally {
    loadingDetail.value = false
  }
}

function handleBack() {
  currentArticle.value = null
  loadArticles()
}

function isSafeUrl(rawUrl: string): boolean {
  const trimmed = rawUrl.trim()
  if (!trimmed) return false
  if (trimmed.startsWith('/') || trimmed.startsWith('./') || trimmed.startsWith('../')) {
    return true
  }
  try {
    const parsed = new URL(trimmed)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function escapeAttr(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

const ALLOWED_TAGS = new Set([
  'DIV', 'P', 'H1', 'H2', 'H3', 'H4', 'BLOCKQUOTE', 'UL', 'OL', 'LI',
  'PRE', 'CODE', 'STRONG', 'EM', 'IMG', 'A', 'SPAN', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD'
])

// 彻底拦截并连同子树整体销毁的危险标签
const FORBIDDEN_TAGS = new Set([
  'SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'MATH',
  'FORM', 'INPUT', 'BUTTON', 'SELECT', 'TEXTAREA', 'LINK', 'META', 'BASE', 'FRAME', 'FRAMESET'
])

function cleanNode(node: Node) {
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return
  }
  const el = node as HTMLElement
  const tagName = el.tagName.toUpperCase()

  // 1. 危险黑名单标签：彻底整体删除节点及其所有子内容，杜绝隐藏代码执行
  if (FORBIDDEN_TAGS.has(tagName)) {
    el.remove()
    return
  }

  // 2. 非白名单未知标签：在提升前先递归深度清洗整棵子树，确保直接与间接子节点受白名单约束
  // 然后拆除当前未知容器（unwrap），将其子节点提升到父级
  if (!ALLOWED_TAGS.has(tagName)) {
    const children = Array.from(el.childNodes)
    for (const child of children) {
      cleanNode(child)
    }
    const parent = el.parentNode
    if (parent) {
      while (el.firstChild) {
        parent.insertBefore(el.firstChild, el)
      }
      el.remove()
    } else {
      el.remove()
    }
    return
  }

  // 3. 白名单合法标签：严格过滤属性，剥除所有 on* 事件及非白名单属性
  const attrs = Array.from(el.attributes)
  for (const attr of attrs) {
    const attrName = attr.name.toLowerCase()
    if (attrName.startsWith('on')) {
      el.removeAttribute(attr.name)
      continue
    }
    if (tagName === 'A') {
      if (!['href', 'target', 'rel', 'class'].includes(attrName)) {
        el.removeAttribute(attr.name)
      } else if (attrName === 'href' && !isSafeUrl(attr.value)) {
        el.setAttribute('href', '#')
      }
    } else if (tagName === 'IMG') {
      if (!['src', 'alt', 'class', 'loading'].includes(attrName)) {
        el.removeAttribute(attr.name)
      } else if (attrName === 'src' && !isSafeUrl(attr.value)) {
        el.removeAttribute('src')
      }
    } else if (attrName !== 'class') {
      el.removeAttribute(attr.name)
    }
  }

  // 4. 递归清洗当前合法容器内的全部子节点
  const children = Array.from(el.childNodes)
  for (const child of children) {
    cleanNode(child)
  }
}

function cleanElementNode(node: Node) {
  const children = Array.from(node.childNodes)
  for (const child of children) {
    cleanNode(child)
  }
}

function sanitizeHtml(dirty: string): string {
  if (typeof window === 'undefined' || !window.DOMParser) {
    return dirty.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
  }
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(dirty, 'text/html')
    cleanElementNode(doc.body)
    return doc.body.innerHTML
  } catch {
    return escapeHtml(dirty)
  }
}

// 离线安全的 Markdown 转 HTML（白名单安全净化、属性引号转义、协议校验、支持本地图片）
function renderSafeMarkdown(md: string): string {
  if (!md) return ''
  let html = escapeHtml(md)

  // 代码块 ```lang ... ```
  html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    return `<div class="md-code-block"><div class="code-header"><span>${escapeAttr(lang || 'code')}</span></div><pre><code>${code}</code></pre></div>`
  })

  // 行内代码 `...`
  html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>')

  // 图片 ![alt](url) - 校验安全 URL 并对属性引号统一编码
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, rawAlt, rawUrl) => {
    const cleanUrl = isSafeUrl(rawUrl) ? escapeAttr(rawUrl.trim()) : ''
    if (!cleanUrl) return ''
    const safeAlt = escapeAttr(rawAlt)
    return `<div class="md-img-wrap"><img src="${cleanUrl}" alt="${safeAlt}" loading="lazy" /><span class="img-caption">${safeAlt}</span></div>`
  })

  // 链接 [text](url) - 校验安全协议并对属性引号统一编码
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, rawText, rawUrl) => {
    const cleanUrl = isSafeUrl(rawUrl) ? escapeAttr(rawUrl.trim()) : '#'
    const safeText = escapeAttr(rawText)
    return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="md-link">${safeText}</a>`
  })

  // 标题
  html = html.replace(/^### (.*$)/gim, '<h3 class="md-h3">$1</h3>')
  html = html.replace(/^## (.*$)/gim, '<h2 class="md-h2">$1</h2>')
  html = html.replace(/^# (.*$)/gim, '<h1 class="md-h1">$1</h1>')

  // 引用块 >
  html = html.replace(/^> (.*$)/gim, '<blockquote class="md-quote">$1</blockquote>')

  // 粗体
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  // 无序列表
  html = html.replace(/^\* (.*$)/gim, '<li class="md-li">$1</li>')
  html = html.replace(/^- (.*$)/gim, '<li class="md-li">$1</li>')

  // 换行段落
  html = html.replace(/\n\n/g, '<p class="md-p"></p>')

  return sanitizeHtml(html)
}

onMounted(() => {
  loadArticles()
})
</script>

<template>
  <div class="articles-view">
    <!-- 详情模式 -->
    <div v-if="currentArticle" class="article-detail-container">
      <button class="back-nav-btn md-state-layer" @click="handleBack">
        <ArrowLeft :size="16" />
        <span>返回案例列表</span>
      </button>

      <article class="article-sheet">
        <header class="sheet-header">
          <div class="sheet-category-badge">{{ currentArticle.category }}</div>
          <h1 class="sheet-title">{{ currentArticle.title }}</h1>
          <div class="sheet-meta">
            <span><User :size="14" /> {{ currentArticle.author_name }}</span>
            <span>·</span>
            <span><Calendar :size="14" /> {{ currentArticle.created_at }}</span>
            <span>·</span>
            <span><Eye :size="14" /> {{ currentArticle.view_count }} 次阅读</span>
          </div>
          <div v-if="currentArticle.tags?.length" class="sheet-tags">
            <span v-for="t in currentArticle.tags" :key="t" class="tag-chip">
              #{{ t }}
            </span>
          </div>
        </header>

        <div class="sheet-summary-box" v-if="currentArticle.summary">
          <strong>摘要：</strong>{{ currentArticle.summary }}
        </div>

        <div class="sheet-body" v-html="renderSafeMarkdown(currentArticle.content_md)" />
      </article>
    </div>

    <!-- 列表模式 -->
    <div v-else class="articles-list-container">
      <div class="page-header">
        <div class="header-left">
          <h2 class="page-title">大模型落地最佳实践与案例广场</h2>
          <p class="page-desc">
            汇聚全行各部门在代码辅助重构、复杂 SQL 优化、金融风控建模与长文档分析中的优秀落地实战文章
          </p>
        </div>

        <div class="search-box">
          <Search :size="18" class="search-icon" />
          <input
            v-model="keyword"
            type="text"
            class="search-input"
            placeholder="搜索文章标题或关键词..."
            @keyup.enter="loadArticles"
          />
        </div>
      </div>

      <!-- 分类过滤 -->
      <div class="category-tabs-bar">
        <button
          v-for="c in categories"
          :key="c"
          type="button"
          class="cat-tab"
          :class="{ active: (activeCategory || '全部') === c }"
          @click="activeCategory = c; loadArticles()"
        >
          {{ c }}
        </button>
      </div>

      <!-- 列表网格 -->
      <div v-if="loading" class="loading-state">
        <span>正在加载文章案例...</span>
      </div>
      <div v-else-if="articles.length === 0" class="empty-state">
        <span>未搜索到匹配的文章案例</span>
      </div>
      <div v-else class="articles-grid">
        <div
          v-for="item in articles"
          :key="item.id"
          class="article-card studio-elevated-card md-state-layer"
          @click="viewArticle(item.id)"
        >
          <div class="card-top">
            <span class="card-cat">{{ item.category }}</span>
            <span v-if="item.is_pinned" class="status-pill warning">
              <Pin :size="12" />
              <span>置顶</span>
            </span>
          </div>

          <h3 class="card-title">{{ item.title }}</h3>
          <p class="card-summary">{{ item.summary || '点击阅读完整实践案例...' }}</p>

          <div class="card-footer tabular-nums">
            <div class="author-info">
              <User :size="13" />
              <span>{{ item.author_name }}</span>
            </div>
            <div class="views-info">
              <Eye :size="13" />
              <span>{{ item.view_count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.articles-view {
  display: flex;
  flex-direction: column;
}

/* 列表头部 */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
}

.page-title {
  font-size: 22px;
  font-weight: 800;
  color: var(--md-sys-color-on-surface);
  margin-bottom: 4px;
}

.page-desc {
  font-size: 14px;
  color: var(--md-sys-color-on-surface-variant);
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 14px;
  color: var(--md-sys-color-outline);
  pointer-events: none;
}

.search-input {
  width: 280px;
  padding: 10px 14px 10px 42px;
  border-radius: var(--md-sys-shape-corner-full);
  border: 1px solid var(--md-sys-color-outline);
  background-color: var(--md-sys-color-surface-container);
  color: var(--md-sys-color-on-surface);
  font-size: 14px;
  outline: none;
}

.search-input:focus {
  border-color: var(--md-sys-color-primary);
}

.category-tabs-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  padding-bottom: 12px;
  overflow-x: auto;
}

.cat-tab {
  padding: 8px 18px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-primary-container);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.cat-tab.active {
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-weight: 600;
}

:root[data-theme="dark"] .cat-tab.active {
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

.articles-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.article-card {
  padding: 22px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
  cursor: pointer;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-cat {
  font-size: 12px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  background-color: var(--md-sys-color-primary-container);
  padding: 3px 8px;
  border-radius: 4px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
  line-height: 1.4;
}

.card-summary {
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.6;
  flex: 1;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--md-sys-color-outline);
  border-top: 1px solid var(--md-sys-color-outline-variant);
  padding-top: 10px;
}

.author-info,
.views-info {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 详情文章纸张 */
.article-detail-container {
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.back-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: #1F1F1F;
  color: #FFFFFF;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 20px;
}

:root[data-theme="dark"] .back-nav-btn {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.article-sheet {
  padding: 36px;
}

.sheet-header {
  margin-bottom: 24px;
}

.sheet-category-badge {
  display: inline-block;
  font-size: 13px;
  font-weight: 700;
  color: var(--md-sys-color-primary);
  background-color: var(--md-sys-color-primary-container);
  padding: 4px 10px;
  border-radius: 4px;
  margin-bottom: 12px;
}

.sheet-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--md-sys-color-on-surface);
  line-height: 1.3;
  margin-bottom: 14px;
}

.sheet-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--md-sys-color-outline);
  margin-bottom: 12px;
}

.sheet-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sheet-tags {
  display: flex;
  gap: 6px;
}

.tag-chip {
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-surface-container-high);
  padding: 2px 8px;
  border-radius: 4px;
}

.sheet-summary-box {
  padding: 16px 20px;
  background-color: var(--md-sys-color-surface-container);
  border-left: 4px solid var(--md-sys-color-primary);
  border-radius: 0 var(--md-sys-shape-corner-small) var(--md-sys-shape-corner-small) 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--md-sys-color-on-surface-variant);
  margin-bottom: 30px;
}

.sheet-body {
  font-size: 15px;
  line-height: 1.8;
  color: var(--md-sys-color-on-surface);
}

:deep(.md-h1) {
  font-size: 24px;
  font-weight: 800;
  margin: 32px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
}

:deep(.md-h2) {
  font-size: 20px;
  font-weight: 700;
  margin: 28px 0 12px;
}

:deep(.md-h3) {
  font-size: 17px;
  font-weight: 700;
  margin: 20px 0 10px;
}

:deep(.md-p) {
  margin-bottom: 16px;
}

:deep(.md-li) {
  margin-left: 20px;
  margin-bottom: 6px;
}

:deep(.md-quote) {
  margin: 16px 0;
  padding: 12px 18px;
  background-color: var(--md-sys-color-surface-container);
  border-left: 3px solid var(--md-sys-color-outline);
  color: var(--md-sys-color-on-surface-variant);
  font-style: italic;
}

:deep(.md-code-block) {
  margin: 20px 0;
  background-color: #1e1e24;
  color: #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

:deep(.code-header) {
  padding: 8px 16px;
  background-color: #16161a;
  font-size: 12px;
  color: #94a3b8;
  text-transform: uppercase;
  font-family: monospace;
}

:deep(.md-code-block pre) {
  padding: 16px;
  overflow-x: auto;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
}

:deep(.md-inline-code) {
  font-family: monospace;
  font-size: 13px;
  background-color: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-primary);
  padding: 2px 6px;
  border-radius: 4px;
}

:deep(.md-img-wrap) {
  margin: 24px 0;
  text-align: center;
}

:deep(.md-img-wrap img) {
  max-width: 100%;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

:deep(.img-caption) {
  display: block;
  font-size: 12px;
  color: var(--md-sys-color-outline);
  margin-top: 6px;
}
</style>
