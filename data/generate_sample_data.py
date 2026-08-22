"""
generate_sample_data —— 模拟设备时序数据生成脚本

生成 data/raw_data/sample_equipment_data.csv，基于设备清单：
    - 9 类生产设备 + 3 类公用动力设备
    - 8 台代表设备（覆盖高/中/低耗能各类型）
    - 连续 7 天，分钟级采样（共 10080 行/台）
    - 每台设备注入 2-3 次异常事件，验证 LSTM 异常检测效果

【数据规律】
    - 正常工况：功率在额定值 60%-90% 波动，温度稳定，振动正常
    - 班次规律：早班负载高，中班中等，夜班低（化成柜除外，24h 运行）
    - 周末规律：周六日负载降低约 30%
    - 异常注入：烘烤炉超温、空压机低负载、化成柜大电流充电等

运行方式：
    python data/generate_sample_data.py

输出：
    data/raw_data/sample_equipment_data.csv  （约 8 万行）
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import sys

# 把项目根目录加入 sys.path，便于直接 import config
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import EQUIPMENT_LIST, EQUIPMENT_TYPES, RAW_DATA_DIR


# ============================================================
# 入选代表设备（覆盖高/中/低耗能各类型，便于测试）
# ============================================================
REPRESENTATIVE_EQUIPMENT = [
    ('I-9-01', 'baking_oven'),         # 单台最高耗能 45kW
    ('COMP-01', 'compressor'),        # 公用最大 75kW
    ('D-4-01', 'formation_cabinet'),  # 数量最多的高耗能 8kW
    ('C-3-01', 'winding_machine'),    # 数量最多生产设备 15kW
    ('L-12-01', 'cnc_milling_machine'),  # 加工设备代表 18.5kW
    ('FAN-01', 'cooling_fan'),        # 风机特性方程验证 15kW
    ('CHILL-01', 'chiller'),          # COP 模型验证 55kW
    ('A-1-01', 'appearance_inspector'),  # 低耗能 3kW（线性特征）
]

# 时间范围
START_TIME = datetime(2026, 8, 15, 0, 0, 0)  # 周六
DURATION_DAYS = 7
SAMPLE_FREQ_MIN = 1  # 分钟级

# 异常事件配置（每台设备的异常注入点）
ANOMALY_EVENTS = {
    'I-9-01': [  # 烘烤炉：超温
        {'day': 1, 'hour': 14, 'duration': 90, 'type': 'overheat', 'temp_offset': 12},
        {'day': 4, 'hour': 10, 'duration': 60, 'type': 'overheat', 'temp_offset': 8},
    ],
    'COMP-01': [  # 空压机：低负载运行
        {'day': 2, 'hour': 3, 'duration': 120, 'type': 'low_load', 'load_ratio': 0.25},
        {'day': 5, 'hour': 22, 'duration': 90, 'type': 'low_load', 'load_ratio': 0.30},
    ],
    'D-4-01': [  # 化成柜：大电流充电（高负载）
        {'day': 3, 'hour': 16, 'duration': 75, 'type': 'high_load', 'load_ratio': 0.98},
        {'day': 6, 'hour': 9, 'duration': 60, 'type': 'high_load', 'load_ratio': 0.95},
    ],
    'C-3-01': [  # 卷绕机：启停冲击 + 高负载
        {'day': 2, 'hour': 10, 'duration': 45, 'type': 'startup_surge', 'power_spike': 1.4},
        {'day': 5, 'hour': 14, 'duration': 60, 'type': 'high_load', 'load_ratio': 0.92},
    ],
    'L-12-01': [  # 龙门铣床：振动异常 + 高负载
        {'day': 3, 'hour': 11, 'duration': 50, 'type': 'vibration_spike', 'vib_factor': 2.5},
        {'day': 6, 'hour': 15, 'duration': 40, 'type': 'high_load', 'load_ratio': 0.95},
    ],
    'FAN-01': [  # 冷却风机：低负载（变频未启动）
        {'day': 4, 'hour': 4, 'duration': 100, 'type': 'low_load', 'load_ratio': 0.35},
        {'day': 6, 'hour': 23, 'duration': 80, 'type': 'low_load', 'load_ratio': 0.40},
    ],
    'CHILL-01': [  # 冷水机组：COP 下降
        {'day': 1, 'hour': 13, 'duration': 70, 'type': 'low_efficiency', 'eff_drop': 0.2},
        {'day': 4, 'hour': 16, 'duration': 60, 'type': 'high_load', 'load_ratio': 0.95},
    ],
    'A-1-01': [  # 检测机：一般高负载（轻微异常）
        {'day': 2, 'hour': 9, 'duration': 40, 'type': 'high_load', 'load_ratio': 0.90},
    ],
}


def _time_index() -> pd.DatetimeIndex:
    """7 天 × 1 分钟 = 10080 个时间戳"""
    return pd.date_range(
        start=START_TIME,
        periods=DURATION_DAYS * 24 * 60,
        freq=f'{SAMPLE_FREQ_MIN}min',
    )


def _shift_factor(hour: int) -> float:
    """班次负载因子：早班 1.0，中班 0.85，夜班 0.5"""
    if 8 <= hour < 16:
        return 1.0
    if 16 <= hour < 24:
        return 0.85
    return 0.5


def _weekend_factor(weekday: int) -> float:
    """周末负载降低 30%"""
    return 0.7 if weekday >= 5 else 1.0


def _in_window(ts: pd.Timestamp, day: int, hour: int, duration: int) -> bool:
    """判断 ts 是否落在异常事件窗口"""
    target_start = START_TIME + timedelta(days=day, hours=hour)
    target_end = target_start + timedelta(minutes=duration)
    return target_start <= ts <= target_end


def _generate_normal_pattern(
    timestamps: pd.DatetimeIndex,
    rated_power: float,
    eq_type: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    生成正常工况的功率/温度/振动/负载率序列。

    Returns
    -------
    power (kW), temperature (℃), vibration (mm/s), load_rate (0-1)
    """
    n = len(timestamps)
    # 基础负载率
    base_load = np.array([_shift_factor(ts.hour) * _weekend_factor(ts.weekday())
                          for ts in timestamps], dtype=np.float32)
    # 加正弦波动 + 随机噪声
    t = np.arange(n, dtype=np.float32)
    sine_wave = 0.1 * np.sin(2 * np.pi * t / (60 * 24))  # 日周期
    noise = np.random.normal(0, 0.03, n)
    # 设备类型修正：化成柜 24h 运行，夜班负载不下调
    if eq_type == 'formation_cabinet':
        base_load = np.where(base_load < 0.6, 0.7, base_load)
    # 公用动力设备（空压机/风机/冷水机组）夜间也要保持基础负载
    if eq_type in ('compressor', 'cooling_fan', 'chiller'):
        base_load = np.where(base_load < 0.5, 0.55, base_load)

    load_rate = np.clip(base_load * (0.6 + 0.2 * (sine_wave + 1) + 0.15) + noise,
                        0.05, 1.0)
    # 在 0.6-0.9 之间波动（大部分时间）
    load_rate = np.clip(load_rate * 0.85 + 0.15, 0.05, 1.0)

    power = rated_power * load_rate + np.random.normal(0, rated_power * 0.02, n)
    power = np.clip(power, 0, rated_power * 1.05)

    # 温度：基于负载率 + 设备类型基础温度
    base_temp = {
        'baking_oven': 120.0,
        'formation_cabinet': 45.0,
        'compressor': 75.0,
        'cooling_fan': 35.0,
        'chiller': 30.0,
        'cnc_milling_machine': 55.0,
        'winding_machine': 40.0,
        'appearance_inspector': 25.0,
    }.get(eq_type, 30.0)
    temperature = base_temp + load_rate * 20 + np.random.normal(0, 1.5, n)

    # 振动：正常 1-3 mm/s
    base_vib = {
        'cnc_milling_machine': 3.0,
        'compressor': 2.5,
        'cooling_fan': 2.0,
        'winding_machine': 2.5,
        'baking_oven': 0.5,
        'formation_cabinet': 1.0,
        'chiller': 2.0,
        'appearance_inspector': 0.3,
    }.get(eq_type, 1.5)
    vibration = base_vib * (0.5 + 0.5 * load_rate) + np.random.normal(0, 0.2, n)
    vibration = np.clip(vibration, 0, 10)

    return power, temperature, vibration, load_rate


