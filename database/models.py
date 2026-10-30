"""
models —— SQLAlchemy ORM 模型定义（6 张表）

字段严格对齐《backend_integration_checklist.html》阶段2「数据库设计与搭建」：
    设备表    equipment        ID / 名称 / 类型 / 车间 / 班组 / 额定功率
    时序表    time_series_data 功率 / 温度 / 振动 / 负载率 / 碳排（按分钟入库）
    归档表    time_series_archive 分钟级数据降采样聚合（小时/天），支撑 3 年历史查询
    告警表    alarm_record     设备ID / 时间 / 严重度 / 根因 / 处理状态
    方案表    strategy         设备ID / 方案类型 / 节能估算 / 优先级
    用户表    user             账号 / 角色 / 密码哈希 / 权限

字段取值约定：
    - severity      ：critical / high / medium / low
    - status        ：pending / processing / resolved
    - strategy_type ：equipment_maintenance / production_scheduling / process_optimization
    - priority      ：high / medium / low
    - role          ：management（管理层）/ operator（运维岗）/ it_admin（IT管理员）
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


class Equipment(Base):
    """设备表：设备主数据（来自 config.EQUIPMENT_LIST / EQUIPMENT_TYPES）"""

    __tablename__ = 'equipment'

    equipment_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment='设备唯一编号，如 I-9-01')
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment='设备名称')
    equipment_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment='设备类型标识')
    workshop_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment='所属车间 WS-01~WS-05')
    team_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment='所属班组 TEAM-A/B/C')
    rated_power: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment='额定功率(kW)')


class TimeSeriesData(Base):
    """时序数据表：设备运行参数，按分钟入库"""

    __tablename__ = 'time_series_data'
    __table_args__ = (
        UniqueConstraint('equipment_id', 'timestamp', name='uq_ts_equipment_time'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(
        String(32), ForeignKey('equipment.equipment_id'), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment='时间戳（分钟级）')
    power: Mapped[float] = mapped_column(Float, nullable=True, comment='有功功率(kW)')
    temperature: Mapped[float] = mapped_column(Float, nullable=True, comment='温度(℃)')
    vibration: Mapped[float] = mapped_column(Float, nullable=True, comment='振动(mm/s)')
    load_rate: Mapped[float] = mapped_column(Float, nullable=True, comment='负载率(0-1)')
    carbon_emission: Mapped[float] = mapped_column(Float, nullable=True, comment='碳排放(kgCO2)')


class TimeSeriesArchive(Base):
    """时序归档表：分钟级数据降采样聚合，支撑 3 年历史高效查询

    原始分钟数据在 time_series_data 中仅保留近 N 天（见 config.ARCHIVE_CONFIG），
    过期后按「小时 / 天」粒度的统计桶归档到本表，原始分钟行被删除以控制库容。
    查询时优先读原始表，跨期自动回落到归档表。
    """

    __tablename__ = 'time_series_archive'
    __table_args__ = (
        UniqueConstraint('equipment_id', 'bucket_start', 'granularity', name='uq_arch_equip_bucket_gran'),
        Index('ix_arch_bucket_start', 'bucket_start'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(
        String(32), ForeignKey('equipment.equipment_id'), nullable=False, index=True
    )
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment='聚合桶起始时间')
    granularity: Mapped[str] = mapped_column(String(8), nullable=False, default='hour', comment='hour / day')
    power_avg: Mapped[float] = mapped_column(Float, nullable=True, comment='平均功率(kW)')
    power_max: Mapped[float] = mapped_column(Float, nullable=True, comment='峰值功率(kW)')
    load_rate_avg: Mapped[float] = mapped_column(Float, nullable=True, comment='平均负载率(0-1)')
    temperature_avg: Mapped[float] = mapped_column(Float, nullable=True, comment='平均温度(℃)')
    vibration_avg: Mapped[float] = mapped_column(Float, nullable=True, comment='平均振动(mm/s)')
    carbon_sum: Mapped[float] = mapped_column(Float, nullable=True, comment='碳排累计(kgCO2)')
    energy_sum: Mapped[float] = mapped_column(Float, nullable=True, comment='能耗累计(kWh)')
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment='桶内分钟采样点数')


class AlarmRecord(Base):
    """告警记录表：异常告警"""

    __tablename__ = 'alarm_record'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(
        String(32), ForeignKey('equipment.equipment_id'), nullable=False, index=True
    )
    alarm_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment='告警时间')
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default='medium', comment='严重度 critical/high/medium/low')
    root_cause: Mapped[str] = mapped_column(String(255), nullable=True, comment='根因描述')
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='pending', comment='处理状态 pending/processing/resolved')
    feature_contributions: Mapped[List] = mapped_column(
        JSON, nullable=True, comment='可解释性：top 特征贡献（feature/feature_name/contribution）'
    )


class Strategy(Base):
    """方案表：降碳方案（来自碳排策略引擎）"""

    __tablename__ = 'strategy'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(
        String(32), ForeignKey('equipment.equipment_id'), nullable=False, index=True
    )
    strategy_type: Mapped[str] = mapped_column(String(32), nullable=False, comment='方案类型 运维/排班/工艺')
    estimated_energy_saving: Mapped[str] = mapped_column(String(32), nullable=True, comment='节能估算，如 15.2%')
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default='medium', comment='优先级 high/medium/low')


class User(Base):
    """用户表：账号 / 角色 / 密码哈希 / 权限 / 数据范围（组织级隔离）"""

    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment='账号')
    role: Mapped[str] = mapped_column(String(32), nullable=False, default='operator', comment='角色 management/operator/it_admin')
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment='密码哈希')
    permissions: Mapped[List] = mapped_column(JSON, nullable=True, comment='权限列表（JSON）')
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default='all', comment='数据范围 all/factory/workshop')
    scope_value: Mapped[str] = mapped_column(String(32), nullable=True, comment='范围值：工厂code(F-01) 或 车间id(WS-01)')


class MrvReport(Base):
    """MRV 核查报告台账：记录每期报告的核算结果与核查留痕（监测-报告-核查闭环）"""

    __tablename__ = 'mrv_report'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment='报告期，如 2026-09')
    scope1_emission: Mapped[float] = mapped_column(Float, nullable=True, comment='范围1直接排放(kgCO2)')
    scope2_emission: Mapped[float] = mapped_column(Float, nullable=True, comment='范围2外购电力间接(kgCO2)')
    scope3_emission: Mapped[float] = mapped_column(Float, nullable=True, comment='范围3其他间接(kgCO2)')
    data_quality_score: Mapped[float] = mapped_column(Float, nullable=True, comment='数据质量评分 0-100')
    methodology: Mapped[str] = mapped_column(String(128), nullable=True, comment='核算方法学')
    uncertainty: Mapped[str] = mapped_column(String(255), nullable=True, comment='不确定性说明')
    verifier: Mapped[str] = mapped_column(String(64), nullable=True, comment='核查人账号')
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default='draft', comment='核查状态 draft/self_audited/verified')
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment='核查时间')
    generated_by: Mapped[str] = mapped_column(String(64), nullable=True, comment='生成人账号')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment='生成时间')