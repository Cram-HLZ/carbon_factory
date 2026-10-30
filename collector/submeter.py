"""
submeter —— 分项计量（照明 / 空调 / 动力 / 产线）

补齐「无分项计量体系、无法做分项节能诊断」的短板：

    resolve_submeter(equipment_id)   把设备映射到分项（含 type 兜底 → 产线）
    submeter_summary(start, end)     按分项汇总累计能耗/碳排/功率均值/设备数

分项口径说明（按设备类型归类，见 config.settings.SUBMETER_MAP）：
    空调  冷水机组 chiller / 冷却风机 cooling_fan
    动力  空压机 compressor
    产线  其余生产/检测/加工/物流设备（默认）
    照明  预留（新增照明计量点后在 SUBMETER_MAP 启用）
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from config.settings import (
    EQUIPMENT_LIST,
    SUBMETER_CATEGORIES,
    SUBMETER_MAP,
)
from database.database import SessionLocal
from database.models import TimeSeriesData

# 每 1 分钟采样的能耗折算系数：kW × (1/60 h) = kWh
_MINUTES_TO_HOURS = 1.0 / 60.0


def resolve_submeter(equipment_id: str) -> str:
    """把设备映射到分项；无法识别时默认归入「产线」。"""
    info = EQUIPMENT_LIST.get(equipment_id)
    if info:
        etype = info.get('equipment_type')
        if etype and etype in SUBMETER_MAP:
            return SUBMETER_MAP[etype]
    return '产线'


def submeter_summary(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> Dict:
    """
    按分项汇总时间范围内的能耗与碳排。

    Returns
    -------
    {
      'start_time', 'end_time',
      'total': {'energy_kwh', 'carbon_kg', 'samples', 'devices'},
      'categories': [
        {'category','energy_kwh','carbon_kg','share_energy','share_carbon','samples','devices'}, ...
        # 按碳排降序
      ]
    }
    """
    with SessionLocal() as db:
        query = db.query(TimeSeriesData)
        if start_time is not None:
            query = query.filter(TimeSeriesData.timestamp >= start_time)
        if end_time is not None:
            query = query.filter(TimeSeriesData.timestamp <= end_time)

        agg: Dict[str, Dict] = {c: {
            'category': c, 'energy_kwh': 0.0, 'carbon_kg': 0.0,
            'samples': 0, 'devices': set(),
        } for c in SUBMETER_CATEGORIES}

        for row in query.yield_per(1000):
            cat = resolve_submeter(row.equipment_id)
            if cat not in agg:
                continue
            bucket = agg[cat]
            bucket['energy_kwh'] += (row.power or 0.0) * _MINUTES_TO_HOURS
            bucket['carbon_kg'] += (row.carbon_emission or 0.0)
            bucket['samples'] += 1
            bucket['devices'].add(row.equipment_id)

    total = {
        'energy_kwh': round(sum(b['energy_kwh'] for b in agg.values()), 4),
        'carbon_kg': round(sum(b['carbon_kg'] for b in agg.values()), 4),
        'samples': sum(b['samples'] for b in agg.values()),
        'devices': len({d for b in agg.values() for d in b['devices']}),
    }

    categories: List[Dict] = []
    for cat in SUBMETER_CATEGORIES:
        b = agg[cat]
        share_e = b['energy_kwh'] / total['energy_kwh'] if total['energy_kwh'] else 0.0
        share_c = b['carbon_kg'] / total['carbon_kg'] if total['carbon_kg'] else 0.0
        categories.append({
            'category': cat,
            'energy_kwh': round(b['energy_kwh'], 4),
            'carbon_kg': round(b['carbon_kg'], 4),
            'share_energy': round(share_e, 4),
            'share_carbon': round(share_c, 4),
            'samples': b['samples'],
            'devices': len(b['devices']),
        })
    categories.sort(key=lambda x: x['carbon_kg'], reverse=True)

    return {
        'start_time': start_time.isoformat() if start_time else None,
        'end_time': end_time.isoformat() if end_time else None,
        'total': total,
        'categories': categories,
    }