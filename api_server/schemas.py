"""
schemas —— 请求/响应数据模型

【这是与后端对接的核心契约】所有字段名、类型、单位都严格定义在这里，
后端同学联调时直接按这些 schema 构造请求/解析响应。

【单位约定】
    时间        ISO 8601 字符串，如 '2026-08-21T14:30:00'
    能耗        kWh
    功率        kW
    碳排        kgCO2
    碳排强度    kgCO2/件
    温度        ℃
    负载率      0-1（小数）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# 通用响应包装
# ============================================================
class APIResponse(BaseModel):
    """统一响应格式：code=200 表示成功，否则给出 message"""
    code: int = Field(200, description='状态码，200=成功，500=服务内部错误')
    message: str = Field('success', description='消息（失败时含错误信息）')
    data: Optional[Any] = Field(None, description='业务数据')


# ============================================================
# 碳排查询相关
# ============================================================
class CarbonQueryRequest(BaseModel):
    level: str = Field(..., description='聚合层级：factory/workshop/equipment/team')
    node_id: Optional[str] = Field(None, description='节点ID，factory 时忽略')
    start_time: datetime = Field(..., description='起始时间（ISO 8601）')
    end_time: datetime = Field(..., description='结束时间（ISO 8601）')


class CarbonEmissionData(BaseModel):
    node_id: str
    node_name: str
    carbon_emission: float = Field(..., description='碳排放量 (kgCO2)')
    energy_consumption: float = Field(..., description='能耗 (kWh)')
    carbon_intensity: Optional[float] = Field(None, description='碳排强度')
    percentage: Optional[float] = Field(None, description='占比 (%)')


# ============================================================
# 异常检测相关
# ============================================================
class AnomalyDetectRequest(BaseModel):
    equipment_id: str = Field(..., description='设备 ID，如 I-9-01')
    sequence_data: List[List[float]] = Field(
        ...,
        description='60×8 的时序数据矩阵（已归一化，由后端用训练 scaler 处理）',
    )


class AnomalyDetectResponse(BaseModel):
    """
    2026-08-30 按实际返回对齐：
        - 补充 equipment_name / threshold_type / should_alert（接口实际返回，后端直接可用）
        - threshold_type 取值：lstm(已训练) / fallback(未训练兜底) / adaptive / fixed
    """
    is_anomaly: bool
    reconstruction_error: float
    threshold: float
    severity: str = Field(..., description='high/medium/low/normal')
    anomaly_score: float
    equipment_id: str
    equipment_name: Optional[str] = Field(None, description='设备名称，如"电芯烘烤炉"')
    timestamp: datetime
    threshold_type: str = Field('adaptive', description='阈值来源：lstm/fallback/adaptive/fixed')
    should_alert: bool = Field(False, description='是否应推送告警（已含10分钟冷却控制）')
    feature_contributions: Optional[List[Dict[str, Any]]] = Field(
        None,
        description='可解释性：逐特征重建误差贡献（降序 top-N），每项含 feature/feature_name/reconstruction_error/contribution',
    )


# ============================================================
# 溯源相关
# ============================================================
class TraceabilityRequest(BaseModel):
    equipment_id: str = Field(..., description='设备 ID')
    anomaly_time: datetime = Field(..., description='异常发生时间（ISO 8601）')
    hours: int = Field(72, description='回溯小时数，默认 72h')


# ============================================================
# 降碳方案相关
# ============================================================
class StrategyRequest(BaseModel):
    equipment_id: str = Field(..., description='设备 ID')
    analysis_result: Optional[Dict[str, Any]] = Field(
        None,
        description='溯源结果（来自 /api/v1/traceability/report），不传则用默认模板',
    )


class StrategyItem(BaseModel):
    """
    2026-08-30 按实际返回对齐：
        - 原 target 必填字段拆为 target_equipment（设备方案）/ target_workshop（车间方案）
        - 补充 workshop_id / equipment_type / equipment_count / constraints 可选字段
    """
    strategy_type: str = Field(..., description='equipment_maintenance/production_scheduling/process_optimization')
    title: str
    actions: List[str]
    estimated_energy_saving: str = Field(..., description='估算节能量（如 15.2%）')
    estimated_carbon_reduction: str = Field(..., description='估算降碳量（如 23.8 kgCO2/天）')
    estimated_cost_saving: str = Field(..., description='估算月度成本节约（如 ¥6,800/月）')
    investment: str = Field(..., description='所需投资')
    payback_period: str = Field(..., description='回收期')
    priority: str = Field(..., description='high/medium/low')
    # 设备类方案字段（equipment_maintenance / process_optimization）
    target_equipment: Optional[str] = Field(None, description='目标设备ID，如 I-9-01')
    target_equipment_name: Optional[str] = Field(None, description='目标设备名称')
    workshop_id: Optional[str] = Field(None, description='所属车间')
    equipment_type: Optional[str] = Field(None, description='设备类型标识')
    # 车间类方案字段（production_scheduling）
    target_workshop: Optional[str] = Field(None, description='目标车间，如 WS-02（电芯化成车间）')
    equipment_count: Optional[int] = Field(None, description='车间方案涉及的设备数')
    constraints: Optional[str] = Field(None, description='方案约束条件（如工艺要求）')


# ============================================================
# 设备实时数据相关
# ============================================================
class EquipmentRealtimeData(BaseModel):
    equipment_id: str
    equipment_name: str
    equipment_type: str
    workshop_id: Optional[str] = None
    timestamp: datetime
    power: float = Field(..., description='有功功率 (kW)')
    load_rate: float = Field(..., description='负载率 (0-1)')
    carbon_emission: float = Field(..., description='实时碳排 (kgCO2/min)')
    temperature: float = Field(..., description='设备温度 (℃)')
    status: int = Field(..., description='1=运行, 0=停机, 2=待机')
    is_anomaly: bool = Field(False, description='当前是否异常')


class EquipmentListItem(BaseModel):
    equipment_id: str
    equipment_name: str
    equipment_type: str
    workshop_id: str
    team_id: str
    rated_power: float
    category: str
