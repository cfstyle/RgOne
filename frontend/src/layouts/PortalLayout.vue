<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Sun,
  Moon,
  UserCheck,
  ShieldAlert,
  LogOut,
  Download,
  BookOpen,
  LayoutDashboard,
  Compass,
} from 'lucide-vue-next'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import LoginModal from '@/components/LoginModal.vue'
import OneLogo from '@/components/OneLogo.vue'

const route = useRoute()
const router = useRouter()
const themeStore = useThemeStore()
const authStore = useAuthStore()

const showLoginModal = ref(false)
const loginDefaultMode = ref<'employee' | 'admin'>('employee')

const navItems = [
  { label: '快速上手', path: '/', icon: Compass },
  { label: '我的工作台', path: '/workspace', icon: LayoutDashboard },
  { label: '下载中心', path: '/downloads', icon: Download },
  { label: '案例广场', path: '/articles', icon: BookOpen },
]

function handleNavClick(path: string) {
  router.push(path)
}

function openLogin(mode: 'employee' | 'admin' = 'employee') {
  loginDefaultMode.value = mode
  showLoginModal.value = true
}
</script>

<template>
  <div class="portal-root">
    <!-- 顶部统一导航栏 -->
    <header class="portal-header">
      <div class="header-inner">
        <!-- Logo 与系统名称 -->
        <div class="brand-box" @click="router.push('/')">
          <div class="brand-logo">
            <OneLogo :size="20" />
          </div>
          <div class="brand-text">
            <span class="brand-title">One</span>
            <span class="brand-sub">All-in-One AI Platform</span>
          </div>
        </div>

        <!-- 导航菜单 -->
        <nav class="nav-links">
          <button
            v-for="item in navItems"
            :key="item.path"
            type="button"
            class="nav-tab md-state-layer"
            :class="{ active: route.path === item.path }"
            @click="handleNavClick(item.path)"
          >
            <component :is="item.icon" :size="16" />
            <span>{{ item.label }}</span>
          </button>
        </nav>

        <!-- 右侧操作栏 -->
        <div class="header-actions">
          <!-- 深浅色切换 -->
          <button
            type="button"
            class="icon-action-btn md-state-layer"
            :title="themeStore.isDark ? '切换浅色' : '切换深色'"
            @click="themeStore.toggleTheme"
          >
            <Sun v-if="themeStore.isDark" :size="18" />
            <Moon v-else :size="18" />
          </button>

          <!-- 会话与登录状态 -->
          <template v-if="authStore.isEmployeeLoggedIn">
            <div class="emp-badge">
              <UserCheck :size="16" style="color: var(--md-sys-color-primary)" />
              <span class="emp-name">{{ authStore.empName }} ({{ authStore.empNo }})</span>
              <button
                type="button"
                class="logout-icon-btn"
                title="退出当前工号"
                @click="authStore.logoutEmployee"
              >
                <LogOut :size="14" />
              </button>
            </div>
            <button
              v-if="authStore.isAdminLoggedIn"
              type="button"
              class="admin-entry-btn md-state-layer"
              @click="router.push('/admin/dashboard')"
            >
              <ShieldAlert :size="15" />
              <span>管理后台</span>
            </button>
          </template>
          <template v-else-if="authStore.isAdminLoggedIn">
            <div class="emp-badge">
              <ShieldAlert :size="16" style="color: #1F1F1F" />
              <span class="emp-name">管理员 ({{ authStore.adminUsername }})</span>
              <button
                type="button"
                class="logout-icon-btn"
                title="退出管理员"
                @click="authStore.logoutAdmin"
              >
                <LogOut :size="14" />
              </button>
            </div>
            <button
              type="button"
              class="admin-entry-btn md-state-layer"
              @click="router.push('/admin/dashboard')"
            >
              <ShieldAlert :size="15" />
              <span>管理后台</span>
            </button>
          </template>
          <template v-else>
            <!-- 统一合并登录按钮 -->
            <button
              type="button"
              class="verify-btn md-state-layer"
              @click="openLogin('employee')"
            >
              <UserCheck :size="16" />
              <span>登录</span>
            </button>
          </template>
        </div>
      </div>
    </header>

    <!-- 核心视图插槽 -->
    <main class="portal-main">
      <router-view />
    </main>

    <!-- 底部简要版权 -->
    <footer class="portal-footer">
      <p>行内大模型算力网关 (new-api) & DeepSeek Harness 接入支撑平台 · 纯内网离线专线提供</p>
    </footer>

    <!-- 全局统一登录弹窗 -->
    <LoginModal
      v-model="showLoginModal"
      :default-mode="loginDefaultMode"
    />
  </div>
</template>

<style scoped>
.portal-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--md-sys-color-surface);
}

.portal-header {
  position: sticky;
  top: 0;
  z-index: 100;
  height: 64px;
  background-color: rgba(255, 255, 255, 0.88);
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  backdrop-filter: blur(12px);
}

:root[data-theme="dark"] .portal-header {
  background-color: rgba(19, 19, 20, 0.88);
}

.header-inner {
  max-width: 1400px;
  height: 100%;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-box {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  user-select: none;
}

.brand-logo {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
}

:root[data-theme="dark"] .brand-logo {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--md-sys-color-on-surface);
  line-height: 1.15;
}

.brand-sub {
  font-size: 11px;
  color: var(--md-sys-color-outline);
  letter-spacing: 0.02em;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 14px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
  transition: all 0.2s;
  cursor: pointer;
}

.nav-tab:hover {
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
}

.nav-tab.active {
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.icon-action-btn {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--md-sys-color-on-surface-variant);
  background-color: var(--md-sys-color-primary-container);
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
}

.icon-action-btn:hover {
  color: var(--md-sys-color-on-surface);
}

.emp-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 600;
}

.logout-icon-btn {
  display: flex;
  align-items: center;
  color: var(--md-sys-color-outline);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  transition: color 0.2s;
}

.logout-icon-btn:hover {
  color: #B91C1C;
}

.verify-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background-color: #1F1F1F;
  color: #FFFFFF;
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.verify-btn:hover {
  opacity: 0.9;
}

:root[data-theme="dark"] .verify-btn {
  background-color: #FFFFFF;
  color: #1F1F1F;
}

.admin-entry-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background-color: var(--md-sys-color-primary-container);
  color: var(--md-sys-color-on-surface);
  border-radius: var(--md-sys-shape-corner-full);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.admin-entry-btn:hover {
  background-color: var(--md-sys-color-surface-container-high);
}

.portal-main {
  flex: 1;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  padding: 24px;
}

.portal-footer {
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--md-sys-color-outline);
  border-top: 1px solid var(--md-sys-color-outline-variant);
  background-color: var(--md-sys-color-surface-container-lowest);
}

@media (max-width: 900px) {
  .brand-sub {
    display: none;
  }
  .nav-tab span {
    display: none;
  }
}
</style>
