<template>
  <div>
    <h5 class="mb-3 report-head">报表中心 <small class="text-secondary fs-6">（月度碳排报告 · 设备溯源台账 · 降碳成效对比 · 导出 PDF/Excel）</small></h5>

    <!-- ① 月度碳排报告 -->
    <div class="card mb-4" style="padding:18px 20px">
      <div class="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <h6 class="mb-0 fw-semibold">月度碳排报告</h6>
        <div class="d-flex align-items-end gap-2 flex-wrap">
          <div><label class="form-label small mb-1">年份</label><input v-model.number="monthly.year" class="form-control form-control-sm" type="number" style="width:96px" /></div>
          <div>
            <label class="form-label small mb-1">月份</label>
            <select v-model="monthly.month" class="form-select form-select-sm" style="width:80px">
              <option v-for="i in 12" :key="i" :value="i">{{ i }} 月</option>
            </select>
          </div>
          <div>
            <label class="form-label small mb-1">格式</label>
            <select v-model="monthly.format" class="form-select form-select-sm" style="width:90px">
              <option value="excel">Excel</option><option value="pdf">PDF</option>
            </select>
          </div>
          <button class="btn btn-sm btn-outline-success" @click="preview('monthly')">预览</button>
          <button class="btn btn-sm btn-success" @click="download('monthly')">下载</button>
        </div>
      </div>
      <div class="preview" v-html="states.monthly.html"></div>
    </div>

    <!-- ② 设备溯源台账 -->
    <div class="card mb-4" style="padding:18px 20px">
      <div class="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <h6 class="mb-0 fw-semibold">设备溯源台账</h6>
        <div class="d-flex align-items-end gap-2 flex-wrap">
          <div><label class="form-label small mb-1">设备编号</label><input v-model.trim="trace.equipmentId" class="form-control form-control-sm" placeholder="留空=全部设备" style="width:150px" /></div>
          <div><label class="form-label small mb-1">起始时间</label><input v-model="trace.start" class="form-control form-control-sm" type="datetime-local" style="width:190px" /></div>
          <div><label class="form-label small mb-1">结束时间</label><input v-model="trace.end" class="form-control form-control-sm" type="datetime-local" style="width:190px" /></div>
          <div>
            <label class="form-label small mb-1">格式</label>
            <select v-model="trace.format" class="form-select form-select-sm" style="width:90px">
              <option value="excel">Excel</option><option value="pdf">PDF</option>
            </select>
          </div>
          <button class="btn btn-sm btn-outline-success" @click="preview('trace')">预览</button>
          <button class="btn btn-sm btn-success" @click="download('trace')">下载</button>
        </div>
      </div>
      <div class="preview" v-html="states.trace.html"></div>
    </div>

    <!-- ③ 降碳成效对比表 -->
    <div class="card mb-4" style="padding:18px 20px">
      <div class="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <h6 class="mb-0 fw-semibold">降碳成效对比表 <small class="text-secondary">（8 台高耗能重点设备）</small></h6>
        <div class="d-flex align-items-end gap-2 flex-wrap">
          <div>
            <label class="form-label small mb-1">格式</label>
            <select v-model="savings.format" class="form-select form-select-sm" style="width:90px">
              <option value="excel">Excel</option><option value="pdf">PDF</option>
            </select>
          </div>
          <button class="btn btn-sm btn-outline-success" @click="preview('savings')">预览</button>
          <button class="btn btn-sm btn-success" @click="download('savings')">下载</button>
        </div>
      </div>
      <div class="preview" v-html="states.savings.html"></div>
    </div>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import {
  reportMonthly, reportTraceability, reportSavings,
  downloadReport, saveBlob,
} from '../api'

const states = reactive({
  monthly: reactive({ loading: false, error: '', html: '' }),
  trace: reactive({ loading: false, error: '', html: '' }),
  savings: reactive({ loading: false, error: '', html: '' }),
})

const monthly = reactive({ year: new Date().getFullYear(), month: new Date().getMonth() + 1, format: 'excel' })
const trace = reactive({ equipmentId: '', start: '', end: '', format: 'excel' })
const savings = reactive({ format: 'excel' })

function esc(v) {
  return String(v == null ? '—' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function renderReport(report) {
  if (!report || !report.sections) return '<div class="text-secondary small">暂无数据</div>'
  let html = ''
  if (report.subtitle) html += '<div class="small text-secondary mb-2">' + esc(report.subtitle) + '</div>'
  for (const sec of report.sections) {
    html += '<div class="fw-semibold mt-3 mb-2">' + esc(sec.heading) + '</div>'
    for (const t of (sec.tables || [])) {
      html += '<div class="table-responsive border rounded"><table class="table table-sm align-middle mb-0">'
      html += '<thead><tr>' + (t.headers || []).map(h => '<th class="text-nowrap">' + esc(h) + '</th>').join('') + '</tr></thead>'
      html += '<tbody>' + (t.rows || []).map(r => '<tr>' + r.map(c => '<td>' + esc(c) + '</td>').join('') + '</tr>').join('') + '</tbody>'
      html += '</table></div>'
    }
  }
  return html
}

function padSeconds(v) {
  if (!v) return ''
  return v.length === 16 ? v + ':00' : v
}

function config(key) {
  if (key === 'monthly') {
    const base = { year: monthly.year, month: monthly.month }
    return {
      path: '/report/monthly',
      jsonParams: base,
      dlParams: { ...base, format: monthly.format },
      fallback: `monthly_carbon_report_${monthly.year}_${monthly.month}`,
    }
  }
  if (key === 'trace') {
    // 未填写的条件不传参，避免空串被后端解析成非法 datetime（422）
    const base = {}
    if (trace.equipmentId) base.equipment_id = trace.equipmentId
    const s = padSeconds(trace.start)
    const e = padSeconds(trace.end)
    if (s) base.start_time = s
    if (e) base.end_time = e
    return {
      path: '/report/traceability',
      jsonParams: base,
      dlParams: { ...base, format: trace.format },
      fallback: 'equipment_traceability',
    }
  }
  return {
    path: '/report/savings',
    jsonParams: {},
    dlParams: { format: savings.format },
    fallback: 'carbon_savings_comparison',
  }
}

const loaders = {
  monthly: (p) => reportMonthly(p.year, p.month),
  trace: (p) => reportTraceability(p),
  savings: () => reportSavings(),
}

async function preview(key) {
  const st = states[key]
  const cfg = config(key)
  st.loading = true
  st.error = ''
  st.html = '<div class="text-secondary small">加载中…</div>'
  try {
    st.html = renderReport(await loaders[key](cfg.jsonParams))
  } catch (e) {
    st.html = '<div class="text-danger small">⚠ ' + esc(errText(e) || '请求失败') + '</div>'
  } finally {
    st.loading = false
  }
}

async function download(key) {
  const st = states[key]
  const cfg = config(key)
  st.error = ''
  try {
    const { blob, name } = await downloadReport(cfg.path, cfg.dlParams, cfg.fallback)
    saveBlob(blob, name)
  } catch (e) {
    st.html = '<div class="text-danger small">⚠ ' + esc(errText(e) || '下载失败') + '</div>'
  }
}

function errText(e) {
  const d = e && e.response && e.response.data
  if (d && d.detail) return d.detail
  if (d && typeof d === 'string') return d
  return ''
}
</script>

<style>
.preview table { font-size: 13px; }
.preview th { background: #0f766e; color: #fff; white-space: nowrap; }
.report-head { color: #0f766e; }
</style>