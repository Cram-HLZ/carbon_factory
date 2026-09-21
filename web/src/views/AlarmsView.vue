<template>
  <div>
    <div class="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
      <h5 class="mb-0">告警中心 <small class="text-secondary fs-6">（异常检测结果 · 历史查询 · 处理状态跟踪）</small></h5>
      <div class="d-flex gap-2">
        <button v-if="hasHandle" class="btn btn-sm btn-primary" @click="openCreate">+ 手动录入告警</button>
        <button class="btn btn-sm btn-success" @click="scanNow">立即扫描检测</button>
      </div>
    </div>

    <!-- 统计 -->
    <div class="row g-3 mb-3">
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">告警总数<b> <span>{{ items.length }}</span></b></div></div></div>
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">待处理<b> <span>{{ countBy('pending') }}</span></b></div></div></div>
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">处理中<b> <span>{{ countBy('processing') }}</span></b></div></div></div>
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">已解决<b> <span>{{ countBy('resolved') }}</span></b></div></div></div>
    </div>

    <!-- 过滤 -->
    <div class="card mb-3" style="padding:14px 18px">
      <div class="row g-2 align-items-end">
        <div class="col-6 col-md-2">
          <label class="form-label small mb-1">严重度</label>
          <select v-model="filters.severity" class="form-select form-select-sm" @change="load">
            <option value="">全部</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option>
          </select>
        </div>
        <div class="col-6 col-md-2">
          <label class="form-label small mb-1">处理状态</label>
          <select v-model="filters.status" class="form-select form-select-sm" @change="load">
            <option value="">全部</option><option value="pending">待处理</option><option value="processing">处理中</option><option value="resolved">已解决</option>
          </select>
        </div>
        <div class="col-6 col-md-3">
          <label class="form-label small mb-1">设备编号</label>
          <input v-model.trim="filters.equipmentId" class="form-control form-control-sm" placeholder="如 I-9-01" @keydown.enter="load" />
        </div>
        <div class="col-6 col-md-2"><button class="btn btn-sm btn-outline-success w-100" @click="load">查询</button></div>
        <div class="col-6 col-md-2"><button class="btn btn-sm btn-outline-secondary w-100" @click="resetFilter">重置</button></div>
      </div>
    </div>

    <div v-if="alertMsg" class="alert mb-3" :class="'alert-' + alertType">⚠ {{ alertMsg }}</div>

    <!-- 列表 -->
    <div class="card" style="padding:16px 20px">
      <div v-if="canDelete" class="d-flex align-items-center justify-content-between mb-2">
        <button class="btn btn-sm btn-outline-danger" @click="batchDelete">批量删除选中</button>
        <span class="small text-secondary">{{ selectedCount ? `已选 ${selectedCount} 条` : '未选中任何记录' }}</span>
      </div>
      <table class="table align-middle mb-0">
        <thead>
          <tr>
            <th v-if="canDelete" style="width:36px"><input type="checkbox" class="form-check-input" :checked="allChecked" @change="toggleAll" /></th>
            <th>ID</th><th>告警时间</th><th>设备</th><th>严重度</th><th>根因</th><th>处理状态</th><th style="width:250px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in items" :key="a.id">
            <td v-if="canDelete"><input type="checkbox" class="form-check-input" v-model="a.checked" /></td>
            <td>{{ a.id }}</td>
            <td class="small">{{ a.alarm_time || '—' }}</td>
            <td>{{ a.equipment_name || a.equipment_id }}<div class="small text-secondary">{{ a.equipment_id }}</div></td>
            <td><span class="badge" :class="'bg-' + (SEVERITY_COLOR[a.severity] || 'secondary')">{{ SEVERITY_LABEL[a.severity] || a.severity }}</span></td>
            <td class="small">{{ a.root_cause || '—' }}</td>
            <td><span class="badge" :class="STATUS_BADGE[a.status] || 'bg-secondary'">{{ STATUS_LABEL[a.status] || a.status }}</span></td>
            <td>
              <div class="d-flex gap-1 flex-wrap">
                <template v-if="hasHandle">
                  <button class="btn btn-sm btn-outline-primary" @click="openEdit(a.id)">编辑</button>
                  <button v-if="a.status === 'pending'" class="btn btn-sm btn-outline-warning" @click="setStatus(a.id, 'processing')">开始处理</button>
                  <button v-if="a.status === 'pending'" class="btn btn-sm btn-outline-success" @click="setStatus(a.id, 'resolved')">已解决</button>
                  <button v-if="a.status === 'processing'" class="btn btn-sm btn-outline-success" @click="setStatus(a.id, 'resolved')">已解决</button>
                  <button v-if="a.status === 'processing'" class="btn btn-sm btn-outline-secondary" @click="setStatus(a.id, 'pending')">退回</button>
                  <button v-if="a.status === 'resolved'" class="btn btn-sm btn-outline-secondary" @click="setStatus(a.id, 'pending')">重新打开</button>
                </template>
                <button v-if="canDelete" class="btn btn-sm btn-outline-danger" @click="delAlarm(a.id)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!items.length" class="text-center text-secondary small py-3">暂无告警记录</div>
    </div>

    <!-- 新增 / 编辑弹窗 -->
    <div v-if="modalOpen" class="modal-backdrop-custom" @click.self="modalOpen = false">
      <div class="card modal-card">
        <div class="d-flex justify-content-between align-items-center p-3 border-bottom">
          <h6 class="mb-0">{{ isEdit ? '编辑告警 #' + form.id : '手动录入告警' }}</h6>
          <button type="button" class="btn-close" @click="modalOpen = false"></button>
        </div>
        <div class="p-3">
          <div class="mb-3">
            <label class="form-label small">设备编号</label>
            <select v-model="form.equipment_id" class="form-select form-select-sm">
              <option v-for="e in equipList" :key="e.equipment_id" :value="e.equipment_id">{{ e.equipment_name || e.equipment_id }}（{{ e.equipment_id }}）</option>
            </select>
          </div>
          <div class="mb-3">
            <label class="form-label small">严重度</label>
            <select v-model="form.severity" class="form-select form-select-sm">
              <option value="high">高</option><option value="medium">中</option><option value="low">低</option>
            </select>
          </div>
          <div class="mb-3">
            <label class="form-label small">告警根因</label>
            <textarea v-model="form.root_cause" class="form-control form-control-sm" rows="2" placeholder="可选，描述告警原因"></textarea>
          </div>
          <div class="mb-3">
            <label class="form-label small">告警时间（留空用当前时间）</label>
            <input v-model="form.alarm_time" type="datetime-local" class="form-control form-control-sm" />
          </div>
        </div>
        <div class="d-flex justify-content-end gap-2 p-3 border-top">
          <button class="btn btn-sm btn-outline-secondary" @click="modalOpen = false">取消</button>
          <button class="btn btn-sm btn-primary" @click="submit">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  listAlarms, createAlarm, updateAlarm, updateAlarmStatus, deleteAlarm,
  batchDeleteAlarms, scanAlarms, getEquipmentList,
} from '../api'
import { SEVERITY_COLOR, SEVERITY_LABEL, STATUS_LABEL, STATUS_BADGE } from '../constants'
import { useAuthStore } from '../stores/auth'
import { useAlarmRealtime } from '../composables/alarmRealtime'

