"""
history_routes —— 历史时序查询 / 手动归档路由

    GET  /api/history/timeseries   单设备时序查询（自动跨原始+归档，支持粒度选择）
    POST /api/history/archive      手动触发一轮归档（默认 IT管理员 / 运维岗可操作）

均需登录；归档兜底由 backend.archive_loop 定时执行，手动接口用于联调/排障。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.archive_service import run_archive
from backend.security import get_current_user, require_roles
from backend.timeseries_service import query_timeseries
from database.database import get_db
from database.models import User

router = APIRouter(prefix='/api/history', tags=['历史时序'])


@router.get('/timeseries', summary='单设备时序查询')
async def history_timeseries(
    equipment_id: str = Query(..., description='设备编号，如 I-9-01'),
    start: datetime = Query(..., description='起始时间 ISO 8601'),
    end: datetime = Query(..., description='结束时间 ISO 8601'),
    granularity: str = Query('auto', description='minute / hour / day / auto（按跨度自动）'),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if start >= end:
        raise HTTPException(status_code=400, detail='start 必须早于 end')
    return query_timeseries(db, equipment_id, start, end, granularity)


@router.post('/archive', summary='手动触发归档')
async def history_archive(
    _: User = Depends(require_roles('it_admin', 'operator')),
):
    """立即执行一轮归档：清理超期归档 + 分钟级数据降采样 + 删除已归档原始行"""
    result = await run_in_threadpool(run_archive)
    return result