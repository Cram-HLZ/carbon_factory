"""
detection_loop —— 后台异常检测调度循环

启动一个 asyncio 后台任务，按固定间隔扫描代表性设备，调用算法侧
GET /api/v1/anomaly/equipment/{id} 做实时检测；检测到异常且算法侧判定
should_alert=True（含 10 分钟冷却）时，触发「落库 + 多渠道推送」。

生产环境可替换为「数据采集入站后直接触发检测」，这里用轮询作为
无真实 PLC 时的兜底实时驱动，保证 WebSocket 推送链路能自动跑起来。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.settings import ALERT_CONFIG
from backend.algorithm_client import call_algo
from backend.alarm_service import process_detection

logger = logging.getLogger(__name__)

# 参与实时扫描的代表设备（读取 config.ALERT_CONFIG）
SCAN_EQUIPMENT: List[str] = list(ALERT_CONFIG['scan_equipment'])

_stop_event: Optional[asyncio.Event] = None
_task: Optional[asyncio.Task] = None


def _load_sequence(equipment_id: str, minutes: int = 70) -> Optional[List[List[float]]]:
    """
    从数据库读取设备最近 minutes 分钟时序数据，构造成 60×8 特征序列。

    8 维特征顺序（与 feature_engineer.FEATURE_COLUMNS 严格一致）：
        load_rate, power, energy_diff, temperature, vibration,
        carbon_emission, power_change_rate, runtime_hours
    不足 60 条时返回 None（数据不足以做序列检测）。

    说明：无训练权重 / torch 未安装时，算法侧 /anomaly/detect 走统计兜底
    （fallback），不依赖 scaler 归一化，故这里直接传原始物理量即可。
    """
    from database.database import SessionLocal
    from database.models import TimeSeriesData

    since = datetime.now() - timedelta(minutes=minutes)
    with SessionLocal() as db:
        rows = (
            db.query(TimeSeriesData)
            .filter(
                TimeSeriesData.equipment_id == equipment_id,
                TimeSeriesData.timestamp >= since,
            )
            .order_by(TimeSeriesData.timestamp.asc())
            .all()
        )

    if len(rows) < 60:
        logger.debug('设备 %s 近期数据不足（%d<60），跳过检测', equipment_id, len(rows))
        return None

    rows = rows[-60:]  # 取最近 60 个采样点
    seq: List[List[float]] = []
    prev_power: Optional[float] = None
    for row in rows:
        power = float(row.power or 0.0)
        load_rate = float(row.load_rate or 0.0)
        temperature = float(row.temperature or 0.0)
        vibration = float(row.vibration or 0.0)
        carbon = float(row.carbon_emission or 0.0)
        energy_diff = power / 60.0  # 每分钟能耗增量 (kWh/min)
        power_change = (power - prev_power) if prev_power is not None else 0.0
        # runtime_hours 透传 0（fallback 检测不依赖该维度，训练模型就绪后再接入累积值）
        seq.append(
            [
                load_rate,
                power,
                energy_diff,
                temperature,
                vibration,
                carbon,
                power_change,
                0.0,
            ]
        )
        prev_power = power
    return seq


async def _detect_one(equipment_id: str) -> Optional[Dict[str, Any]]:
    """从数据库读数据 → 调算法 POST /anomaly/detect → 返回检测结果（无数据时 None）"""
    seq = await asyncio.to_thread(_load_sequence, equipment_id)
    if seq is None:
        return None

    # call_algo 为同步 urllib，放线程池避免阻塞事件循环
    resp = await asyncio.to_thread(
        call_algo,
        '/anomaly/detect',
        'POST',
        None,
        {'equipment_id': equipment_id, 'sequence_data': seq},
    )
    if not isinstance(resp, dict):
        return None
    data = resp.get('data')
    if not isinstance(data, dict):
        return None
    data.setdefault('equipment_id', equipment_id)
    return data


async def scan_once() -> List[Dict[str, Any]]:
    """扫描一轮全部代表设备，返回本轮实际触发的告警 payload 列表"""
    detections = await asyncio.gather(*(_detect_one(eq) for eq in SCAN_EQUIPMENT))
    alerts: List[Dict[str, Any]] = []
    for detection in detections:
        if detection is None:
            continue
        try:
            payload = await process_detection(detection)
        except Exception as exc:
            logger.exception('处理检测结果失败（%s）: %s', detection.get('equipment_id'), exc)
            continue
        if payload:
            alerts.append(payload)
    return alerts


async def _loop(stop_event: asyncio.Event) -> None:
    interval = ALERT_CONFIG['detect_interval_seconds']
    logger.info('告警实时检测循环启动：每 %ds 扫描 %d 台设备', interval, len(SCAN_EQUIPMENT))
    while not stop_event.is_set():
        try:
            await scan_once()
        except Exception as exc:
            logger.exception('检测循环异常: %s', exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def start() -> None:
    """启动后台检测循环（幂等）"""
    global _stop_event, _task
    if _task is not None:
        return
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_loop(_stop_event))


async def stop() -> None:
    """停止后台检测循环（优雅停机）"""
    global _stop_event, _task
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        _stop_event = None