"""
ingestion —— 数据采集接口（后端路由，阶段2）

提供 MES / EMS / PLC 数据入站入口，以及模拟采集触发入口：

    POST /api/ingest/sensor            单条读数写入
    POST /api/ingest/batch             批量读数写入
    POST /api/ingest/gateway           边缘网关协议注入（Modbus / OPC UA / MQTT 归一化入写）
    GET  /api/ingest/submeter/summary  分项计量汇总（照明/空调/动力/产线）
    GET  /api/ingest/submeter/resolve  设备 → 分项
    POST /api/ingest/simulate/backfill 触发历史回填（模拟 MES/EMS 批量同步）
    POST /api/ingest/simulate/live     触发实时采集（模拟 PLC 在线推送）

说明：真实 MES/EMS/PLC 部署时，由其网关/中间件调用本组接口推送数据；
现场 PLC / 传感器也可经 EdgeGateway（Modbus/OPC UA/MQTT）主动采集后统一入写。
入写服务统一落表并核算碳排，实现「采集 → 数据库」链路。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from collector.schemas import GatewayIngestRequest, IngestResult, SensorBatch, SensorReading
from collector.service import IngestionService

router = APIRouter(prefix='/api/ingest', tags=['数据采集'])

_service = IngestionService()


@router.post('/sensor', response_model=IngestResult, summary='单条传感器读数写入')
async def ingest_sensor(reading: SensorReading):
    """单条实时读数（PLC/传感器在线推送）"""
    return _service.write_batch([reading.model_dump()])


@router.post('/batch', response_model=IngestResult, summary='批量读数写入')
async def ingest_batch(batch: SensorBatch):
    """批量读数（EMS/MES 定时同步，如每分钟同步一批设备）"""
    return _service.write_batch([r.model_dump() for r in batch.readings])


@router.post('/gateway', summary='边缘网关协议注入（Modbus / OPC UA / MQTT 归一化入写）')
async def ingest_gateway(req: GatewayIngestRequest):
    """
    协议无关入站：接受网关转发的原始协议数据，归一化后写库。

    modbus → raw={'registers':[120,400,15,780]}（顺序保持寄存器）
    opcua  → raw={'Power':12.3,'Temperature':40.1,...}（节点值）
    mqtt   → raw={'power':12.3,'temperature':40.1,...}（JSON）
    """
    from collector.gateway import EdgeGateway

    try:
        return EdgeGateway().ingest_reading(req.protocol, req.equipment_id, req.raw, req.timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        # 协议客户端库未安装 → 501 提示，不阻断主流程
        raise HTTPException(status_code=501, detail=str(exc))


@router.get('/submeter/summary', summary='分项计量汇总（照明/空调/动力/产线）')
async def get_submeter_summary(
    start_time: datetime = Query(None, description='起始时间（ISO 8601，可选）'),
    end_time: datetime = Query(None, description='结束时间（ISO 8601，可选）'),
):
    from collector.submeter import submeter_summary

    return submeter_summary(start_time, end_time)


@router.get('/submeter/resolve', summary='设备 → 分项')
async def get_submeter(equipment_id: str = Query(..., description='设备编号，如 I-9-01')):
    from collector.submeter import resolve_submeter

    return {'equipment_id': equipment_id, 'submeter': resolve_submeter(equipment_id)}


@router.post('/simulate/backfill', summary='模拟：历史数据回填')
async def simulate_backfill(days: int = Query(7, ge=1, le=30, description='回填最近 N 天')):
    """无真实系统时，用现有样本生成器回填历史数据到数据库"""
    from collector.simulator import backfill_historical

    result = backfill_historical(days=days)
    return {'days': days, **result}


@router.post('/simulate/live', summary='模拟：实时采集最近 N 分钟')
async def simulate_live(minutes: int = Query(1, ge=1, le=60, description='最近 N 分钟')):
    """模拟 PLC 在线推送最近 N 分钟的实时工况"""
    from collector.simulator import collect_live

    result = collect_live(minutes=minutes)
    return {'minutes': minutes, **result}