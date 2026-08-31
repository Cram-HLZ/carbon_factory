"""
schemas —— 采集入站数据模型（对接 MES / EMS / PLC 的接口契约）

字段说明：
    equipment_id   设备编号（对应 equipment 表主键，如 I-9-01）
    timestamp      采样时间（分钟级，ISO 8601）
    power          有功功率(kW)，来自 EMS
    temperature    温度(℃)，来自 PLC 传感器
    vibration      振动(mm/s)，来自 PLC 传感器
    load_rate      负载率(0-1)，来自 PLC / MES
    carbon_emission 碳排(kgCO2/min)，可选；缺省由入写服务按功率核算
    source         数据来源标识：mes / ems / plc / sensor（仅作链路追踪，不落库）
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SensorReading(BaseModel):
    """单条传感器/能耗读数"""

    equipment_id: str = Field(..., description='设备编号，如 I-9-01')
    timestamp: datetime = Field(..., description='采样时间（分钟级）')
    power: float = Field(..., description='有功功率(kW)')
    temperature: Optional[float] = Field(None, description='温度(℃)')
    vibration: Optional[float] = Field(None, description='振动(mm/s)')
    load_rate: Optional[float] = Field(None, ge=0, le=1.5, description='负载率(0-1)')
    carbon_emission: Optional[float] = Field(None, description='碳排(kgCO2/min)，缺省按功率计算')
    source: str = Field('sensor', description='数据来源：mes/ems/plc/sensor')


class SensorBatch(BaseModel):
    """批量读数（EMS/MES 定时同步常用）"""

    readings: List[SensorReading] = Field(..., min_length=1, description='读数列表')
    source: str = Field('batch', description='批量来源标识')


class IngestResult(BaseModel):
    """写入结果统计"""

    inserted: int = Field(0, description='新增条数')
    updated: int = Field(0, description='更新条数')
    total: int = Field(0, description='处理总条数')