def _inject_anomalies(
    timestamps: pd.DatetimeIndex,
    power: np.ndarray,
    temperature: np.ndarray,
    vibration: np.ndarray,
    load_rate: np.ndarray,
    eq_id: str,
    rated_power: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """注入异常事件"""
    events = ANOMALY_EVENTS.get(eq_id, [])
    for ev in events:
        for i, ts in enumerate(timestamps):
            if not _in_window(ts, ev['day'], ev['hour'], ev['duration']):
                continue
            ev_type = ev['type']
            if ev_type == 'overheat':
                temperature[i] += ev['temp_offset'] + np.random.normal(0, 0.5)
                power[i] *= 1.15  # 超温导致加热功率上升
            elif ev_type == 'low_load':
                load_rate[i] = ev['load_ratio'] + np.random.normal(0, 0.02)
                power[i] = rated_power * load_rate[i]
            elif ev_type == 'high_load':
                load_rate[i] = ev['load_ratio'] + np.random.normal(0, 0.02)
                power[i] = rated_power * load_rate[i]
                temperature[i] += 8
            elif ev_type == 'startup_surge':
                power[i] = rated_power * ev['power_spike'] * (1 + np.random.normal(0, 0.05))
                vibration[i] *= 2
            elif ev_type == 'vibration_spike':
                vibration[i] *= ev['vib_factor']
                power[i] *= 1.08
            elif ev_type == 'low_efficiency':
                # COP 下降，相同负载功率上升
                power[i] *= (1 + ev['eff_drop'])
                temperature[i] += 5
    power = np.clip(power, 0, rated_power * 1.5)
    load_rate = np.clip(load_rate, 0, 1.2)
    return power, temperature, vibration, load_rate


def _build_voltage_current(power: np.ndarray, rated_power: float) -> Tuple[np.ndarray, np.ndarray]:
    """根据功率反推电压/电流（近似）"""
    voltage = np.full_like(power, 380.0)  # 工业三相 380V
    voltage += np.random.normal(0, 5, len(power))
    current = power / (380 * 1.732) * 1000  # 三相 P = √3 × U × I
    current += np.random.normal(0, 0.5, len(current))
    current = np.clip(current, 0, rated_power * 1.5)
    return voltage, current


def _build_energy_runtime(power: np.ndarray, base_energy: float, base_runtime: float) -> Tuple[np.ndarray, np.ndarray]:
    """能耗累计 + 运行时长累计"""
    # 每 1 分钟，能耗增量 = power × 1/60 kWh
    energy_diff = power / 60.0
    energy_cum = np.cumsum(energy_diff) + base_energy
    runtime_inc = np.full_like(power, 1.0 / 60.0)  # 每分钟 +1/60 小时
    runtime_cum = np.cumsum(runtime_inc) + base_runtime
    return energy_cum, runtime_cum


def _build_status(load_rate: np.ndarray) -> np.ndarray:
    """状态：1=运行, 2=待机, 0=停机"""
    status = np.where(load_rate > 0.1, 1, np.where(load_rate > 0.02, 2, 0))
    return status.astype(int)


def generate_for_equipment(eq_id: str, eq_type: str) -> pd.DataFrame:
    """为单台设备生成 7 天分钟级时序数据"""
    info = EQUIPMENT_LIST[eq_id]
    type_info = EQUIPMENT_TYPES[eq_type]
    rated_power = type_info['rated_power']

    timestamps = _time_index()
    n = len(timestamps)

    power, temperature, vibration, load_rate = _generate_normal_pattern(
        timestamps, rated_power, eq_type
    )
    power, temperature, vibration, load_rate = _inject_anomalies(
        timestamps, power, temperature, vibration, load_rate, eq_id, rated_power
    )

    voltage, current = _build_voltage_current(power, rated_power)
    # 不同设备的初始累计能耗/运行时长（避免所有设备从0开始）
    base_energy = float(np.random.randint(50000, 200000))
    base_runtime = float(np.random.randint(2000, 12000))
    energy, runtime = _build_energy_runtime(power, base_energy, base_runtime)
    status = _build_status(load_rate)

    df = pd.DataFrame({
        'timestamp': timestamps,
        'equipment_id': eq_id,
        'equipment_type': eq_type,
        'workshop_id': info['workshop_id'],
        'team_id': info['team_id'],
        'voltage': np.round(voltage, 2),
        'current': np.round(current, 3),
        'power': np.round(power, 4),
        'energy': np.round(energy, 4),
        'load_rate': np.round(load_rate, 4),
        'temperature': np.round(temperature, 2),
        'vibration': np.round(vibration, 3),
        'runtime_hours': np.round(runtime, 2),
        'status': status,
    })
    return df


def main():
    """生成全部代表设备的合并 CSV"""
    np.random.seed(42)  # 固定种子保证可复现
    print(f'[generate] 开始生成 {len(REPRESENTATIVE_EQUIPMENT)} 台设备 × 7 天 数据...')
    frames = []
    for eq_id, eq_type in REPRESENTATIVE_EQUIPMENT:
        print(f'  - {eq_id} ({eq_type})')
        df = generate_for_equipment(eq_id, eq_type)
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    print(f'[generate] 合并后总行数: {len(all_df)}')

    # 输出路径
    out_path = RAW_DATA_DIR / 'sample_equipment_data.csv'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    all_df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'[generate] CSV saved → {out_path}')
    print(f'[generate] 文件大小约 {out_path.stat().st_size / 1024:.1f} KB')

    # 简单验证
    print('\n[verify] 数据预览：')
    print(all_df.head(3))
    print(f'\n[verify] 设备数量: {all_df["equipment_id"].nunique()}')
    print(f'[verify] 时间范围: {all_df["timestamp"].min()} ~ {all_df["timestamp"].max()}')
    print(f'[verify] 总碳排估算: {all_df["power"].sum() / 60 * 0.5810:.2f} kgCO2')


if __name__ == '__main__':
    main()
