"""
simulator —— 模拟采集器（无真实 MES/EMS/PLC 时的替代数据源）

复用 data/generate_sample_data.py 的生成逻辑（8 台代表设备、分钟级、
含异常注入），把数据经 IngestionService 写入 time_series_data 表，
用于打通「采集 → 数据库 → 算法」实时链路。

使用方式：
    python -m collector.simulator            # 回填近 7 天数据（8 台设备）
    python -m collector.simulator --days 3   # 仅回填近 3 天
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Dict, List

from data.generate_sample_data import REPRESENTATIVE_EQUIPMENT, generate_for_equipment
from collector.service import IngestionService


def _df_to_rows(eq_id: str, df) -> List[dict]:
    """把单台设备的 DataFrame 转成入写服务所需的行 dict 列表"""
    cols = ['timestamp', 'power', 'temperature', 'vibration', 'load_rate']
    rows = df[cols].assign(equipment_id=eq_id).to_dict(orient='records')
    return rows


def backfill_historical(days: int = 7) -> Dict[str, int]:
    """回填历史数据：8 台代表设备 × 近 days 天（分钟级）写入数据库"""
    svc = IngestionService()
    min_ts = datetime.now() - timedelta(days=days)
    agg = {'inserted': 0, 'updated': 0, 'total': 0}

    for eq_id, eq_type in REPRESENTATIVE_EQUIPMENT:
        df = generate_for_equipment(eq_id, eq_type)
        df = df[df['timestamp'] >= min_ts] if days < 7 else df
        res = svc.write_batch(_df_to_rows(eq_id, df))
        for k in agg:
            agg[k] += res[k]
        print(f'  - {eq_id} 写入/更新 {res["total"]} 条')
    return agg


def collect_live(minutes: int = 1) -> Dict[str, int]:
    """模拟实时采集：取每台代表设备最近 minutes 分钟的读数写入数据库"""
    svc = IngestionService()
    agg = {'inserted': 0, 'updated': 0, 'total': 0}

    for eq_id, eq_type in REPRESENTATIVE_EQUIPMENT:
        df = generate_for_equipment(eq_id, eq_type).tail(minutes)
        res = svc.write_batch(_df_to_rows(eq_id, df))
        for k in agg:
            agg[k] += res[k]
    return agg


def main() -> None:
    parser = argparse.ArgumentParser(description='模拟采集：把 MES/EMS/PLC 数据写入数据库')
    parser.add_argument('--days', type=int, default=7, help='回填最近 N 天数据（默认 7）')
    args = parser.parse_args()

    print(f'[collector] 开始回填近 {args.days} 天模拟数据（8 台代表设备）...')
    result = backfill_historical(days=args.days)
    print(f'[collector] 完成：新增 {result["inserted"]}，更新 {result["updated"]}，'
          f'共 {result["total"]} 条')


if __name__ == '__main__':
    main()