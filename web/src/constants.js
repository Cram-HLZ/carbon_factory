// constants.js —— 全局常量（角色名 / 严重度 / 设备类型 / 车间 / 运行状态 / 接口地址）
// 原 app.js + 各页面分散硬编码，统一收口到此处

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8001/api'

export const WS_ALERT_URL =
  API_BASE.replace(/^http/, 'ws').replace(/\/api$/, '') + '/ws/alerts'

export const ROLE_NAMES = { it_admin: 'IT管理员', management: '管理层', operator: '运维岗' }

export const SEVERITY_LABEL = { high: '高', medium: '中', low: '低', normal: '正常' }

// bootstrap 颜色后缀（badge-* / alert-* 通用）
export const SEVERITY_COLOR = { high: 'danger', medium: 'warning', low: 'primary', normal: 'secondary' }

export const STATUS_LABEL = { pending: '待处理', processing: '处理中', resolved: '已解决' }
export const STATUS_BADGE = { pending: 'bg-secondary', processing: 'bg-warning text-dark', resolved: 'bg-success' }

// 设备类型 → 中文名（Top10/工具提示/实时页通用）
export const TYPE_NAMES = {
  appearance_inspector: '电芯外观检测机', dimension_inspector: '电芯尺寸检测机',
  winding_machine: '电芯卷绕机', formation_cabinet: '电芯化成柜', sorting_machine: '电芯分选机',
  conveyor_line: '电芯输送流水线', baking_oven: '电芯烘烤炉', agv: '自动导引运输车AGV',
  cnc_milling_machine: '数控龙门铣床', compressor: '空压机', cooling_fan: '冷却风机', chiller: '冷水机组',
}

// 车间编号 → 中文名
export const WORKSHOPS = {
  'WS-01': '电芯制备车间', 'WS-02': '电芯化成车间', 'WS-03': '电芯检测分选车间',
  'WS-04': '模具加工车间', 'WS-05': '物流动力区',
}

// 运行状态
export const RUN_STATUS = { 0: '停机', 1: '运行', 2: '待机' }
export const RUN_STATUS_CLS = { 0: 'badge-stop', 1: 'badge-run', 2: 'badge-standby' }

// 通用格式化
export function fmt(v, digits = 1) {
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}