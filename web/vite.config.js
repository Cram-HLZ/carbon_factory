import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 碳排AI监测系统 - 前端（Vue3 SPA）
// 开发服务器端口沿用原静态站点 8002，后端 8001 / 算法 8000 保持不变
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 8002,
  },
  preview: {
    host: '0.0.0.0',
    port: 8002,
  },
})