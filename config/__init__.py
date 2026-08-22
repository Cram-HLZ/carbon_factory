"""
config —— 全局配置包

后端同学注意：
    本包只暴露常量，不执行任何副作用计算，可在任意位置 import。
    所有硬编码参数（碳排因子、模型超参、设备清单、车间/班组）都集中在这里，
    方便后续接入真实数据时只改一处即可。
"""

from config.settings import (
    settings,
    CARBON_FACTORS,
    MODEL_CONFIG,
    THRESHOLD_CONFIG,
    EQUIPMENT_TYPES,
    EQUIPMENT_LIST,
    WORKSHOPS,
    TEAMS,
    HIERARCHY_LEVELS,
    API_CONFIG,
    BASE_DIR,
    DATA_DIR,
    RAW_DATA_DIR,
    PROCESS_DATA_DIR,
    OUTPUT_DIR,
    MODEL_WEIGHT_DIR,
    LOG_DIR,
    CHART_DIR,
)

__all__ = [
    'settings',
    'CARBON_FACTORS',
    'MODEL_CONFIG',
    'THRESHOLD_CONFIG',
    'EQUIPMENT_TYPES',
    'EQUIPMENT_LIST',
    'WORKSHOPS',
    'TEAMS',
    'HIERARCHY_LEVELS',
    'API_CONFIG',
    'BASE_DIR',
    'DATA_DIR',
    'RAW_DATA_DIR',
    'PROCESS_DATA_DIR',
    'OUTPUT_DIR',
    'MODEL_WEIGHT_DIR',
    'LOG_DIR',
    'CHART_DIR',
]
