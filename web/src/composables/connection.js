// composables/connection.js —— 页面 → 导航栏「连接状态」徽标的轻量共享状态
import { ref } from 'vue'

export const connection = ref({ text: '后端: 8001', cls: 'text-secondary' })

// categories: 'secondary' | 'success' | 'danger'
export function setConnection(text, cls = 'text-success') {
  connection.value = { text, cls }
}