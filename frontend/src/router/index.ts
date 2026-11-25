import { createRouter, createWebHistory } from 'vue-router'
import PortalLayout from '@/layouts/PortalLayout.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 员工门户体系 (Portal Track)
    {
      path: '/',
      component: PortalLayout,
      children: [
        {
          path: '',
          name: 'home-guide',
          component: () => import('@/views/portal/HomeGuideView.vue'),
        },
        {
          path: 'workspace',
          name: 'workspace',
          component: () => import('@/views/portal/WorkspaceView.vue'),
        },
        {
          path: 'downloads',
          name: 'downloads',
          component: () => import('@/views/portal/DownloadsView.vue'),
        },
        {
          path: 'articles',
          name: 'articles',
          component: () => import('@/views/portal/ArticlesView.vue'),
        },
      ],
    },
    // 后台管理体系 (Admin Track)
    {
      path: '/admin',
      component: AdminLayout,
      children: [
        {
          path: '',
          redirect: '/admin/dashboard',
        },
        {
          path: 'dashboard',
          name: 'admin-dashboard',
          component: () => import('@/views/admin/AdminDashboardView.vue'),
        },
        {
          path: 'employees',
          name: 'admin-employees',
          component: () => import('@/views/admin/AdminEmployeesView.vue'),
        },
        {
          path: 'tokens',
          name: 'admin-tokens',
          component: () => import('@/views/admin/AdminTokensView.vue'),
        },
        {
          path: 'files',
          name: 'admin-files',
          component: () => import('@/views/admin/AdminFilesView.vue'),
        },
        {
          path: 'articles',
          name: 'admin-articles',
          component: () => import('@/views/admin/AdminArticlesView.vue'),
        },
        {
          path: 'settings',
          name: 'admin-settings',
          component: () => import('@/views/admin/AdminSettingsView.vue'),
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

// Web 安全防范：协议合法性校验，拦截恶意伪协议重定向
router.beforeEach((to, _from, next) => {
  if (to.query.redirect) {
    const redirectUrl = String(to.query.redirect)
    if (/^\s*(javascript|data|vbscript):/i.test(redirectUrl)) {
      next({ path: '/' })
      return
    }
  }
  next()
})

export default router
