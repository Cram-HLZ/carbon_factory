<template>
  <div>
    <div class="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
      <h5 class="mb-0">设备实时监测</h5>
      <div class="d-flex align-items-center gap-2">
        <select v-model="equipId" class="form-select form-select-sm" style="min-width:220px" @change="load">
          <option v-for="e in equipList" :key="e.equipment_id" :value="e.equipment_id">
            {{ e.equipment_name || e.equipment_id }}（{{ e.equipment_id }}）
          </option>
        </select>
        <div class="form-check form-switch mb-0">
          <input v-model="autoRefresh" class="form-check-input" type="checkbox" id="autoRefresh" />
          <label class="form-check-label small" for="autoRefresh">自动刷新(10s)</label>
        </div>
        <button class="btn btn-sm btn-success" @click="load">立即刷新</button>
      </div>
    </div>

    <div v-if="alertMsg" class="alert mb-3" :class="alertType ? 'alert-' + alertType : 'alert-warning'">⚠ {{ alertMsg }}</div>

    <div class="card mb-3" style="padding:14px 20px">
      <div class="d-flex flex-wrap align-items-center gap-3">
        <div>
          <span class="fs-5 fw-bold">{{ info.name }}</span>
          <span class="badge bg-secondary ms-2">{{ info.id }}</span>
        </div>
        <span class="text-secondary small">{{ info.type }}</span>
        <span class="text-secondary small">{{ info.workshop }}</span>
        <span class="text-secondary small">{{ info.time }}</span>
        <span class="ms-auto badge" :class="info.statusCls">{{ info.statusText }}</span>
      </div>
    </div>

    <div class="row g-3">
      <div class="col-md-4">
        <div class="card">
          <div class="card-title">负载率</div>
          <div ref="gaugeEl" style="height:280px"></div>
        </div>
      </div>
      <div class="col-md-8">
        <div class="row g-3 h-100">
          <div class="col-6"><div class="card metric"><div class="label">实时功率</div><div class="value">{{ mPower }}</div><div class="unit">kW</div></div></div>
          <div class="col-6"><div class="card metric"><div class="label">瞬时碳排</div><div class="value">{{ mCarbon }}</div><div class="unit">kgCO₂</div></div></div>
          <div class="col-6"><div class="card metric"><div class="label">设备温度</div><div class="value">{{ mTemp }}</div><div class="unit">℃</div></div></div>
          <div class="col-6"><div class="card metric"><div class="label">采样时间</div><div class="value" style="font-size:18px">{{ mTime }}</div><div class="unit">实时数据</div></div></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { getEquipmentList, getRealtime } from '../api'
import { TYPE_NAMES, WORKSHOPS, RUN_STATUS, RUN_STATUS_CLS, fmt } from '../constants'
import { setConnection } from '../composables/connection'
import { useEcharts } from '../composables/useEcharts'

const gaugeEl = ref(null)
const { setOption: setGauge } = useEcharts(gaugeEl)

const equipList = ref([])
const equipId = ref('')
const autoRefresh = ref(true)
const alertMsg = ref('')
const alertType = ref('')

const info = reactive({ name: '—', id: '—', type: '—', workshop: '—', time: '—', statusText: '—', statusCls: 'bg-secondary' })
const mPower = ref('—')
const mCarbon = ref('—')
const mTemp = ref('—')
const mTime = ref('—')

let timer = null

function showError(m) { alertMsg.value = m; alertType.value = 'danger' }
function showTip(m) { alertMsg.value = m; alertType.value = 'warning' }

function render(d) {
  info.name = d.equipment_name || d.equipment_id || '—'
  info.id = d.equipment_id || '—'
  info.type = '类型：' + (TYPE_NAMES[d.equipment_type] || d.equipment_type || '—')
  info.workshop = '车间：' + (WORKSHOPS[d.workshop_id] || d.workshop_id || '—')
  info.time = '数据时间：' + (d.timestamp || '—')

  const s = d.status
  info.statusText = RUN_STATUS[s] != null ? RUN_STATUS[s] : '未知'
  info.statusCls = RUN_STATUS_CLS[s] || 'bg-secondary'

  mPower.value = fmt(d.power)
  mCarbon.value = fmt(d.carbon_emission)
  mTemp.value = fmt(d.temperature)
  mTime.value = (d.timestamp || '').replace('T', ' ')

  const rate = (d.load_rate || 0) * 100
  setGauge({
    series: [{
      type: 'gauge', min: 0, max: 120, splitNumber: 6,
      progress: { show: true, width: 18, itemStyle: { color: '#10b981' } },
      axisLine: { lineStyle: { width: 18 } },
      axisLabel: { formatter: '{value}%' },
      pointer: { width: 4 },
      detail: { formatter: '{value}%', fontSize: 26, fontWeight: 700, offsetCenter: [0, '70%'] },
      data: [{ value: +rate.toFixed(1), name: '负载率' }],
    }],
  })
}

async function load() {
  if (!equipId.value) return
  alertMsg.value = ''
  try {
    const json = await getRealtime(equipId.value)
    if (json.code === 503) { showError('算法服务未启动：' + (json.message || '')); return }
    if (json.code !== 200 && json.code != null) { showError(json.message || ('code=' + json.code)); return }
    const d = json.data || {}
    render(d)
    if (d.message) showTip('提示：' + d.message)
    setConnection('已连接 · 实时', 'text-success')
  } catch (e) {
    showError('无法连接后端 8001：' + e.message)
    setConnection('后端未连接', 'text-danger')
  }
}

async function loadEquipmentList() {
  try {
    const json = await getEquipmentList()
    if (json.code !== 200) throw new Error(json.message)
    equipList.value = (json.data && json.data.items) || []
    if (equipList.value.some(e => e.equipment_id === 'I-9-01')) equipId.value = 'I-9-01'
    else if (equipList.value.length) equipId.value = equipList.value[0].equipment_id
    load()
  } catch (e) {
    showError('获取设备列表失败：' + e.message)
  }
}

onMounted(() => {
  loadEquipmentList()
  timer = setInterval(() => { if (autoRefresh.value) load() }, 10000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>