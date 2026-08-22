"""
carbon_strategy —— 碳排核算与降碳策略包

包含：
    CarbonCalculator       : IPCC 因子核算 + 四级聚合（厂区/车间/设备/班组）
    equipment_models       : 设备机理模型（9类生产设备 + 3类公用动力）
    TraceabilityAnalyzer   : 72h 溯源 + 根因分析
    CarbonStrategyEngine   : 降碳方案生成（设备运维/生产排班/工艺优化三类）

后端同学：
    - 实时碳排数据：GET /api/v1/carbon/overview 调 CarbonCalculator.aggregate_factory
    - 异常溯源：POST /api/v1/traceability/report 调 TraceabilityAnalyzer
    - 降碳方案：POST /api/v1/strategy/generate 调 CarbonStrategyEngine
"""

from carbon_strategy.carbon_calculator import CarbonCalculator
from carbon_strategy.equipment_models import (
    equipment_health_score,
    estimate_energy_savings,
)
from carbon_strategy.traceability import TraceabilityAnalyzer
from carbon_strategy.strategy_engine import CarbonStrategyEngine

__all__ = [
    'CarbonCalculator',
    'TraceabilityAnalyzer',
    'CarbonStrategyEngine',
    'equipment_health_score',
    'estimate_energy_savings',
]
