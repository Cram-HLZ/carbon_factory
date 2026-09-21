<template>
  <div>
    <div class="d-flex align-items-end justify-content-between mb-3 flex-wrap gap-2">
      <h5 class="mb-0">碳排热力图 <small class="text-secondary fs-6">（车间 × 设备 · 颜色越深碳排越高）</small></h5>
      <div class="d-flex align-items-center gap-2">
        <input v-model="startTime" type="datetime-local" class="form-control form-control-sm" />
        <span class="text-secondary small">至</span>
        <input v-model="endTime" type="datetime-local" class="form-control form-control-sm" />
        <button class="btn btn-sm btn-success" @click="load">查询</button>
        <button class="btn btn-sm btn-outline-secondary" @click="useSample">示例时间窗口</button>
      </div>
    </div>

    <div v-if="alertMsg" class="alert mb-3" :class="alertType ? 'alert-' + alertType : 'alert-warning'">⚠ {{ alertMsg }}</div>

    <div class="row g-3 mb-3">
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">设备数<b> <span>{{ statCount }}</span></b></div></div></div>
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">总碳排 (kgCO₂)<b> <span>{{ statTotal }}</span></b></div></div></div>
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">最大碳排设备<b> <span>{{ statMax }}</span></b></div></div></div>
      <div class="col-6 col-lg-3"><div class="card" style="padding:14px 18px"><div class="stat">平均功率 (kW)<b> <span>{{ statPower }}</span></b></div></div></div>
    </div>

    <div class="card" style="padding:0"><div ref="heatmapEl" style="height:660px"></div></div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getHeatmap } from '../api'
import { WORKSHOPS, fmt } from '../constants'
import { setConnection } from '../composables/connection'
import { useEcharts } from '../composables/useEcharts'

const heatmapEl = ref(null)
const { setOption } = useEcharts(heatmapEl)

const startTime = ref('')
const endTime = ref('')
const alertMsg = ref('')
const alertType = ref('')
const statCount = ref('—')
const statTotal = ref('—')
const statMax = ref('—')
const statPower = ref('—')

function toLocalInput(d) {
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

function defaultRange() {
  const end = new Date()
  const start = new Date(end.getTime() - 7 * 24 * 3600 * 1000)
  return { start: toLocalInput(start), end: toLocalInput(end) }
}

function useSample() {
  const r = defaultRange()
  startTime.value = r.start
  endTime.value = r.end
  load()
}

function padLocal(v) {
  return v && v.length === 16 ? v + ':00' : v
}

function showError(m) { alertMsg.value = m; alertType.value = 'danger' }
function showEmpty(m) { alertMsg.value = m; alertType.value = 'warning' }

function render(records, count) {
  const total = records.reduce((s, r) => s + (r.carbon_emission || 0), 0)
  const maxR = records.slice().sort((a, b) => b.carbon_emission - a.carbon_emission)[0]
  const powerMean = records.reduce((s, r) => s + (r.power_mean || 0), 0) / (records.length || 1)
  statCount.value = count != null ? count : records.length
  statTotal.value = total.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
  statMax.value = maxR ? (maxR.equipment_name || maxR.equipment_id) : '—'
  statPower.value = powerMean.toFixed(2)

  const wsOrder = Object.keys(WORKSHOPS)
  const sorted = records.slice().sort((a, b) => {
    const w = wsOrder.indexOf(a.workshop_id) - wsOrder.indexOf(b.workshop_id)
    return w !== 0 ? w : (a.equipment_id < b.equipment_id ? -1 : 1)
  })
  const xCats = wsOrder.map(w => WORKSHOPS[w])
  const yCats = sorted.map(r => `${r.equipment_name || r.equipment_id}\n(${r.equipment_id})`)
  const data = sorted.map((r, yi) => [wsOrder.indexOf(r.workshop_id), yi, r.carbon_emission])
  const maxVal = Math.max(1, ...records.map(r => r.carbon_emission || 0))

  setOption({
    tooltip: {
      position: 'top',
      formatter: p => {
        const r = sorted[p.value[1]]
        return `<b>${r.equipment_name || r.equipment_id}</b>（${r.equipment_id}）<br/>`
          + `车间：${WORKSHOPS[r.workshop_id] || r.workshop_id}<br/>`
          + `碳排：${(r.carbon_emission).toLocaleString('zh-CN')} kgCO₂<br/>`
          + `平均功率：${r.power_mean} kW · 运行时数：${r.runtime}`
      },
    },
    grid: { left: 10, right: 10, top: 10, bottom: 60, containLabel: true },
    xAxis: { type: 'category', data: xCats, splitArea: { show: true }, axisLabel: { interval: 0 } },
    yAxis: { type: 'category', data: yCats, splitArea: { show: true }, axisLabel: { fontSize: 10, lineHeight: 12 } },
    visualMap: {
      min: 0, max: maxVal, calculable: true, orient: 'horizontal',
      left: 'center', bottom: 0, text: ['高碳排', '低碳排'],
      inRange: { color: ['#e0f2fe', '#10b981', '#0f766e', '#7c3aed'] },
    },
    series: [{
      type: 'heatmap', data,
      label: { show: false },
      itemStyle: { borderColor: '#fff', borderWidth: 1 },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,.4)' } },
    }],
  })
}

async function load() {
  alertMsg.value = ''
  const start = padLocal(startTime.value)
  const end = padLocal(endTime.value)
  if (!start || !end) { showError('请选择起始/结束时间'); return }
  try {
    const json = await getHeatmap(start, end)
    if (json.code !== 200) { showError(json.message || ('code=' + json.code)); return }
    const d = json.data || {}
    const records = d.records || []
    if (records.length === 0) { showEmpty('该时间范围内暂无数据：' + (d.message || '请确认 raw_data 目录或调整时间范围')); return }
    render(records, d.count)
    setConnection(`已连接 · ${records.length} 台设备`, 'text-success')
  } catch (e) {
    showError('无法连接后端 8001：' + e.message)
    setConnection('后端未连接', 'text-danger')
  }
}

onMounted(() => {
  const r = defaultRange()
  startTime.value = r.start
  endTime.value = r.end
  load()
})
</script>

<style scoped>
.stat { font-size: 13px; color: #6b7280; }
.stat b { color: #0f766e; font-size: 18px; font-weight: 600; }
</style>