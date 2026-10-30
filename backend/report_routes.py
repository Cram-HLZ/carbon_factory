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
    build_mrv_report,
    monthly_report,
    mrv_metrics,
    mrv_workbook,
    savings_comparison,
    traceability_ledger,
)
from backend.security import get_current_user
from database.database import get_db
from database.models import MrvReport, User

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


@router.get('/mrv', summary='MRV 碳排放核查报告')
async def report_mrv(
    year: int = Query(..., ge=2000, le=2100, description='年份，如 2026'),
    month: int = Query(..., ge=1, le=12, description='月份，如 9'),
    fmt: str = Query('json', alias='format', description='json / excel / pdf'),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = mrv_metrics(db, year, month)
    # 核算结果与数据质量评分落台账，支撑核查留痕
    db.add(MrvReport(
        period=m['period'],
        scope1_emission=m['scope1'],
        scope2_emission=m['scope2'],
        scope3_emission=m['scope3'],
        data_quality_score=m['data_quality_score'],
        methodology='GHG Protocol / ISO 14064-1 排放因子法',
        uncertainty=f"覆盖 {m['active_count']}/{m['registered']} 台设备",
        generated_by=user.account,
    ))
    db.commit()
    return _output(build_mrv_report(m), fmt, f'MRV碳排放核查报告_{m["period"]}')


@router.get('/mrv/workbook', summary='MRV 核算底稿（逐设备×逐日明细）')
async def report_mrv_workbook(
    year: int = Query(..., ge=2000, le=2100, description='年份，如 2026'),
    month: int = Query(..., ge=1, le=12, description='月份，如 9'),
    fmt: str = Query('json', alias='format', description='json / excel / pdf'),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    data = mrv_workbook(db, year, month)
    return _output(data, fmt, f'MRV核算底稿_{year}{month:02d}')


@router.get('/mrv/history', summary='MRV 核查报告台账')
async def mrv_history(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    records = db.query(MrvReport).order_by(MrvReport.created_at.desc()).all()
    return {
        'data': [
            {
                'id': r.id,
                'period': r.period,
                'scope1_emission': r.scope1_emission,
                'scope2_emission': r.scope2_emission,
                'scope3_emission': r.scope3_emission,
                'data_quality_score': r.data_quality_score,
                'verification_status': r.verification_status,
                'verifier': r.verifier,
                'verified_at': r.verified_at.isoformat() if r.verified_at else None,
                'generated_by': r.generated_by,
                'created_at': r.created_at.isoformat(),
            }
            for r in records
        ]
    }


@router.post('/mrv/{report_id}/verify', summary='MRV 报告核查确认')
async def mrv_verify(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = db.query(MrvReport).filter(MrvReport.id == report_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail='报告不存在')
    record.verifier = user.account
    record.verified_at = datetime.now()
    record.verification_status = 'verified'
    db.commit()
    return {'message': f'报告 {record.period} 核查完成', 'verifier': user.account}