<template>
  <div>
    <nav class="navbar navbar-expand-lg navbar-dark" style="background:#0f766e">
      <div class="container-fluid">
        <router-link class="navbar-brand" to="/overview">🌿 数字孪生锂电工厂 · 碳排AI监测</router-link>
        <div class="navbar-nav">
          <router-link
            v-for="item in navItems"
            :key="item.to"
            class="nav-link"
            :class="{ active: route.path === item.to }"
            :to="item.to"
          >{{ item.label }}</router-link>
        </div>
        <div class="d-flex align-items-center gap-3 ms-auto">
          <span class="navbar-text small" :class="connection.cls">{{ connection.text }}</span>
          <span class="navbar-text small d-flex align-items-center gap-2">
            <span class="small">{{ auth.account }}（{{ roleName }}）</span>
            <button class="btn btn-sm btn-outline-light py-0" @click="onLogout">退出</button>
          </span>
        </div>
      </div>
    </nav>

    <main class="container-fluid py-4">
      <router-view />
    </main>

    <!-- 全局实时告警 Toast -->
    <div class="toast-stack">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="alert shadow-sm mb-2"
        :class="'alert-' + t.variant"
        style="font-size:13px"
      >
        <div class="d-flex justify-content-between align-items-start">
          <strong>{{ t.title }}</strong>
          <button type="button" class="btn-close btn-sm ms-2" @click="dismissToast(t.id)"></button>
        </div>
        <div v-for="(line, i) in t.lines" :key="i" class="small" :class="{ 'text-muted': i !== 1 }">{{ line }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ROLE_NAMES } from '../constants'
import { connection } from '../composables/connection'
import { toasts, dismissToast } from '../composables/toast'
import { useAlarmRealtime } from '../composables/alarmRealtime'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const { connect, disconnect } = useAlarmRealtime()

const roleName = computed(() => ROLE_NAMES[auth.role] || auth.role)

const navItems = computed(() => {
  const base = [
    { to: '/overview', label: '厂区总览' },
    { to: '/heatmap', label: '碳排热力图' },
    { to: '/realtime', label: '设备实时' },
    { to: '/alarms', label: '告警中心' },
    { to: '/reports', label: '报表中心' },
  ]
  if (auth.isAdmin) base.push({ to: '/users', label: '用户管理' })
  return base
})

function onLogout() {
  auth.logout().finally(() => router.push('/login'))
}

onMounted(connect)
onBeforeUnmount(() => {
  disconnect()
  toasts.value = []
})
</script>

<style scoped>
.toast-stack {
  position: fixed;
  top: 70px;
  right: 16px;
  z-index: 1080;
  width: 340px;
  max-width: 92vw;
}
</style>