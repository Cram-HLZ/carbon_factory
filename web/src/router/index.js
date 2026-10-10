// router/index.js —— 路由 + 登录态 / 角色守卫
import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../layout/AppLayout.vue'),
    children: [
      { path: '', redirect: '/overview' },
      { path: 'overview', name: 'overview', component: () => import('../views/OverviewView.vue') },
      { path: 'heatmap', name: 'heatmap', component: () => import('../views/HeatmapView.vue') },
      { path: 'realtime', name: 'realtime', component: () => import('../views/RealtimeView.vue') },
      { path: 'alarms', name: 'alarms', component: () => import('../views/AlarmsView.vue') },
      { path: 'reports', name: 'reports', component: () => import('../views/ReportsView.vue') },
      { path: 'users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { adminOnly: true } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    // 已登录且令牌未过期访问登录页 → 直接进总览
    if (auth.isLogin && !auth.isTokenExpired) return { path: '/overview' }
    return true
  }
  // 未登录或令牌已过期 → 清会话并回登录页（避免进入受保护页后才因 401 被踢）
  if (!auth.isLogin || auth.isTokenExpired) {
    auth.clear()
    return { path: '/login' }
  }
  if (to.meta.adminOnly && !auth.isAdmin) return { path: '/overview' }
  return true
})

export default router