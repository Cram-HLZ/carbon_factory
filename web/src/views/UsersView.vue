<template>
  <div>
    <div class="d-flex align-items-center justify-content-between mb-3">
      <h5 class="mb-0">用户与角色管理 <small class="text-secondary fs-6">（管理层 / 运维岗 / IT管理员）</small></h5>
      <span class="small text-secondary">仅 IT管理员可访问</span>
    </div>

    <div v-if="err" class="alert alert-danger py-2 small">⚠ {{ err }}</div>

    <!-- 新建用户 -->
    <div class="card mb-3" style="padding:16px 20px">
      <div class="row g-2 align-items-end">
        <div class="col-6 col-md-2"><label class="form-label small mb-1">账号</label><input v-model.trim="form.account" class="form-control form-control-sm" placeholder="如 zhangsan" /></div>
        <div class="col-6 col-md-2"><label class="form-label small mb-1">初始密码</label><input v-model="form.password" class="form-control form-control-sm" type="password" placeholder="≥6 位" /></div>
        <div class="col-6 col-md-2">
          <label class="form-label small mb-1">角色</label>
          <select v-model="form.role" class="form-select form-select-sm">
            <option v-for="r in roleOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
        </div>
        <div class="col-6 col-md-2"><button class="btn btn-sm btn-success" @click="createUser">新增用户</button></div>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="card" style="padding:16px 20px">
      <div class="d-flex gap-2 mb-3">
        <button class="btn btn-sm" :class="filter === 'all' ? 'btn-dark' : 'btn-outline-secondary'" @click="filter = 'all'">全部</button>
        <button class="btn btn-sm" :class="filter === 'pending' ? 'btn-warning' : 'btn-outline-secondary'" @click="filter = 'pending'">
          待审批 <span v-if="pendingCount" class="badge bg-danger">{{ pendingCount }}</span>
        </button>
        <button class="btn btn-sm" :class="filter === 'active' ? 'btn-success' : 'btn-outline-secondary'" @click="filter = 'active'">正常</button>
      </div>
      <table class="table align-middle mb-0">
        <thead><tr><th>ID</th><th>账号</th><th>状态</th><th>角色</th><th>权限</th><th style="width:280px">操作</th></tr></thead>
        <tbody>
          <tr v-for="u in filteredUsers" :key="u.id">
            <td>{{ u.id }}</td>
            <td>{{ u.account }}</td>
            <td><span class="badge" :class="statusClass(u.status)">{{ u.status_name || u.status }}</span></td>
            <td>{{ roleLabel(u.role) }}</td>
            <td class="small text-secondary">{{ (u.permissions || []).join(', ') || '—' }}</td>
            <td>
              <!-- 待审批账号：通过 / 驳回 -->
              <div v-if="u.status === 'pending'" class="d-flex gap-2">
                <button class="btn btn-sm btn-success" @click="approve(u)">通过</button>
                <button class="btn btn-sm btn-outline-danger" @click="reject(u)">驳回</button>
              </div>
              <div v-else class="d-flex gap-2 align-items-center">
                <select v-model="u.pendingRole" class="form-select form-select-sm">
                  <option v-for="r in roleOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
                </select>
                <button class="btn btn-sm btn-outline-primary text-nowrap" @click="updateRole(u)">改角色</button>
                <button class="btn btn-sm btn-outline-danger" @click="delUser(u)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredUsers.length" class="text-center text-secondary small py-3">暂无用户</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  getRoles,
  listUsers,
  createUser as apiCreateUser,
  updateUser as apiUpdateUser,
  deleteUser as apiDeleteUser,
  approveUser as apiApproveUser,
  rejectUser as apiRejectUser,
} from '../api'
import { ROLE_NAMES } from '../constants'

const err = ref('')
const users = ref([])
const roleOptions = ref([])
const filter = ref('all')
const form = reactive({ account: '', password: '', role: '' })

const pendingCount = computed(() => users.value.filter(u => u.status === 'pending').length)
const filteredUsers = computed(() => {
  if (filter.value === 'all') return users.value
  return users.value.filter(u => (u.status || 'active') === filter.value)
})

function statusClass(status) {
  if (status === 'pending') return 'bg-warning text-dark'
  if (status === 'disabled') return 'bg-secondary'
  return 'bg-success'
}

function roleLabel(role) {
  const opt = roleOptions.value.find(r => r.value === role)
  return (opt && opt.label) || ROLE_NAMES[role] || role
}

function errText(e) {
  const d = e && e.response && e.response.data
  if (d && d.detail) return d.detail
  return ''
}

async function loadRoles() {
  try {
    const json = await getRoles()
    const obj = json && (json.data || json)
    roleOptions.value = Object.keys(obj || {}).map(k => ({ value: k, label: (obj[k] && obj[k].name) || ROLE_NAMES[k] || k }))
    if (!form.role && roleOptions.value.length) form.role = roleOptions.value[0].value
  } catch (e) {
    err.value = errText(e) || '加载角色失败'
  }
}

async function loadUsers() {
  try {
    const json = await listUsers()
    const list = Array.isArray(json) ? json : (json && (json.items || json.data))
    users.value = (Array.isArray(list) ? list : []).map(u => ({ ...u, pendingRole: u.role }))
    err.value = ''
  } catch (e) {
    err.value = errText(e) || '加载用户失败'
  }
}

async function createUser() {
  if (!form.account || !form.password) { err.value = '请填写账号和密码'; return }
  try {
    await apiCreateUser({ account: form.account, password: form.password, role: form.role })
    form.account = ''
    form.password = ''
    err.value = ''
    loadUsers()
  } catch (e) {
    err.value = errText(e) || '创建失败'
  }
}

async function updateRole(u) {
  try {
    await apiUpdateUser(u.id, { role: u.pendingRole })
    err.value = ''
    loadUsers()
  } catch (e) {
    err.value = errText(e) || '更新失败'
  }
}

async function delUser(u) {
  if (!confirm('确认删除用户 ' + u.account + ' ？')) return
  try {
    await apiDeleteUser(u.id)
    err.value = ''
    loadUsers()
  } catch (e) {
    err.value = errText(e) || '删除失败'
  }
}

async function approve(u) {
  try {
    await apiApproveUser(u.id)
    err.value = ''
    loadUsers()
  } catch (e) {
    err.value = errText(e) || '审批失败'
  }
}

async function reject(u) {
  if (!confirm('驳回后该账号将被删除，确认驳回 ' + u.account + ' ？')) return
  try {
    await apiRejectUser(u.id)
    err.value = ''
    loadUsers()
  } catch (e) {
    err.value = errText(e) || '驳回失败'
  }
}

onMounted(() => {
  loadRoles()
  loadUsers()
})
</script>