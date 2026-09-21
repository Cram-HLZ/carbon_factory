"""
archive_service —— 历史数据归档服务

分层存储：分钟级原始数据仅保留近 retention_raw_days 天（见 config.ARCHIVE_CONFIG），
过期后按「小时 / 天」粒度降采样为统计桶写入 time_series_archive，原始分钟行随后删除，
归档数据保留 retention_archive_years 年（默认 3 年），超出后清理。

归档流程（run_archive，幂等，可定时/手动触发）：
    1. 清理超过 3 年的归档桶
    2. 把 < cutoff 的分钟数据聚合为 hour / day 两类桶，upsert 进归档表
    3. 删除 < cutoff 的原始分钟行

聚合口径：
    power_avg / power_max      功率均值 / 峰值（kW）
    load_rate_avg              负载率均值（0-1）
    temperature_avg / vibration_avg   温度均值 / 振动均值
    carbon_sum                 碳排累计（kgCO2）
    energy_sum                 能耗累计（kWh）= Σ power / 60（每条代表 1 分钟）
    sample_count               桶内分钟采样点数
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from sqlalchemy import func

from config.settings import ARCHIVE_CONFIG
from database.database import SessionLocal
from database.models import TimeSeriesArchive, TimeSeriesData

# 聚合桶的 strftime 模板与回解析模板（SQLite 方言；切换 MySQL 时替换为 DATE_FORMAT）
_FMT = {
    'hour': '%Y-%m-%d %H:00:00',
    'day': '%Y-%m-%d 00:00:00',
}
_PARSE_FMT = '%Y-%m-%d %H:%M:%S'

# 归档表可更新/覆盖的聚合字段
_AGG_FIELDS = [
    'power_avg', 'power_max', 'load_rate_avg', 'temperature_avg',
    'vibration_avg', 'carbon_sum', 'energy_sum', 'sample_count',
]


def _f(v) -> float:
    """None → None，其余转 float"""
    return None if v is None else float(v)


def _archive_granularity(db, cutoff: datetime, granularity: str) -> Tuple[int, int, int]:
    """把 < cutoff 的分钟数据按 granularity 聚合，upsert 进归档表，返回 (inserted, updated, total)"""
    bucket = func.strftime(_FMT[granularity], TimeSeriesData.timestamp)
    agg = (
        db.query(
            TimeSeriesData.equipment_id.label('equipment_id'),
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
        .filter(TimeSeriesData.timestamp < cutoff)
        .group_by(TimeSeriesData.equipment_id, bucket)
        .all()
    )

    new_rows: List[dict] = []
    for r in agg:
        new_rows.append({
            'equipment_id': r.equipment_id,
            'bucket_start': datetime.strptime(r.bucket_start, _PARSE_FMT),
            'granularity': granularity,
            'power_avg': _f(r.power_avg),
            'power_max': _f(r.power_max),
            'load_rate_avg': _f(r.load_rate_avg),
            'temperature_avg': _f(r.temperature_avg),
            'vibration_avg': _f(r.vibration_avg),
            'carbon_sum': float(r.carbon_sum or 0.0),
            'energy_sum': float(r.energy_sum or 0.0),
            'sample_count': int(r.sample_count or 0),
        })

    if not new_rows:
        return 0, 0, 0

    # 仅按本次聚合涉及的键做存在性查询（避免加载整张归档表），做 upsert
    eq_ids = {n['equipment_id'] for n in new_rows}
    bucket_starts = {n['bucket_start'] for n in new_rows}
    existing: Dict[tuple, TimeSeriesArchive] = {}
    for row in (
        db.query(TimeSeriesArchive)
        .filter(
            TimeSeriesArchive.granularity == granularity,
            TimeSeriesArchive.equipment_id.in_(eq_ids),
            TimeSeriesArchive.bucket_start.in_(bucket_starts),
        )
        .all()
    ):
        existing[(row.equipment_id, row.bucket_start, row.granularity)] = row

    inserted = updated = 0
    for n in new_rows:
        key = (n['equipment_id'], n['bucket_start'], n['granularity'])
        obj = existing.get(key)
        if obj is None:
            db.add(TimeSeriesArchive(**n))
            inserted += 1
        else:
            for f in _AGG_FIELDS:
                setattr(obj, f, n[f])
            updated += 1
    return inserted, updated, len(new_rows)


def run_archive() -> Dict[str, int]:
    """执行一轮归档，返回各阶段统计（幂等）"""
    cfg = ARCHIVE_CONFIG
    cutoff = datetime.now() - timedelta(days=cfg['retention_raw_days'])
    prune_before = datetime.now() - timedelta(days=cfg['retention_archive_years'] * 365)

    with SessionLocal() as db:
        # 1. 清理超过 3 年的归档桶
        pruned = (
            db.query(TimeSeriesArchive)
            .filter(TimeSeriesArchive.bucket_start < prune_before)
            .delete(synchronize_session=False)
        )

        # 2. 分钟数据降采样为 hour / day 两类桶（须在删除原始行之前完成）
        hour_ins, hour_upd, hour_total = _archive_granularity(db, cutoff, 'hour')
        day_ins, day_upd, day_total = _archive_granularity(db, cutoff, 'day')

        # 3. 删除已归档的原始分钟行
        raw_deleted = (
            db.query(TimeSeriesData)
            .filter(TimeSeriesData.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()

    return {
        'archive_pruned': pruned,
        'hour_buckets': hour_total,
        'hour_inserted': hour_ins,
        'hour_updated': hour_upd,
        'day_buckets': day_total,
        'day_inserted': day_ins,
        'day_updated': day_upd,
        'raw_deleted': raw_deleted,
        'cutoff': cutoff.isoformat(),
    }