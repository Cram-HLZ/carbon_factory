// stores/auth.js —— 认证状态（Pinia）：token / 用户信息 / 角色权限
import { defineStore } from 'pinia'
import { login as apiLogin, register as apiRegister, logout as apiLogout } from '../api'

const TOKEN_KEY = 'cf_token'
const USER_KEY = 'cf_user'

function readUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null') }
  catch (e) { return null }
}

// 解析 JWT 负载（第二段 base64url），无法解析时返回 null
function readTokenPayload(token) {
  try {
    const seg = token.split('.')[1]
    if (!seg) return null
    const b64 = seg.replace(/-/g, '+').replace(/_/g, '/')
    const pad = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
    return JSON.parse(atob(pad))
  } catch (e) { return null }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: readUser(),
  }),
  getters: {
    isLogin: (s) => !!s.token,
    isTokenExpired: (s) => {
      if (!s.token) return true
      const p = readTokenPayload(s.token)
      if (!p || !p.exp) return true
      return p.exp * 1000 <= Date.now()
    },
    role: (s) => (s.user && s.user.role) || '',
    account: (s) => (s.user && s.user.account) || '',
    isAdmin: (s) => s.user && s.user.role === 'it_admin',
    hasPermission: (s) => (perm) => {
      const ps = (s.user && s.user.permissions) || []
      return ps.includes('*') || ps.includes(perm)
    },
  },
  actions: {
    setSession(token, user) {
      this.token = token
      this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    clear() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
    async login(account, password) {
      const data = await apiLogin(account, password)
      this.setSession(data.access_token, data.user)
    },
    async register(account, password) {
      const data = await apiRegister(account, password)
      this.setSession(data.access_token, data.user)
    },
    async logout() {
      try { await apiLogout() } catch (e) { /* 无状态令牌，忽略 */ }
      this.clear()
    },
  },
})