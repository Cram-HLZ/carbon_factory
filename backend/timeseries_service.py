"""
timeseries_service —— 高效时序查询服务

对上层提供统一的单设备时序查询入口，透明地跨「原始表 + 归档表」读取：

    - minute 粒度：直接读 time_series_data（仅保留近 retention_raw_days 天）
    - hour  / day 粒度：读 time_series_archive（预聚合，覆盖 3 年）；
      最近 retention_raw_days 天的部分尚未归档，则对原始分钟数据实时聚合并与之合并
    - auto（默认）：按查询跨度自动选粒度（≤2天人 → minute，≤90天 → hour，更久 → day），
      避免一次返回海量点

输出为统一结构（供前端图表 / 导出直接消费）：
    {
        'equipment_id', 'granularity', 'start', 'end', 'count',
        'retention_raw_days', 'points': [ {timestamp, power, power_max, load_rate,
        temperature, vibration, carbon_emission, energy, sample_count}, ... ]
    }
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from config.settings import ARCHIVE_CONFIG
from database.models import TimeSeriesArchive, TimeSeriesData

_FMT = {
    'hour': '%Y-%m-%d %H:00:00',
    'day': '%Y-%m-%d 00:00:00',
}
_PARSE_FMT = '%Y-%m-%d %H:%M:%S'


# ============================================================
# 粒度选择
# ============================================================
def resolve_granularity(start: datetime, end: datetime, requested: str) -> str:
    if requested in ('minute', 'hour', 'day'):
        return requested
    span_days = (end - start).total_seconds() / 86400.0
    if span_days <= 2:
        return 'minute'
    if span_days <= 90:
        return 'hour'
    return 'day'


# ============================================================
# 数据读取（原始 / 归档）
# ============================================================
def _mk_point(
    ts: datetime,
    power: Optional[float],
    power_max: Optional[float],
    load_rate: Optional[float],
    temperature: Optional[float],
    vibration: Optional[float],
    carbon: float,
    energy: float,
    sample_count: int,
) -> dict:
    return {
        'timestamp': ts.isoformat(),
        'power': power,
        'power_max': power_max,
        'load_rate': load_rate,
        'temperature': temperature,
        'vibration': vibration,
        'carbon_emission': carbon,
        'energy': energy,
        'sample_count': sample_count,
    }


def _raw_minute(db: Session, equipment_id: str, start: datetime, end: datetime) -> List[dict]:
    rows = (
        db.query(TimeSeriesData)
        .filter(
            TimeSeriesData.equipment_id == equipment_id,
            TimeSeriesData.timestamp >= start,
            TimeSeriesData.timestamp < end,
        )
        .order_by(TimeSeriesData.timestamp.asc())
        .all()
    )
    pts: List[dict] = []
    for r in rows:
        power = float(r.power or 0.0)
        pts.append(_mk_point(
            r.timestamp, power, None, r.load_rate, r.temperature, r.vibration,
            float(r.carbon_emission or 0.0), power / 60.0, 1,
        ))
    return pts


def _raw_aggregated(db: Session, equipment_id: str, granularity: str, start: datetime, end: datetime) -> List[dict]:
    """对原始分钟数据按 granularity 实时聚合（覆盖尚未归档的近期窗口）"""
    bucket = func.strftime(_FMT[granularity], TimeSeriesData.timestamp)
    rows = (
        db.query(
            bucket.label('bucket_start'),
            func.avg(TimeSeriesData.power).label('power_avg'),
            func.max(TimeSeriesData.power).label('power_max'),
            func.avg(TimeSeriesData.load_rate).label('load_rate_avg'),
            func.avg(TimeSeriesData.temperature).label('temperature_avg'),
            func.avg(TimeSeriesData.vibration).label('vibration_avg'),
            func.coalesce(func.sum(TimeSeriesData.carbon_emission), 0.0).label('carbon_sum'),
            (func.coalesce(func.sum(TimeSeriesData.power), 0.0) / 60.0).label('energy_sum'),
            func.count(TimeSeriesData.id).label('sample_count'),
        )
        .filter(
            TimeSeriesData.equipment_id == equipment_id,
            TimeSeriesData.timestamp >= start,
            TimeSeriesData.timestamp < end,
        )
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )
    pts: List[dict] = []
    for r in rows:
        pts.append(_mk_point(
            datetime.strptime(r.bucket_start, _PARSE_FMT),
            r.power_avg, r.power_max, r.load_rate_avg, r.temperature_avg,
            r.vibration_avg, float(r.carbon_sum or 0.0), float(r.energy_sum or 0.0),
            int(r.sample_count or 0),
        ))
    return pts


def _archive_points(db: Session, equipment_id: str, granularity: str, start: datetime, end: datetime) -> List[dict]:
    rows = (
        db.query(TimeSeriesArchive)
        .filter(
            TimeSeriesArchive.equipment_id == equipment_id,
            TimeSeriesArchive.granularity == granularity,
            TimeSeriesArchive.bucket_start >= start,
            TimeSeriesArchive.bucket_start < end,
        )
        .order_by(TimeSeriesArchive.bucket_start.asc())
        .all()
    )
    pts: List[dict] = []
    for r in rows:
        pts.append(_mk_point(
            r.bucket_start, r.power_avg, r.power_max, r.load_rate_avg, r.temperature_avg,
            r.vibration_avg, float(r.carbon_sum or 0.0), float(r.energy_sum or 0.0),
            int(r.sample_count or 0),
        ))
    return pts


# ============================================================
# 对外查询入口
# ============================================================
def query_timeseries(
    db: Session,
    equipment_id: str,
    start: datetime,
    end: datetime,
    granularity: str = 'auto',
) -> dict:
    gran = resolve_granularity(start, end, granularity)
    cutoff = datetime.now() - timedelta(days=ARCHIVE_CONFIG['retention_raw_days'])

    if gran == 'minute':
        points = _raw_minute(db, equipment_id, start, end)
    else:
        points: List[dict] = []
        # 归档部分（跨期窗口的早期段）
        a_end = min(end, cutoff)
        if start < a_end:
            points.extend(_archive_points(db, equipment_id, gran, start, a_end))
        # 近期原始部分（尚未归档），实时聚合并与之合并
        r_start = max(start, cutoff)
        if r_start < end:
            points.extend(_raw_aggregated(db, equipment_id, gran, r_start, end))
        points.sort(key=lambda p: p['timestamp'])

    return {
        'equipment_id': equipment_id,
        'granularity': gran,
        'start': start.isoformat(),
        'end': end.isoformat(),
        'retention_raw_days': ARCHIVE_CONFIG['retention_raw_days'],
        'count': len(points),
        'points': points,
    }