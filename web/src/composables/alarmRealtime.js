// composables/alarmRealtime.js —— 实时告警 WebSocket（自动重连 + 全局 Toast + 订阅回调）
import { pushToast } from './toast'
import { WS_ALERT_URL, SEVERITY_COLOR, SEVERITY_LABEL } from '../constants'

let ws = null
let retry = 0
let timer = null
let subscriber = null

function onAlarm(a) {
  const feats = (a.feature_contributions || [])
    .slice(0, 3)
    .map(f => `${f.feature_name || f.feature} ${Math.round((f.contribution || 0) * 100)}%`)
    .join(' · ')
  pushToast({
    variant: SEVERITY_COLOR[a.severity] || 'secondary',
    title: `⚠ ${a.equipment_name || a.equipment_id} · ${SEVERITY_LABEL[a.severity] || a.severity}级告警`,
    lines: [
      `设备 ${a.equipment_id} · 异常得分 ${a.anomaly_score == null ? '—' : a.anomaly_score}`,
      a.root_cause || '',
      feats ? `Top 特征：${feats}` : '',
      a.alarm_time || '',
    ].filter(Boolean),
  })
  if (typeof subscriber === 'function') {
    try { subscriber(a) } catch (e) { /* 忽略订阅者异常 */ }
  }
}

function scheduleReconnect() {
  if (!localStorage.getItem('cf_token')) return
  const delay = Math.min(30000, 3000 * Math.pow(2, retry))
  retry = Math.min(retry + 1, 5)
  clearTimeout(timer)
  timer = setTimeout(connect, delay)
}

function connect() {
  if (!localStorage.getItem('cf_token')) return
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  try {
    ws = new WebSocket(WS_ALERT_URL)
  } catch (e) {
    scheduleReconnect()
    return
  }
  ws.onopen = () => { retry = 0 }
  ws.onmessage = (ev) => {
    let msg
    try { msg = JSON.parse(ev.data) } catch (e) { return }
    if (msg && msg.type === 'alarm') onAlarm(msg)
  }
  ws.onclose = () => { ws = null; scheduleReconnect() }
  ws.onerror = () => { try { if (ws) ws.close() } catch (e) {} }
}

export function useAlarmRealtime() {
  return {
    connect,
    disconnect() {
      clearTimeout(timer)
      if (ws) { ws.onclose = null; ws.close() }
      ws = null
    },
    setSubscriber(fn) { subscriber = fn },
  }
}