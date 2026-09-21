"""
alarm_routes —— 告警管理路由

提供：
    GET    /api/alarms                 告警历史查询（按状态/严重度/设备过滤 + 分页）
    GET    /api/alarms/{id}            单条告警详情
    POST   /api/alarms                 手动录入告警记录
    PUT    /api/alarms/{id}            编辑告警记录（严重度/根因/状态/时间）
    PUT    /api/alarms/{id}/status     更新处理状态（pending / processing / resolved）
    DELETE /api/alarms/{id}            删除单条告警记录
    DELETE /api/alarms?ids=1,2,3       批量删除告警记录
    POST   /api/alarms/scan            手动触发一轮实时检测扫描（联调/演示用）
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field

from backend import alarm_service, detection_loop
from backend.security import get_current_user, require_roles
from database.models import User

router = APIRouter(prefix='/api/alarms', tags=['告警管理'])


class StatusUpdate(BaseModel):
    status: str = Field(..., description='pending / processing / resolved')


class AlarmCreate(BaseModel):
    equipment_id: str = Field(..., min_length=1, description='设备编号')
    severity: str = Field('medium', description='high / medium / low')
    root_cause: str = Field('', description='告警根因描述')
    alarm_time: Optional[datetime] = Field(None, description='告警时间，缺省当前时间')


class AlarmUpdate(BaseModel):
    equipment_id: Optional[str] = Field(None, min_length=1, description='设备编号')
    severity: Optional[str] = Field(None, description='high / medium / low')
    root_cause: Optional[str] = Field(None, description='告警根因描述')
    status: Optional[str] = Field(None, description='pending / processing / resolved')
    alarm_time: Optional[datetime] = Field(None, description='告警时间')


@router.get('', summary='告警历史查询')
async def list_alarms(
    status: Optional[str] = Query(None, description='处理状态过滤 pending/processing/resolved'),
    severity: Optional[str] = Query(None, description='严重度过滤 high/medium/low'),
    equipment_id: Optional[str] = Query(None, description='设备ID过滤'),
    limit: int = Query(100, ge=1, le=500, description='每页条数'),
    offset: int = Query(0, ge=0, description='偏移量'),
    _: User = Depends(get_current_user),
):
    return alarm_service.list_alarms(status, severity, equipment_id, limit, offset)


@router.get('/{alarm_id}', summary='单条告警详情')
async def get_alarm(alarm_id: int, _: User = Depends(get_current_user)):
    rec = alarm_service.get_alarm(alarm_id)
    if rec is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, '告警记录不存在')
    return rec


@router.put('/{alarm_id}/status', summary='更新告警处理状态')
async def update_status(
    alarm_id: int,
    body: StatusUpdate,
    _: User = Depends(require_roles('operator', 'it_admin')),
):
    try:
        rec = alarm_service.update_alarm_status(alarm_id, body.status)
    except ValueError as exc:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if rec is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, '告警记录不存在')
    return rec


@router.post('', summary='手动录入告警记录', status_code=http_status.HTTP_201_CREATED)
async def create_alarm(
    body: AlarmCreate,
    _: User = Depends(require_roles('operator', 'it_admin')),
):
    try:
        return alarm_service.create_alarm(
            body.equipment_id, body.severity, body.root_cause, body.alarm_time
        )
    except ValueError as exc:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.put('/{alarm_id}', summary='编辑告警记录')
async def update_alarm(
    alarm_id: int,
    body: AlarmUpdate,
    _: User = Depends(require_roles('operator', 'it_admin')),
):
    try:
        rec = alarm_service.update_alarm(alarm_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if rec is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, '告警记录不存在')
    return rec


@router.delete('/{alarm_id}', summary='删除单条告警记录')
async def delete_alarm(alarm_id: int, _: User = Depends(require_roles('it_admin'))):
    if not alarm_service.delete_alarm(alarm_id):
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, '告警记录不存在')
    return {'deleted': alarm_id}


@router.delete('', summary='批量删除告警记录')
async def batch_delete_alarms(
    ids: str = Query(..., description='逗号分隔的告警ID，如 1,2,3'),
    _: User = Depends(require_roles('it_admin')),
):
    try:
        id_list = [int(x) for x in ids.split(',') if x.strip()]
    except ValueError:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, 'ids 必须为逗号分隔的整数')
    if not id_list:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, '请提供至少一个告警ID')
    return {'deleted': alarm_service.delete_alarms(id_list)}


@router.post('/scan', summary='手动触发实时检测扫描')
async def scan(_: User = Depends(get_current_user)):
    """立即扫描一轮代表设备，返回本轮触发推送的告警列表（联调/演示）"""
    alerts = await detection_loop.scan_once()
    return {
        'scanned': len(detection_loop.SCAN_EQUIPMENT),
        'triggered': len(alerts),
        'alerts': alerts,
    }