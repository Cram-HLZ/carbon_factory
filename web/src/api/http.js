// http.js —— axios 实例：统一注入 JWT 令牌 + 401 自动登出跳转
import axios from 'axios'
import { API_BASE } from '../constants'

const http = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
})

// 请求拦截：给所有 /api 请求注入 Authorization: Bearer <token>
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('cf_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：token 失效（401）时清空会话并回登录页（登录页自身的 401 由页面提示）
http.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response && err.response.status === 401) {
      const hash = window.location.hash
      const isLoginPage = hash.includes('/login')
      if (!isLoginPage) {
        localStorage.removeItem('cf_token')
        localStorage.removeItem('cf_user')
        window.location.hash = '#/login'
      }
    }
    return Promise.reject(err)
  },
)

export default http