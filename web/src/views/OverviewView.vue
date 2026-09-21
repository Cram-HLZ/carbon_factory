<template>
  <div>
    <div class="d-flex align-items-center justify-content-between mb-3">
      <h5 class="mb-0">厂区碳排总览</h5>
      <button class="btn btn-sm btn-outline-success" @click="load">刷新数据</button>
    </div>

    <div v-if="alertMsg" class="alert mb-3" :class="alertType ? 'alert-' + alertType : 'alert-warning'">⚠ {{ alertMsg }}</div>

    <!-- KPI -->
    <div class="row g-3 mb-3">
      <div class="col-6 col-lg-3"><div class="card kpi"><div class="label">总碳排 (kgCO₂)</div><div class="value">{{ kpiEmission }}</div><div class="sub">{{ kpiEmissionSub }}</div></div></div>
      <div class="col-6 col-lg-3"><div class="card kpi"><div class="label">总能耗 (kWh)</div><div class="value">{{ kpiEnergy }}</div><div class="sub">{{ kpiEnergySub }}</div></div></div>
      <div class="col-6 col-lg-3"><div class="card kpi"><div class="label">覆盖车间数</div><div class="value">{{ workshopCount }}</div><div class="sub">按车间维度</div></div></div>
      <div class="col-6 col-lg-3"><div class="card kpi"><div class="label">覆盖班组数</div><div class="value">{{ teamCount }}</div><div class="sub">按班组维度</div></div></div>
    </div>

    <div class="row g-3 mb-3">
      <div class="col-lg-6"><div class="card"><div class="card-title">车间碳排排名</div><div ref="workshopEl" class="chart"></div></div></div>
      <div class="col-lg-6"><div class="card"><div class="card-title">班组碳排占比</div><div ref="teamEl" class="chart"></div></div></div>
    </div>

    <div class="row g-3">
      <div class="col-lg-6"><div class="card"><div class="card-title">高碳排设备 Top10</div><div ref="topEl" class="chart"></div></div></div>
      <div class="col-lg-6"><div class="card"><div class="card-title">按小时碳排趋势</div><div ref="trendEl" class="chart"></div></div></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getOverview } from '../api'
import { fmt, TYPE_NAMES } from '../constants'
import { setConnection } from '../composables/connection'
import { useEcharts } from '../composables/useEcharts'

const workshopEl = ref(null)
const teamEl = ref(null)
const topEl = ref(null)
const trendEl = ref(null)
const { setOption: setWorkshop } = useEcharts(workshopEl)
const { setOption: setTeam } = useEcharts(teamEl)
const { setOption: setTop } = useEcharts(topEl)
const { setOption: setTrend } = useEcharts(trendEl)

const data = ref({})
const alertMsg = ref('')
const alertType = ref('')

const kpiEmission = computed(() => fmt(data.value.total_emission))
const kpiEmissionSub = computed(() => '≈ ' + fmt((data.value.total_emission || 0) / 1000) + ' 吨')
const kpiEnergy = computed(() => fmt(data.value.total_energy))
const kpiEnergySub = computed(() => '≈ ' + fmt((data.value.total_energy || 0) / 1000) + ' MWh')
const workshopCount = computed(() => (data.value.by_workshop || []).length)
const teamCount = computed(() => (data.value.by_team || []).length)

function showError(m) { alertMsg.value = m; alertType.value = 'danger' }
function showEmpty(m) { alertMsg.value = m; alertType.value = 'warning' }

function renderWorkshop(ws) {
  setWorkshop({
    grid: { left: 16, right: 20, top: 10, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', name: 'kgCO₂' },
    yAxis: { type: 'category', data: ws.map(x => x.workshop_name || x.workshop_id), inverse: true },
    series: [{
      type: 'bar', data: ws.map(x => x.carbon_emission), barMaxWidth: 26,
      itemStyle: { color: '#10b981', borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', formatter: p => fmt(p.value) },
    }],
  })
}

function renderTeam(tm) {
  setTeam({
    tooltip: { trigger: 'item', formatter: '{b}: {c} kgCO₂ ({d}%)' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '68%'],
      data: tm.map(x => ({ name: x.team_name || x.team_id, value: x.carbon_emission })),
      label: { formatter: '{b}\n{d}%' },
      color: ['#0f766e', '#10b981', '#f59e0b'],
    }],
  })
}

function renderTop(eq) {
  setTop({
    grid: { left: 16, right: 20, top: 10, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: ps => {
        const i = ps[0].dataIndex
        const t = TYPE_NAMES[eq[i].equipment_type] || eq[i].equipment_type
        return `${eq[i].equipment_id}（${t}）<br/>碳排：${fmt(eq[i].carbon_emission)} kgCO₂`
      },
    },
    xAxis: { type: 'category', data: eq.map(x => x.equipment_id), axisLabel: { rotate: 40 } },
    yAxis: { type: 'value', name: 'kgCO₂' },
    series: [{
      type: 'bar', data: eq.map(x => x.carbon_emission), barMaxWidth: 22,
      itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] },
    }],
  })
}

function renderTrend(trend) {
  const labels = trend.map(x => (x.timestamp || '').replace('T', ' ').slice(5, 16))
  const carbon = trend.map(x => x.carbon_emission)
  const energy = trend.map(x => x.energy_consumption)
  setTrend({
    tooltip: { trigger: 'axis' },
    legend: { data: ['碳排 (kgCO₂)', '能耗 (kWh)'], bottom: 0 },
    grid: { left: 16, right: 20, top: 30, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: labels, axisLabel: { interval: Math.ceil(labels.length / 12) } },
    yAxis: [{ type: 'value', name: '碳排' }, { type: 'value', name: '能耗' }],
    series: [
      { name: '碳排 (kgCO₂)', type: 'line', smooth: true, data: carbon, itemStyle: { color: '#0f766e' }, areaStyle: { opacity: .12 } },
      { name: '能耗 (kWh)', type: 'line', smooth: true, yAxisIndex: 1, data: energy, itemStyle: { color: '#f59e0b' } },
    ],
  })
}

async function load() {
  alertMsg.value = ''
  try {
    const json = await getOverview()
    if (json.code !== 200) { showError(json.message || ('code=' + json.code)); return }
    const d = json.data || {}
    data.value = d
    renderWorkshop(d.by_workshop || [])
    renderTeam(d.by_team || [])
    renderTop(d.by_equipment_top || [])
    renderTrend(d.hourly_trend || [])
    if (d.message && (!d.by_workshop || d.by_workshop.length === 0)) showEmpty(d.message)
    setConnection('已连接 · 数据实时', 'text-success')
  } catch (e) {
    showError('无法连接后端 8001：' + e.message)
    setConnection('后端未连接', 'text-danger')
  }
}

onMounted(load)
</script>