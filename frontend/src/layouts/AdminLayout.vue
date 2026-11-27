<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  LayoutDashboard,
  Users,
  KeyRound,
  Download,
  BookOpen,
  Settings,
  ArrowLeft,
  LogOut,
  ShieldAlert,
  Sun,
  Moon,
  Blocks,
  Puzzle,
} from 'lucide-vue-next'
import { api } from '@/api'
import { getAdminPermissionRequests } from '@/api/mcp'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import LoginModal from '@/components/LoginModal.vue'
import OneLogo from '@/components/OneLogo.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const themeStore = useThemeStore()

const showLoginModal = ref(!authStore.isAdminLoggedIn)
const pendingMcpCount = ref(0)
const pendingPluginCount = ref(0)

const menuItems = [
  { label: '总览仪表盘', path: '/admin/dashboard', icon: LayoutDashboard },
  { label: '员工名单管理', path: '/admin/employees', icon: Users },
  { label: 'API Key 管理', path: '/admin/tokens', icon: KeyRound },
  { label: '资料与安装包', path: '/admin/files', icon: Download },
  { label: '案例文章管理', path: '/admin/articles', icon: BookOpen },
  { label: 'MCP 能力治理', path: '/admin/mcp-hub', icon: Blocks },
  { label: '插件市场治理', path: '/admin/plugins', icon: Puzzle },
  { label: '系统与网关配置', path: '/admin/settings', icon: Settings },
]

async function refreshPendingBadges() {
  if (!authStore.isAdminLoggedIn) {
    pendingMcpCount.value = 0
    pendingPluginCount.value = 0
    return
  }
  const [mcpReqs, pluginRes] = await Promise.all([
    getAdminPermissionRequests({ status: 'pending' }).catch(() => []),
    api.getAdminPlugins('pending').catch(() => ({ items: [] })),
  ])
  pendingMcpCount.value = Array.isArray(mcpReqs) ? mcpReqs.length : 0
  pendingPluginCount.value = Array.isArray(pluginRes.items) ? pluginRes.items.length : 0
}

function getMenuBadge(path: string): number {
  if (path === '/admin/mcp-hub') return pendingMcpCount.value
  if (path === '/admin/plugins') return pendingPluginCount.value
  return 0
}

function handleBadgesRefreshEvent() {
  void refreshPendingBadges()
}

watch(
  () => authStore.isAdminLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      void refreshPendingBadges()
    } else {
      pendingMcpCount.value = 0
      pendingPluginCount.value = 0
    }
  }
)

