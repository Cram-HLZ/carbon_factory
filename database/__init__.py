"""
database —— 数据库层（阶段2）

基于 SQLAlchemy 2.0 ORM，默认 SQLite（可切换到 MySQL，见 database.database）。
包含 5 张表：
    1. equipment         设备表
    2. time_series_data  时序数据表（按分钟入库）
    3. alarm_record      告警记录表
    4. strategy          方案表
    5. user              用户表

【初始化方式】（在项目根目录执行）
    python -m database.init_db        # 建库 + 建表 + 灌入设备表种子数据
"""

from database.models import (
    Base,
    Equipment,
    TimeSeriesData,
    AlarmRecord,
    Strategy,
    User,
)
from database.database import (
    engine,
    SessionLocal,
    get_db,
    init_database,
)

__all__ = [
    'Base',
    'Equipment',
    'TimeSeriesData',
    'AlarmRecord',
    'Strategy',
    'User',
    'engine',
    'SessionLocal',
    'get_db',
    'init_database',
]