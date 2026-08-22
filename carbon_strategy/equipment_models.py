"""
equipment_models —— 设备机理模型

按设备类型分类的能耗与能效模型，覆盖清单中 9 类生产设备 + 3 类公用动力设备。
所有模型都是经验/机理公式，参数取自行业公开资料 + 现场标定经验值，
实际部署时建议用真实运行数据做最小二乘拟合修正系数。

【设计要点】
    - 函数式 API：每个模型是一个独立函数，便于策略引擎组合调用
    - 参数全部从 config.EQUIPMENT_TYPES 取额定功率，便于扩容设备清单
    - estimate_energy_savings 是统一入口，根据 equipment_type 路由到对应模型
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from config.settings import EQUIPMENT_LIST, EQUIPMENT_TYPES


# ============================================================
# 1. 电芯烘烤炉温控曲线（I-9，单台最高耗能 45kW）
# ============================================================
def baking_oven_curve(
    rated_power: float,
    temperature_set: float = 120.0,
    ambient_temp: float = 25.0,
    stage: str = 'auto',
    t: float = 0.0,
) -> float:
    """
    烘烤炉三阶段能耗模型。

    Parameters
    ----------
    rated_power      : 额定功率(kW)
    temperature_set  : 设定温度(℃)
    ambient_temp     : 环境温度(℃)
    stage            : 'heat'(升温) / 'hold'(保温) / 'cool'(降温) / 'auto'（按 t 自动判断）
    t                : 进入当前阶段的时间(min)

    Returns
    -------
    当前瞬时功率(kW)

    升温阶段：P = P_rated × (1 - e^(-k×t))，功率从额定值逐渐下降
    保温阶段：P = U×A×(T_set - T_ambient)，仅补偿热损失
    降温阶段：P = 0（自然冷却或辅助风机）
    """
    k = 0.08  # 升温系数（min^-1），现场标定
    U_A = rated_power / 100  # 保温阶段热损系数估算（kW/℃）

    if stage == 'auto':
        # 简单分段：0-35min 升温，35-120min 保温，>120min 降温
        if t < 35:
            stage = 'heat'
        elif t < 120:
            stage = 'hold'
        else:
            stage = 'cool'

    if stage == 'heat':
        return float(rated_power * (1 - np.exp(-k * t)))
    if stage == 'hold':
        return float(max(U_A * (temperature_set - ambient_temp), 0))
    if stage == 'cool':
        return 0.0
    raise ValueError(f'未知 stage: {stage}，可选 heat/hold/cool/auto')


# ============================================================
# 2. 电芯化成柜充放电能效（D-4, J-10，16 台 × 8kW）
# ============================================================
def formation_cabinet_efficiency(
    charge_rate: float = 0.5,
    soc: float = 0.5,
) -> Dict:
    """
    化成柜能效：能效随充电倍率(C-rate)和 SOC 变化。

    Parameters
    ----------
    charge_rate : 充电倍率 C-rate（0.5/1/2 等）
    soc         : 电池当前 SOC (0-1)

    Returns
    -------
    dict:
        efficiency       : 能效百分比
        heat_loss_factor : 焦耳热损耗系数（用于能耗上调）
    经验值：
        0.5C → 92%, 1C → 88%, 2C → 82%
        SOC 在 20%-80% 能效最优，过低过高均下降
    """
    # 倍率影响：C-rate 越大，能效越低
    rate_eff = {
        0.2: 0.94, 0.5: 0.92, 1.0: 0.88, 1.5: 0.85, 2.0: 0.82,
    }
    # 取最接近的倍率
    closest = min(rate_eff.keys(), key=lambda x: abs(x - charge_rate))
    base_eff = rate_eff[closest]

    # SOC 影响：超出 0.2-0.8 区间，能效下降
    if soc < 0.1 or soc > 0.95:
        soc_penalty = 0.10
    elif soc < 0.2 or soc > 0.80:
        soc_penalty = 0.04
    else:
        soc_penalty = 0.0

    eff = max(0.5, base_eff - soc_penalty)
    # 焦耳热损耗 = I²R，约束能耗
    heat_loss = 1 - eff
    return {
        'efficiency': round(eff, 4),
        'heat_loss_factor': round(heat_loss, 4),
    }


# ============================================================
# 3. 电芯卷绕机功率模型（C-3，15 台 × 15kW）
# ============================================================
def winding_machine_power(
    rated_power: float,
    tension: float = 10.0,
    speed: float = 1.0,
) -> float:
    """
    卷绕机功率 = 基础功率 + 张力项 + 速度项
    启停冲击能耗约为额定功率的 1.5 倍。
    """
    base = rated_power * 0.3
    tension_term = 0.4 * rated_power * (tension / 12.0)
    speed_term = 0.3 * rated_power * speed
    return float(min(base + tension_term + speed_term, rated_power * 1.2))


# ============================================================
# 4. 数控龙门铣床功率模型（L-12，4 台 × 18.5kW）
# ============================================================
def cnc_milling_power(
    rated_power: float,
    spindle_speed: float = 0.6,
    feed_rate: float = 0.5,
    depth: float = 0.3,
) -> float:
    """
    P = P_idle + k1×spindle_speed + k2×feed_rate×depth
    空载功率约占额定 30%，切削功率与材料去除率正相关。
    """
    p_idle = rated_power * 0.3
    p_spindle = rated_power * 0.4 * spindle_speed
    p_cutting = rated_power * 0.3 * feed_rate * depth * 2
    return float(min(p_idle + p_spindle + p_cutting, rated_power))


# ============================================================
# 5. 输送流水线功率模型（H-8，1 台 × 5.5kW）
# ============================================================
def conveyor_power(
    rated_power: float,
    load_weight: float = 0.5,
    speed: float = 1.0,
) -> float:
    """
    输送线功率 = 基础功率 + 负载×速度的二次项
    负载重量和运行速度近似二次关系。
    """
    base = rated_power * 0.25
    load_term = rated_power * 0.75 * (load_weight * speed) ** 2
    return float(min(base + load_term, rated_power * 1.1))


# ============================================================
# 6. 检测设备功率模型（外观/尺寸检测机，A-1/B-2/F-6）
# ============================================================
def inspector_power(
    rated_power: float,
    inspection_rate: float = 0.8,
) -> float:
    """
    检测设备功率近似线性：P = base + k×检测速率
    """
    base = rated_power * 0.2
    rate_term = rated_power * 0.8 * inspection_rate
    return float(base + rate_term)


# ============================================================
# 7. 分选机功率模型（E-5/G-7，10 台 × 4kW）
# ============================================================
def sorting_power(
    rated_power: float,
    sorting_speed: float = 0.7,
) -> float:
    """分选机功率近似线性，分选速度与功率正相关"""
    return float(rated_power * (0.25 + 0.75 * sorting_speed))


# ============================================================
# 8. AGV 充电功率模型（K-11，2 台 × 1.5kW）
# ============================================================
def agv_charging_power(
    rated_power: float,
    battery_soc: float = 0.3,
) -> float:
    """
    AGV 充电功率：SOC 越低，充电功率越接近额定
    SOC < 0.8 时进入充电模式，SOC > 0.95 停止充电
    """
    if battery_soc > 0.95:
        return 0.0
    if battery_soc < 0.8:
        return float(rated_power)
    # 0.8-0.95：涓流补电
    return float(rated_power * (1 - battery_soc) / 0.15)


# ============================================================
# 9. 空压机能效曲线（公用，3 台 × 75kW，最大公用耗能）
# ============================================================
def compressor_efficiency(
    rated_power: float,
    load_rate: float = 0.7,
) -> Dict:
    """
    比功率 = a0 + a1×负载率 + a2×负载率² + a3×负载率³
    负载率在 60%-80% 区间能效最优，<40% 能效急剧下降。
    """
    a0, a1, a2, a3 = 0.5, 0.8, -1.6, 0.6
    # 比功率(kW/(m³/min))
    specific_power = a0 + a1 * load_rate + a2 * load_rate**2 + a3 * load_rate**3
    # 能效比 = 实际功率 / 额定功率
    actual_power = rated_power * max(0.1, load_rate)
    efficiency = actual_power / (rated_power + 1e-6)
    # 在低负载区间惩罚
    if load_rate < 0.4:
        efficiency *= 0.7
    return {
        'specific_power': round(float(specific_power), 4),
        'actual_power': round(float(actual_power), 4),
        'efficiency': round(float(efficiency), 4),
        'load_rate': float(load_rate),
    }


# ============================================================
# 10. 风机特性方程（冷却风机，4 台 × 15kW）
# ============================================================
def fan_curve(
    rated_power: float,
    flow_rate: float = 0.8,
    static_pressure: float = 0.7,
) -> Dict:
    """
    风机相似定律：功率 ∝ 风量³
    风量下调 20%，功率可下降约 50%（变频改造是风机降碳最有效手段）
    """
    # 额定功率 × (风量)^3 × 压力修正
    actual_power = rated_power * (flow_rate ** 3) * (0.5 + 0.5 * static_pressure)
    return {
        'actual_power': round(float(actual_power), 4),
        'flow_rate': float(flow_rate),
        'static_pressure': float(static_pressure),
        'saving_potential': round(float(1 - flow_rate**3), 4),  # 风量减少带来的节电比例
    }


# ============================================================
# 11. 冷水机组 COP 模型（2 台 × 55kW）
# ============================================================
def chiller_cop(
    rated_power: float,
    outlet_temp: float = 7.0,
    ambient_temp: float = 32.0,
) -> Dict:
    """
    COP（性能系数）模型：出水温度和环境温度对能效比的影响。
    出水温度每升 1℃ COP 提升 ~2-3%，环境温度每升 1℃ COP 下降 ~1-2%
    """
    base_cop = 4.5
    cop = base_cop + (outlet_temp - 7) * 0.08 - (ambient_temp - 32) * 0.04
    cop = max(2.0, cop)
    return {
        'cop': round(float(cop), 4),
        'actual_power': round(float(rated_power / cop), 4),
        'outlet_temp': float(outlet_temp),
        'ambient_temp': float(ambient_temp),
    }


# ============================================================
# 12. 设备健康评分（所有设备）
# ============================================================
def equipment_health_score(equipment_data: pd.DataFrame) -> float:
    """
    设备健康评分 (0-100)：基于温度、振动、能效衰减综合打分。

    评分规则：
        - 温度偏高扣分
        - 振动超标扣分
        - 负载率过低扣分（设备空载）
    越接近 100 越健康。
    """
    if equipment_data is None or len(equipment_data) == 0:
        return 100.0
    df = equipment_data
    score = 100.0

    if 'temperature' in df.columns:
        avg_temp = df['temperature'].mean()
        if avg_temp > 50:
            score -= (avg_temp - 50) * 0.5
    if 'vibration' in df.columns:
        avg_vib = df['vibration'].mean()
        if avg_vib > 2:
            score -= (avg_vib - 2) * 5
    if 'load_rate' in df.columns:
        avg_load = df['load_rate'].mean()
        if avg_load < 0.4:
            score -= (0.4 - avg_load) * 50
    return round(max(0, min(100, score)), 2)


# ============================================================
# 13. 节能量估算（统一入口，按 equipment_type 路由）
# ============================================================
def estimate_energy_savings(
    equipment_id: str,
    current_state: Dict,
    target_state: Dict,
) -> Dict:
    """
    估算调整工况后的节能量。

    Parameters
    ----------
    equipment_id    : 设备 ID（用于查 equipment_type）
    current_state   : 当前工况 dict，如 {'load_rate':0.3, 'temp':130, 'vibration':3.2}
    target_state    : 目标工况 dict

    Returns
    -------
    dict:
        power_before        调整前功率(kW)
        power_after         调整后功率(kW)
        power_saving_kW     节约功率(kW)
        saving_percentage   节电比例
    """
    info = EQUIPMENT_LIST.get(equipment_id, {})
    eq_type = info.get('equipment_type')
    type_info = EQUIPMENT_TYPES.get(eq_type, {})
    rated_power = type_info.get('rated_power', 0)

    # 按 equipment_type 调用对应模型估算
    power_before = _estimate_power(eq_type, rated_power, current_state)
    power_after = _estimate_power(eq_type, rated_power, target_state)
    saving_kW = max(0, power_before - power_after)
    saving_pct = saving_kW / power_before if power_before > 0 else 0
    return {
        'power_before': round(float(power_before), 4),
        'power_after': round(float(power_after), 4),
        'power_saving_kW': round(float(saving_kW), 4),
        'saving_percentage': round(float(saving_pct), 4),
    }


def _estimate_power(eq_type: str, rated_power: float, state: Dict) -> float:
    """内部：根据 equipment_type 调对应模型估算功率"""
    if eq_type == 'baking_oven':
        return baking_oven_curve(
            rated_power,
            temperature_set=state.get('temp_set', 120),
            ambient_temp=state.get('ambient', 25),
            t=state.get('t', 0),
        )
    if eq_type == 'formation_cabinet':
        eff = formation_cabinet_efficiency(
            charge_rate=state.get('charge_rate', 0.5),
            soc=state.get('soc', 0.5),
        )
        return rated_power * eff['heat_loss_factor'] + rated_power * (1 - eff['heat_loss_factor']) * 0.5
    if eq_type == 'winding_machine':
        return winding_machine_power(
            rated_power,
            tension=state.get('tension', 10),
            speed=state.get('speed', 1.0),
        )
    if eq_type == 'cnc_milling_machine':
        return cnc_milling_power(
            rated_power,
            spindle_speed=state.get('spindle_speed', 0.6),
            feed_rate=state.get('feed_rate', 0.5),
            depth=state.get('depth', 0.3),
        )
    if eq_type == 'conveyor_line':
        return conveyor_power(
            rated_power,
            load_weight=state.get('load_weight', 0.5),
            speed=state.get('speed', 1.0),
        )
    if eq_type in ('appearance_inspector', 'dimension_inspector'):
        return inspector_power(rated_power, inspection_rate=state.get('inspection_rate', 0.8))
    if eq_type == 'sorting_machine':
        return sorting_power(rated_power, sorting_speed=state.get('sorting_speed', 0.7))
    if eq_type == 'agv':
        return agv_charging_power(rated_power, battery_soc=state.get('soc', 0.3))
    if eq_type == 'compressor':
        res = compressor_efficiency(rated_power, load_rate=state.get('load_rate', 0.7))
        return res['actual_power']
    if eq_type == 'cooling_fan':
        res = fan_curve(
            rated_power,
            flow_rate=state.get('flow_rate', 0.8),
            static_pressure=state.get('static_pressure', 0.7),
        )
        return res['actual_power']
    if eq_type == 'chiller':
        res = chiller_cop(
            rated_power,
            outlet_temp=state.get('outlet_temp', 7),
            ambient_temp=state.get('ambient', 32),
        )
        return res['actual_power']
    # 兜底：用负载率线性估算
    return float(rated_power * state.get('load_rate', 0.7))
