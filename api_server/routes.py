"""
routes —— FastAPI 路由定义

所有算法接口端点都在这里。前缀统一为 /api/v1。
Swagger UI 在线测试：http://localhost:8000/docs//终端输入uvicorn main:app --reload --port 8000命令启动服务

【接口列表】
    碳排相关：
        POST /api/v1/carbon/query          碳排数据查询（四级聚合）
        GET  /api/v1/carbon/overview        厂区碳排总览
        GET  /api/v1/carbon/heatmap         碳排热力图数据
    异常检测：
        POST /api/v1/anomaly/detect         异常检测（输入 60×8 矩阵）
        GET  /api/v1/anomaly/equipment/{id} 设备当前异常状态
    溯源：
        POST /api/v1/traceability/report    设备碳排溯源报告
    降碳方案：
        POST /api/v1/strategy/generate      AI 降碳方案生成
    设备实时数据：
        GET  /api/v1/equipment/realtime/{id} 设备实时数据
        GET  /api/v1/equipment/list          设备列表（可按车间筛选）
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api_server.schemas import (
    AnomalyDetectRequest,
    APIResponse,
    CarbonQueryRequest,
    StrategyRequest,
    TraceabilityRequest,
)
from api_server import services


router = APIRouter(prefix='/api/v1', tags=['算法接口'])


# ============================================================
# 碳排数据接口
# ============================================================
@router.post('/carbon/query', response_model=APIResponse, summary='碳排数据查询')
async def query_carbon_emission(request: CarbonQueryRequest):
    """按厂区/车间/设备/班组四级聚合查询碳排数据"""
    result = services.get_carbon_emission_data(request)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


@router.get('/carbon/overview', response_model=APIResponse, summary='厂区碳排总览')
async def get_factory_overview():
    """厂区总览：总碳排、按车间/班组/设备 Top 排名、按小时趋势"""
    result = services.get_factory_overview()
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


@router.get('/carbon/heatmap', response_model=APIResponse, summary='碳排热力图数据')
async def get_heatmap(
    start_time: datetime = Query(..., description='ISO 8601 起始时间'),
    end_time: datetime = Query(..., description='ISO 8601 结束时间'),
):
    """碳排热力图数据：返回各设备碳排强度，供前端渲染热力图"""
    result = services.get_heatmap_data(start_time, end_time)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


# ============================================================
# 异常检测接口
# ============================================================
@router.post('/anomaly/detect', response_model=APIResponse, summary='异常检测')
async def detect_anomaly(request: AnomalyDetectRequest):
    """
    异常检测：输入 60×8 时序数据矩阵，返回是否异常及严重程度。

    sequence_data 必须是已经归一化后的数据（用训练时保存的 scaler）。
    若没有 scaler，可调用 /api/v1/anomaly/equipment/{id} 走实时检测流程。
    """
    result = services.detect_anomaly(request)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


@router.get('/anomaly/equipment/{equipment_id}', response_model=APIResponse, summary='设备当前异常状态')
async def get_equipment_anomaly_status(equipment_id: str):
    """获取设备当前异常状态（从最近一条数据自动检测）"""
    result = services.get_equipment_anomaly_status(equipment_id)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


# ============================================================
# 溯源接口
# ============================================================
@router.post('/traceability/report', response_model=APIResponse, summary='设备碳排溯源报告')
async def get_traceability_report(request: TraceabilityRequest):
    """设备碳排溯源：近 72h 历史 + 高碳排根因分析 + 改进建议"""
    result = services.get_traceability_report(request)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


# ============================================================
# 降碳方案接口
# ============================================================
@router.post('/strategy/generate', response_model=APIResponse, summary='AI 降碳方案生成')
async def generate_strategies(request: StrategyRequest):
    """
    AI 降碳方案生成：输出设备运维/生产排班/工艺优化三类方案，
    按投入产出比自动排序。
    """
    result = services.generate_strategies(request)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


# ============================================================
# 设备实时数据接口
# ============================================================
@router.get('/equipment/realtime/{equipment_id}', response_model=APIResponse, summary='设备实时数据')
async def get_equipment_realtime(equipment_id: str):
    """设备实时数据：功率、负载率、碳排、温度、运行状态"""
    result = services.get_equipment_realtime(equipment_id)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


@router.get('/equipment/list', response_model=APIResponse, summary='设备列表')
async def list_equipment(workshop_id: Optional[str] = Query(None, description='可选车间过滤')):
    """设备列表：可按车间筛选，返回所有 78 台设备元信息"""
    result = services.list_equipment(workshop_id)
    if isinstance(result, dict) and 'error' in result:
        return APIResponse(code=500, message=result['error'], data=result)
    return APIResponse(data=result)


# ============================================================
# 健康检查
# ============================================================
@router.get('/health', summary='健康检查')
async def health():
    return {'status': 'healthy', 'service': 'carbon_factory_algorithm'}
