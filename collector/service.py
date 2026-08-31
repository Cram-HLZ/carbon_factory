"""
service —— 采集入写服务

将 MES/EMS/PLC 数据写入 time_series_data 表，核心方法：

    write_batch(rows)   批量写入（按 (equipment_id, timestamp) 做 upsert，
                        已存在则更新，不存在则新增），返回 inserted/updated/total

碳排核算：
    carbon_emission(kgCO2/min) = power(kW) × (1/60 h) × 电力碳排因子(kgCO2/kWh)
    缺省因子取 config.CARBON_FACTORS['electricity']（0.5810，与碳排核算器一致）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from config.settings import CARBON_FACTORS
from database.database import SessionLocal
from database.models import TimeSeriesData


class IngestionService:
    """数据入写服务"""

    def __init__(self, carbon_factor: Optional[float] = None):
        self.carbon_factor = (
            carbon_factor if carbon_factor is not None else CARBON_FACTORS['electricity']
        )

    # ---------------- 碳排核算 ----------------
    def compute_carbon(self, power: float) -> float:
        """按功率核算每分钟碳排 (kgCO2/min)"""
        return round(float(power) / 60.0 * self.carbon_factor, 4)

    # ---------------- 单条写入 ----------------
    def write_reading(
        self,
        equipment_id: str,
        timestamp,
        power: float,
        temperature: Optional[float] = None,
        vibration: Optional[float] = None,
        load_rate: Optional[float] = None,
        carbon_emission: Optional[float] = None,
    ) -> Dict[str, int]:
        """写入单条读数（便捷入口，内部走 write_batch）。"""
        return self.write_batch(
            [
                {
                    'equipment_id': equipment_id,
                    'timestamp': timestamp,
                    'power': power,
                    'temperature': temperature,
                    'vibration': vibration,
                    'load_rate': load_rate,
                    'carbon_emission': carbon_emission,
                }
            ]
        )

    # ---------------- 批量写入 ----------------
    def write_batch(self, rows: List[dict]) -> Dict[str, int]:
        """
        批量写入，按 (equipment_id, timestamp) 唯一约束做 upsert。

        Parameters
        ----------
        rows : list[dict]，每条需含 equipment_id / timestamp / power，
               可选 temperature / vibration / load_rate / carbon_emission

        Returns
        -------
        {'inserted': int, 'updated': int, 'total': int}
        """
        if not rows:
            return {'inserted': 0, 'updated': 0, 'total': 0}

        # 归一化为标准 dict，缺省碳排按功率核算
        normalized: List[dict] = []
        for r in rows:
            power = float(r.get('power') or 0.0)
            carbon = r.get('carbon_emission')
            if carbon is None:
                carbon = self.compute_carbon(power)
            normalized.append(
                {
                    'equipment_id': str(r['equipment_id']),
                    'timestamp': self._norm_ts(r.get('timestamp')),
                    'power': power,
                    'temperature': self._opt_float(r.get('temperature')),
                    'vibration': self._opt_float(r.get('vibration')),
                    'load_rate': self._opt_float(r.get('load_rate')),
                    'carbon_emission': float(carbon),
                }
            )

        inserted = updated = 0
        with SessionLocal() as db:
            eq_ids = {n['equipment_id'] for n in normalized}
            timestamps = {n['timestamp'] for n in normalized}

            # 一次性查出已存在的行，按 (equipment_id, timestamp) 建索引
            existing: Dict[tuple, TimeSeriesData] = {}
            for row in db.query(TimeSeriesData).filter(
                TimeSeriesData.equipment_id.in_(eq_ids),
                TimeSeriesData.timestamp.in_(timestamps),
            ).all():
                existing[(row.equipment_id, row.timestamp)] = row

            for n in normalized:
                key = (n['equipment_id'], n['timestamp'])
                obj = existing.get(key)
                if obj is None:
                    db.add(TimeSeriesData(**n))
                    inserted += 1
                else:
                    obj.power = n['power']
                    obj.temperature = n['temperature']
                    obj.vibration = n['vibration']
                    obj.load_rate = n['load_rate']
                    obj.carbon_emission = n['carbon_emission']
                    updated += 1
            db.commit()

        return {'inserted': inserted, 'updated': updated, 'total': inserted + updated}

    # ---------------- 工具 ----------------
    @staticmethod
    def _norm_ts(ts):
        """把 pandas Timestamp / str 统一为 datetime"""
        if ts is None:
            return None
        if hasattr(ts, 'to_pydatetime'):  # pandas.Timestamp
            return ts.to_pydatetime()
        if isinstance(ts, str):
            return datetime.fromisoformat(ts)
        return ts

    @staticmethod
    def _opt_float(value) -> Optional[float]:
        """可选浮点字段：None / NaN → None"""
        if value is None:
            return None
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        if f != f:  # NaN
            return None
        return f