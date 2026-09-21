"""
alarm_service —— 告警业务服务层

职责：
    1. 异常检测结果（detection dict）→ 判定是否落库（should_alert）
    2. should_alert=True 时写入 alarm_record 表（处理状态初始化 pending）
    3. 编排多渠道推送：WebSocket + 移动端 + 邮件
    4. 告警历史查询 / 处理状态跟踪

【告警冷却】同一设备 10 分钟内只告警一次，由算法侧 anomaly_detector.should_alert
（alert_cooldown_seconds=600）保证，后端仅在 should_alert=True 时落库并推送。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.settings import EQUIPMENT_LIST, SEVERITY_LABELS
from database.database import SessionLocal
from database.models import AlarmRecord
from backend import notifier

logger = logging.getLogger(__name__)

VALID_STATUS = ('pending', 'processing', 'resolved')
VALID_SEVERITY = ('high', 'medium', 'low')


def _equipment_name(equipment_id: str) -> str:
    info = EQUIPMENT_LIST.get(equipment_id)
    return info['name'] if info else equipment_id


def _describe_root_cause(detection: Dict[str, Any]) -> str:
    sev = detection.get('severity', 'normal')
    label = SEVERITY_LABELS.get(sev, sev)
    score = detection.get('anomaly_score')
    return f'{label}级异常（异常得分 {score}，阈值 {detection.get("threshold")}）'


def _to_dict(rec: AlarmRecord) -> Dict[str, Any]:
    return {
        'id': rec.id,
        'equipment_id': rec.equipment_id,
        'equipment_name': _equipment_name(rec.equipment_id),
        'alarm_time': rec.alarm_time.strftime('%Y-%m-%d %H:%M:%S') if rec.alarm_time else None,
        'severity': rec.severity,
        'severity_label': SEVERITY_LABELS.get(rec.severity, rec.severity),
        'root_cause': rec.root_cause,
        'status': rec.status,
    }


# ============================================================
# 落库
# ============================================================
def record_alarm(detection: Dict[str, Any]) -> Dict[str, Any]:
    """写入一条告警记录，返回对外 dict"""
    rec = AlarmRecord(
        equipment_id=detection['equipment_id'],
        alarm_time=datetime.now(),
        severity=detection.get('severity', 'medium'),
        root_cause=_describe_root_cause(detection),
        status='pending',
    )
    with SessionLocal() as db:
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)


# ============================================================
# 历史查询 / 状态跟踪
# ============================================================
def get_alarm(alarm_id: int) -> Optional[Dict[str, Any]]:
    with SessionLocal() as db:
        rec = db.query(AlarmRecord).filter(AlarmRecord.id == alarm_id).first()
        return _to_dict(rec) if rec else None


def list_alarms(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    equipment_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """告警历史查询：支持按状态 / 严重度 / 设备过滤 + 分页"""
    with SessionLocal() as db:
        q = db.query(AlarmRecord)
        if status:
            q = q.filter(AlarmRecord.status == status)
        if severity:
            q = q.filter(AlarmRecord.severity == severity)
        if equipment_id:
            q = q.filter(AlarmRecord.equipment_id == equipment_id)
        total = q.count()
        rows = q.order_by(AlarmRecord.alarm_time.desc()).offset(offset).limit(limit).all()
        return {
            'total': total,
            'limit': limit,
            'offset': offset,
            'items': [_to_dict(r) for r in rows],
        }


def update_alarm_status(alarm_id: int, status: str) -> Optional[Dict[str, Any]]:
    """更新告警处理状态，非法状态抛 ValueError"""
    if status not in VALID_STATUS:
        raise ValueError(f'status 必须是 {"/".join(VALID_STATUS)} 之一')
    with SessionLocal() as db:
        rec = db.query(AlarmRecord).filter(AlarmRecord.id == alarm_id).first()
        if rec is None:
            return None
        rec.status = status
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)


# ============================================================
# 增删改（手动录入 / 编辑 / 删除）
# ============================================================
def create_alarm(
    equipment_id: str,
    severity: str = 'medium',
    root_cause: str = '',
    alarm_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """手动录入一条告警记录（默认待处理），非法严重度抛 ValueError"""
    if severity not in VALID_SEVERITY:
        raise ValueError(f'severity 必须是 {"/".join(VALID_SEVERITY)} 之一')
    with SessionLocal() as db:
        rec = AlarmRecord(
            equipment_id=equipment_id,
            alarm_time=alarm_time or datetime.now(),
            severity=severity,
            root_cause=root_cause or None,
            status='pending',
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)


def update_alarm(alarm_id: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """编辑告警记录（仅更新传入的非 None 字段，如 severity/root_cause/status）"""
    if fields.get('severity') is not None and fields['severity'] not in VALID_SEVERITY:
        raise ValueError(f'severity 必须是 {"/".join(VALID_SEVERITY)} 之一')
    if fields.get('status') is not None and fields['status'] not in VALID_STATUS:
        raise ValueError(f'status 必须是 {"/".join(VALID_STATUS)} 之一')
    with SessionLocal() as db:
        rec = db.query(AlarmRecord).filter(AlarmRecord.id == alarm_id).first()
        if rec is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(rec, key, value)
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)


def delete_alarm(alarm_id: int) -> bool:
    """删除单条告警记录，返回是否删除成功"""
    with SessionLocal() as db:
        rec = db.query(AlarmRecord).filter(AlarmRecord.id == alarm_id).first()
        if rec is None:
            return False
        db.delete(rec)
        db.commit()
        return True


def delete_alarms(ids: List[int]) -> int:
    """批量删除告警记录，返回删除条数"""
    if not ids:
        return 0
    with SessionLocal() as db:
        n = (
            db.query(AlarmRecord)
            .filter(AlarmRecord.id.in_(ids))
            .delete(synchronize_session=False)
        )
        db.commit()
        return n


# ============================================================
# 编排：落库 + 多渠道推送
# ============================================================
def _build_payload(rec: Dict[str, Any], detection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'type': 'alarm',
        'id': rec['id'],
        'equipment_id': rec['equipment_id'],
        'equipment_name': rec['equipment_name'],
        'severity': rec['severity'],
        'severity_label': rec['severity_label'],
        'anomaly_score': detection.get('anomaly_score'),
        'threshold': detection.get('threshold'),
        'reconstruction_error': detection.get('reconstruction_error'),
        'root_cause': rec['root_cause'],
        'alarm_time': rec['alarm_time'],
        'status': rec['status'],
    }


async def process_detection(detection: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """对单台设备的检测结果做「落库 + 多渠道推送」编排；不满足告警条件返回 None"""
    if not detection or not detection.get('should_alert'):
        return None
    if not detection.get('equipment_id'):
        return None

    rec = record_alarm(detection)
    payload = _build_payload(rec, detection)

    # 多渠道推送，任一渠道失败不影响其它渠道（已分别兜底）
    try:
        await notifier.notify_web_socket(payload)
    except Exception as exc:
        logger.warning('WebSocket 推送失败: %s', exc)
    try:
        await notifier.notify_mobile(payload)
    except Exception as exc:
        logger.warning('移动端推送失败: %s', exc)
    try:
        await notifier.notify_email(payload)
    except Exception as exc:
        logger.warning('邮件推送失败: %s', exc)
    return payload