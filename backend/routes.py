"""
routes —— 后端路由定义（阶段1 全部为「透传转发」：Step 1B 的 3 个 GET + Step 1C 的 5 个端点）

【转发约定】
    - 前端请求后端路径：/api/xxx          （注意：没有 v1，和算法的 /api/v1/xxx 区分）
    - 后端转发算法路径：/api/v1/xxx       （由 algorithm_client.ALGO_BASE 统一拼前缀）
    - 阶段1 一律原样透传不加工 —— 先把链路跑通，业务组装放到阶段2（数据库就绪后）

【每个路由的 docstring 标注了】
    1. 对应的前端页面 / 交互场景
    2. 转发的算法接口
    3. 需要注意的透传参数

【阶段2 扩展指引】（后端同学）
    - overview / heatmap 接数据库后：改为「先查库，无数据再调算法」或「后端自行聚合」
    - anomaly/detect 接数据采集后：由后端把实时时序数据归一化后转发
    - 所有接口加认证依赖：Depends(get_current_user)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from backend.algorithm_client import call_algo

router = APIRouter(prefix='/api', tags=['后端→算法转发'])


# ============================================================
# 通用辅助
# ============================================================
async def passthrough_body(request: Request) -> Dict[str, Any]:
    """读取请求 JSON body 原样返回（透传用，不校验不加工）"""
    try:
        return await request.json()
    except Exception:
        return {}


# ============================================================
# Step 1B · 三个核心 GET 接口（对应前端 3 个页面）
# ============================================================
@router.get('/carbon/overview', summary='厂区碳排总览（前端「总览」页）')
async def carbon_overview():
    """
    转发算法 GET /api/v1/carbon/overview，无入参。
    返回 total_emission / by_workshop / by_team / by_equipment_top / hourly_trend。
    注意：算法侧有 30s 内存缓存，改数据不生效时等 30s 或重启算法服务。
    """
    return call_algo('/carbon/overview')


@router.get('/carbon/heatmap', summary='碳排热力图（前端「热力图」页）')
async def carbon_heatmap(
    start_time: datetime = Query(..., description='ISO 8601，如 2026-08-15T00:00:00'),
    end_time: datetime = Query(..., description='ISO 8601，如 2026-08-22T00:00:00'),
):
    """
    转发算法 GET /api/v1/carbon/heatmap，透传 start_time / end_time。
    返回各设备碳排强度 records（equipment_id / carbon_emission / power_mean 等）。
    """
    return call_algo(
        '/carbon/heatmap',
        params={'start_time': start_time.isoformat(), 'end_time': end_time.isoformat()},
    )


@router.get('/equipment/realtime/{equipment_id}', summary='设备实时数据（前端「设备实时」页）')
async def equipment_realtime(equipment_id: str):
    """
    转发算法 GET /api/v1/equipment/realtime/{equipment_id}。
    返回功率/负载率/碳排/温度/状态；无数据时返回占位结构 + message 字段，
    前端判断 message 存在时展示"暂无数据"。
    """
    return call_algo(f'/equipment/realtime/{equipment_id}')


# ============================================================
# Step 1C · 剩余接口转发
# ============================================================
@router.get('/equipment/list', summary='设备列表（前端设备下拉框/列表）')
async def equipment_list(
    workshop_id: Optional[str] = Query(None, description='可选车间过滤，如 WS-01'),
):
    """
    转发算法 GET /api/v1/equipment/list，透传 workshop_id（可选）。
    返回全部 78 台设备元信息（equipment_id / name / type / rated_power 等）。
    """
    params = {'workshop_id': workshop_id} if workshop_id else None
    return call_algo('/equipment/list', params=params)


@router.get('/anomaly/equipment/{equipment_id}', summary='设备当前异常状态（前端设备详情异常徽标）')
async def equipment_anomaly_status(equipment_id: str):
    """
    转发算法 GET /api/v1/anomaly/equipment/{equipment_id}。
    算法侧自动从模拟数据取最近 1 小时做检测，无需前端传时序数据。
    """
    return call_algo(f'/anomaly/equipment/{equipment_id}')


@router.post('/anomaly/detect', summary='异常检测（前端实时监测触发）')
async def anomaly_detect(request: Request):
    """
    转发算法 POST /api/v1/anomaly/detect。
    body: {"equipment_id": "I-9-01", "sequence_data": [[8个float] x 60行]}

    【避坑】（对应执行计划避坑清单第1、2条）
        - sequence_data 需归一化后传入；scaler 文件只在设备训练后存在
          （output/model_weight/scaler_{equipment_id}.pkl），联调前先 ls 核对。
        - 当前未训练任何模型 → threshold_type 返回 "fallback"（统计偏离度），
          能联调但精度低，上线前训练 5 台高耗能设备（见 README 训练命令）。
    """
    body = await passthrough_body(request)
    return call_algo('/anomaly/detect', method='POST', json_body=body)


@router.post('/carbon/query', summary='碳排数据查询（前端按层级/时间查询）')
async def carbon_query(request: Request):
    """
    转发算法 POST /api/v1/carbon/query。
    body: {"level": "workshop", "node_id": "WS-01",
           "start_time": "2026-08-15T00:00:00", "end_time": "2026-08-22T00:00:00"}
    注意：时间必须 ISO 8601 带 T，否则算法返回 422。
    """
    body = await passthrough_body(request)
    return call_algo('/carbon/query', method='POST', json_body=body)


@router.post('/traceability/report', summary='溯源报告（前端点击设备时触发）')
async def traceability_report(request: Request):
    """
    转发算法 POST /api/v1/traceability/report。
    body: {"equipment_id": "I-9-01", "anomaly_time": "2026-08-21T14:30:00", "hours": 72}
    返回根因 root_causes / 72h 汇总 / 改进建议 recommendation。
    """
    body = await passthrough_body(request)
    return call_algo('/traceability/report', method='POST', json_body=body)


@router.post('/strategy/generate', summary='AI 降碳方案（溯源结果页底部触发）')
async def strategy_generate(request: Request):
    """
    转发算法 POST /api/v1/strategy/generate。
    body: {"equipment_id": "I-9-01",
           "analysis_result": {...}  ← 可选，整段传溯源报告结果可做精准匹配}
    返回三类方案（设备运维/生产排班/工艺优化），已按投入产出比排序。
    """
    body = await passthrough_body(request)
    return call_algo('/strategy/generate', method='POST', json_body=body)


# ============================================================
# 探活
# ============================================================
@router.get('/health', summary='后端探活（同时探测算法可达性）')
async def health():
    """
    后端自身健康 + 顺带探测算法服务是否可达（联调排查第一条命令）。
    返回 backend: ok / algorithm: ok|unreachable。
    """
    algo_resp = call_algo('/health')
    algo_ok = algo_resp.get('code') == 200 or (
        isinstance(algo_resp, dict) and algo_resp.get('status') == 'healthy'
    )
    return {
        'backend': 'ok',
        'algorithm': 'ok' if algo_ok else 'unreachable',
        'algorithm_detail': algo_resp,
    }
