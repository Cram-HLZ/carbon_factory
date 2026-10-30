"""
collector —— 数据采集层（对接 MES / EMS / PLC 传感器）

职责：
    把来自 MES（生产/排班）、EMS（能耗）、PLC（实时工况）的数据，
    经统一入写服务（IngestionService）写入 time_series_data 表，
    并在缺省时按功率自动核算碳排（power × 1/60h × 电力碳排因子）。

组件：
    schemas    入站数据校验模型（Pydantic）
    service    入写服务（含碳排核算 + upsert）
    simulator  模拟采集器（无真实 MES/EMS/PLC 时，生成分钟级数据回填/实况写入）
"""

from collector.service import IngestionService
from collector.schemas import SensorReading, SensorBatch, IngestResult, GatewayIngestRequest
from collector.gateway import EdgeGateway

__all__ = [
    'IngestionService',
    'SensorReading',
    'SensorBatch',
    'IngestResult',
    'GatewayIngestRequest',
    'EdgeGateway',
]