onMounted(() => {
  window.addEventListener('rgone:admin-badges-refresh', handleBadgesRefreshEvent)
  if (authStore.isAdminLoggedIn) {
    void refreshPendingBadges()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('rgone:admin-badges-refresh', handleBadgesRefreshEvent)
})

function handleLogout() {
  authStore.logoutAdmin()
  router.push('/')
}
</script>

<template>
  <div class="admin-shell-root">
    <!-- 侧边栏 -->
    <aside class="admin-sidebar">
      <div class="sidebar-top">
        <div class="admin-logo-box" @click="router.push('/')">
          <div class="admin-logo-badge">
            <OneLogo :size="20" />
          </div>
          <div class="admin-logo-text">
            <span class="a-title">One</span>
            <span class="a-sub">Console</span>
          </div>
        </div>

        <nav class="sidebar-menu">
          <button
            v-for="item in menuItems"
            :key="item.path"
            type="button"
            class="menu-item-btn md-state-layer"
            :class="{ active: route.path === item.path }"
            @click="router.push(item.path)"
          >
            <component :is="item.icon" :size="18" />
            <span class="menu-item-label">{{ item.label }}</span>
            <span v-if="getMenuBadge(item.path) > 0" class="menu-badge">
              {{ getMenuBadge(item.path) > 99 ? '99+' : getMenuBadge(item.path) }}
            </span>
          </button>
        </nav>
      </div>

      <div class="sidebar-bottom">
        <button type="button" class="back-portal-btn md-state-layer" @click="router.push('/')">
          <ArrowLeft :size="16" />
          <span>返回员工门户</span>
        </button>
      </div>
    </aside>

    <!-- 右侧主体内容 -->
    <div class="admin-main-wrap">
      <header class="admin-topbar">
        <div class="topbar-title">
          <span>One 运营管理控制台</span>
        </div>

        <div class="topbar-user">
          <button
            type="button"
            class="topbar-theme-btn md-state-layer"
            :title="themeStore.isDark ? '切换浅色' : '切换深色'"
            @click="themeStore.toggleTheme"
          >
            <Sun v-if="themeStore.isDark" :size="16" />
            <Moon v-else :size="16" />
          </button>
          <div class="admin-user-pill">
            <ShieldAlert :size="16" style="color: var(--md-sys-color-primary)" />
            <span>超级管理员：{{ authStore.adminUsername || 'admin' }}</span>
          </div>
          <button class="logout-btn md-state-layer" title="退出管理账号" @click="handleLogout">
            <LogOut :size="16" />
            <span>退出</span>
          </button>
        </div>
      </header>

      <div class="admin-content-body">
        <router-view v-if="authStore.isAdminLoggedIn" />
        <div v-else class="admin-login-required">
          <ShieldAlert :size="48" style="color: var(--md-sys-color-error)" />
          <h3>请先登录管理员账号</h3>
          <p>管理员会话已过期或尚未授权，请点击下方登录</p>
          <button class="relogin-btn md-state-layer" @click="showLoginModal = true">
            <span>登录管理员</span>
          </button>
        </div>
      </div>
    </div>

    <LoginModal v-model="showLoginModal" default-mode="admin" />
  </div>
</template>

<style scoped>
.admin-shell-root {
  display: flex;
  min-height: 100vh;
  background-color: var(--md-sys-color-surface);
}

.admin-sidebar {
  width: 240px;
  background-color: var(--md-sys-color-surface-container-lowest);
  border-right: 1px solid var(--md-sys-color-outline-variant);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 20px 14px;
}

.admin-logo-box {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  padding: 0 8px 24px;
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  margin-bottom: 20px;
}

.admin-logo-badge {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
}

:root[data-theme="dark"] .admin-logo-badge {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.admin-logo-text {
  display: flex;
  flex-direction: column;
}

.a-title {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--md-sys-color-on-surface);
  line-height: 1.15;
}

.a-sub {
  font-size: 11px;
  color: var(--md-sys-color-outline);
  letter-spacing: 0.02em;
}

.sidebar-menu {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.menu-item-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 14px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.menu-item-btn:hover {
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
}

.menu-item-btn.active {
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  font-weight: 600;
}

.menu-item-label {
  flex: 1;
}

.menu-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-error);
  color: var(--md-sys-color-on-error);
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
  flex-shrink: 0;
}

.sidebar-bottom {
  border-top: 1px solid var(--md-sys-color-outline-variant);
  padding-top: 14px;
}

.back-portal-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.admin-main-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: var(--md-sys-color-surface);
}

.admin-topbar {
  height: 60px;
  background-color: rgba(255, 255, 255, 0.88);
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

:root[data-theme="dark"] .admin-topbar {
  background-color: rgba(19, 19, 20, 0.88);
}

.topbar-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.topbar-user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.topbar-theme-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.topbar-theme-btn:hover {
  background-color: var(--md-sys-color-surface-container-highest);
  color: var(--md-sys-color-primary);
}

.admin-user-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--md-sys-color-primary-container);
  font-size: 13px;
  font-weight: 600;
  color: var(--md-sys-color-on-surface);
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border-radius: var(--md-sys-shape-corner-full);
  background-color: var(--sys-status-danger-bg, #FEE2E2);
  color: var(--sys-status-danger-text, #B91C1C);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.logout-btn:hover {
  opacity: 0.9;
}

.admin-content-body {
  flex: 1;
  padding: 24px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

.admin-login-required {
  padding: 80px 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.relogin-btn {
  padding: 10px 24px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 12px;
}

:root[data-theme="dark"] .relogin-btn {
  background-color: #FFFFFF;
  color: #1F1F1F;
}
</style>
