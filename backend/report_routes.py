"""
report_routes —— 报表中心路由

三个下载/预览接口，统一 format 参数切换输出形态：
    format=json   返回规范化报表结构（前端预览）
    format=excel 返回 .xlsx 文件流
    format=pdf   返回 .pdf 文件流

均需登录（Depends(get_current_user)），前端 app.js 会自动注入 token。
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from backend.report_export import to_excel, to_pdf
from backend.report_service import (
    monthly_report,
    savings_comparison,
    traceability_ledger,
)
from backend.security import get_current_user
from database.database import get_db
from database.models import User

router = APIRouter(prefix='/api/report', tags=['报表中心'])

_EXCEL_MEDIA = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _output(data: dict, fmt: str, base_name: str):
    """按 format 返回 JSON 预览或文件下载流"""
    if fmt == 'json':
        return JSONResponse(data)
    if fmt == 'excel':
        content, media, ext = to_excel(data), _EXCEL_MEDIA, 'xlsx'
    elif fmt == 'pdf':
        content, media, ext = to_pdf(data), 'application/pdf', 'pdf'
    else:
        raise HTTPException(status_code=400, detail='format 仅支持 json / excel / pdf')

    filename = f'{base_name}.{ext}'
    encoded = f"attachment; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        BytesIO(content), media_type=media, headers={'Content-Disposition': encoded}
    )


@router.get('/monthly', summary='月度碳排报告')
async def report_monthly(
    year: int = Query(..., ge=2000, le=2100, description='年份，如 2026'),
    month: int = Query(..., ge=1, le=12, description='月份，如 9'),
    fmt: str = Query('json', alias='format', description='json / excel / pdf'),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    data = monthly_report(db, year, month)
    return _output(data, fmt, f'月度碳排报告_{year}{month:02d}')


@router.get('/traceability', summary='设备溯源台账')
async def report_traceability(
    equipment_id: Optional[str] = Query(None, description='可选，指定单台设备；缺省全量'),
    start_time: Optional[datetime] = Query(None, description='可选，起始时间 ISO'),
    end_time: Optional[datetime] = Query(None, description='可选，结束时间 ISO'),
    fmt: str = Query('json', alias='format', description='json / excel / pdf'),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    data = traceability_ledger(db, equipment_id, start_time, end_time)
    return _output(data, fmt, '设备溯源台账')


@router.get('/savings', summary='降碳成效对比表')
async def report_savings(
    fmt: str = Query('json', alias='format', description='json / excel / pdf'),
    _: User = Depends(get_current_user),
):
    data = savings_comparison()
    return _output(data, fmt, '降碳成效对比表')