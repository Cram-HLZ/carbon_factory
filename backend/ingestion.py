"""
ingestion —— 数据采集接口（后端路由，阶段2）

提供 MES / EMS / PLC 数据入站入口，以及模拟采集触发入口：

    POST /api/ingest/sensor            单条读数写入
    POST /api/ingest/batch             批量读数写入
    POST /api/ingest/simulate/backfill 触发历史回填（模拟 MES/EMS 批量同步）
    POST /api/ingest/simulate/live     触发实时采集（模拟 PLC 在线推送）

说明：真实 MES/EMS/PLC 部署时，由其网关/中间件调用本组接口推送数据，
入写服务统一落表并核算碳排，实现「采集 → 数据库」链路。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from collector.schemas import IngestResult, SensorBatch, SensorReading
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