const auth = useAuthStore()
const hasHandle = auth.hasPermission('handle:alarm')
const canDelete = auth.isAdmin

const { setSubscriber } = useAlarmRealtime()

const items = ref([])
const filters = reactive({ severity: '', status: '', equipmentId: '' })
const alertMsg = ref('')
const alertType = ref('danger')

const equipList = ref([])
const modalOpen = ref(false)
const isEdit = ref(false)
const form = reactive({ id: null, equipment_id: '', severity: 'medium', root_cause: '', alarm_time: '' })

const selectedIds = computed(() => items.value.filter(a => a.checked).map(a => a.id))
const selectedCount = computed(() => selectedIds.value.length)
const allChecked = computed(() => items.value.length > 0 && items.value.every(a => a.checked))

function countBy(s) { return items.value.filter(a => a.status === s).length }

function showErr(m) { alertMsg.value = m; alertType.value = 'danger' }
function showInfo(m) { alertMsg.value = m; alertType.value = 'info' }
function clearErr() { alertMsg.value = '' }

function toggleAll(e) {
  const c = e.target.checked
  items.value.forEach(a => { a.checked = c })
}

function toLocalInput(s) {
  if (!s) return ''
  return s.indexOf('T') >= 0 ? s.slice(0, 16) : s.replace(' ', 'T').slice(0, 16)
}

