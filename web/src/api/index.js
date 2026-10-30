// api/index.js —— 后端接口封装（统一返回 resp.data，业务视图自行处理 code/data 封装）
import http from './http'

// ==================== 认证 ====================
export const login = (account, password) => http.post('/auth/login', { account, password }).then(r => r.data)
export const register = (account, password) => http.post('/auth/register', { account, password }).then(r => r.data)
export const getMe = () => http.get('/auth/me').then(r => r.data)
export const logout = () => http.post('/auth/logout').then(r => r.data)
export const getRoles = () => http.get('/auth/roles').then(r => r.data)

export const listUsers = () => http.get('/auth/users').then(r => r.data)
export const createUser = (payload) => http.post('/auth/users', payload).then(r => r.data)
export const updateUser = (id, payload) => http.put(`/auth/users/${id}`, payload).then(r => r.data)
export const deleteUser = (id) => http.delete(`/auth/users/${id}`).then(r => r.data)

// ==================== 算法转发（{code, message, data} 封装） ====================
export const getOverview = () => http.get('/carbon/overview').then(r => r.data)
export const getHeatmap = (start_time, end_time) =>
  http.get('/carbon/heatmap', { params: { start_time, end_time } }).then(r => r.data)
export const getRealtime = (equipmentId) =>
  http.get(`/equipment/realtime/${encodeURIComponent(equipmentId)}`).then(r => r.data)
export const getEquipmentList = () => http.get('/equipment/list').then(r => r.data)

// ==================== 告警 ====================
export const listAlarms = (params) => http.get('/alarms', { params }).then(r => r.data)
export const createAlarm = (body) => http.post('/alarms', body).then(r => r.data)
export const updateAlarm = (id, body) => http.put(`/alarms/${id}`, body).then(r => r.data)
export const updateAlarmStatus = (id, status) => http.put(`/alarms/${id}/status`, { status }).then(r => r.data)
export const deleteAlarm = (id) => http.delete(`/alarms/${id}`).then(r => r.data)
export const batchDeleteAlarms = (ids) => http.delete('/alarms', { params: { ids: ids.join(',') } }).then(r => r.data)
export const scanAlarms = () => http.post('/alarms/scan').then(r => r.data)

// ==================== 分项计量 ====================
export const getSubmeterSummary = (params) =>
  http.get('/ingest/submeter/summary', { params }).then(r => r.data)

// ==================== 报表 ====================
export const reportMonthly = (year, month) =>
  http.get('/report/monthly', { params: { year, month, format: 'json' } }).then(r => r.data)
export const reportTraceability = (params) =>
  http.get('/report/traceability', { params: { ...params, format: 'json' } }).then(r => r.data)
export const reportSavings = () =>
  http.get('/report/savings', { params: { format: 'json' } }).then(r => r.data)
export const reportMrv = (year, month) =>
  http.get('/report/mrv', { params: { year, month, format: 'json' } }).then(r => r.data)

// 报表导出：拉取 excel/pdf 二进制流并解析文件名
export async function downloadReport(path, params, fallbackName) {
  const resp = await http.get(path, { params, responseType: 'blob' })
  const cd = resp.headers['content-disposition'] || ''
  let name = fallbackName
  const m = cd.match(/filename\*=UTF-8''([^;]+)/i)
  if (m) name = decodeURIComponent(m[1])
  else { const m2 = cd.match(/filename="?([^";]+)"?/i); if (m2) name = m2[1] }
  return { blob: resp.data, name }
}

// 触发浏览器下载
export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name || 'report'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}