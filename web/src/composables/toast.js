// composables/toast.js —— 全局轻量 Toast（右上角，手动关闭，不自动消失）
import { ref } from 'vue'

export const toasts = ref([])
let _id = 0

export function pushToast({ variant = 'secondary', title = '', lines = [] }) {
  const id = ++_id
  toasts.value.push({ id, variant, title, lines })
}

export function dismissToast(id) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}