async function load() {
  clearErr()
  const params = { limit: 200 }
  if (filters.severity) params.severity = filters.severity
  if (filters.status) params.status = filters.status
  if (filters.equipmentId) params.equipment_id = filters.equipmentId
  try {
    const json = await listAlarms(params)
    items.value = (json.items || []).map(a => ({ ...a, checked: false }))
  } catch (e) {
    if (e.response && e.response.status === 401) return
    const d = e.response && e.response.data
    showErr(d && d.detail ? d.detail : ('加载失败：' + e.message))
  }
}

async function setStatus(id, status) {
  try {
    await updateAlarmStatus(id, status)
    load()
  } catch (e) {
    showErr(errText(e) || '更新失败')
  }
}

function openCreate() {
  isEdit.value = false
  form.id = null
  form.severity = 'medium'
  form.root_cause = ''
  form.alarm_time = ''
  form.equipment_id = equipList.value.length ? equipList.value[0].equipment_id : ''
  modalOpen.value = true
}

function openEdit(id) {
  const a = items.value.find(x => x.id === id)
  if (!a) return
  isEdit.value = true
  form.id = id
  form.equipment_id = a.equipment_id
  form.severity = a.severity
  form.root_cause = a.root_cause || ''
  form.alarm_time = toLocalInput(a.alarm_time)
  modalOpen.value = true
}

async function submit() {
  if (!form.equipment_id) { showErr('请选择设备编号'); return }
  const body = { equipment_id: form.equipment_id, severity: form.severity, root_cause: form.root_cause }
  if (form.alarm_time) body.alarm_time = form.alarm_time
  try {
    if (isEdit.value) await updateAlarm(form.id, body)
    else await createAlarm(body)
    modalOpen.value = false
    clearErr()
    load()
  } catch (e) {
    showErr(errText(e) || '保存失败')
  }
}

async function delAlarm(id) {
  if (!confirm('确定删除告警 #' + id + ' 吗？此操作不可恢复。')) return
  try {
    await deleteAlarm(id)
    clearErr()
    load()
  } catch (e) {
    showErr(errText(e) || '删除失败')
  }
}

async function batchDelete() {
  if (!selectedIds.value.length) { showErr('请先勾选要删除的告警'); return }
  if (!confirm(`确定批量删除选中的 ${selectedIds.value.length} 条告警吗？此操作不可恢复。`)) return
  try {
    await batchDeleteAlarms(selectedIds.value)
    clearErr()
    load()
  } catch (e) {
    showErr(errText(e) || '批量删除失败')
  }
}

async function scanNow() {
  clearErr()
  try {
    const json = await scanAlarms()
    const n = json.triggered != null ? json.triggered : (json.alerts || []).length
    showInfo(`本轮扫描 ${json.scanned} 台设备，触发 ${n} 条告警`)
    load()
  } catch (e) {
    showErr(errText(e) || '扫描失败')
  }
}

function resetFilter() {
  filters.severity = ''
  filters.status = ''
  filters.equipmentId = ''
  load()
}

function errText(e) {
  const d = e && e.response && e.response.data
  return (d && d.detail) || ''
}

async function loadEquipmentList() {
  try {
    const json = await getEquipmentList()
    equipList.value = (json.data && json.data.items) || []
  } catch (e) { /* 下拉加载失败不影响其它功能 */ }
}

onMounted(() => {
  loadEquipmentList()
  load()
  setSubscriber(() => load())
})

onBeforeUnmount(() => {
  setSubscriber(null)
})
</script>

<style scoped>
.stat { font-size: 13px; color: #6b7280; }
.stat b { color: #0f766e; font-size: 20px; font-weight: 600; }
.modal-backdrop-custom {
  position: fixed; inset: 0; z-index: 1050;
  background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center;
}
.modal-card { width: 100%; max-width: 520px; }
</style>