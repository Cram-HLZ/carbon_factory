"""
traceability —— 碳排溯源

核心类：TraceabilityAnalyzer
    对异常设备做 72h 历史回溯 + 高碳排根因定位。

【根因分析逻辑】（按可能性排序，针对锂电工厂设备特性）
    1. 烘烤炉温控异常         - I-9 高耗能
    2. 化成柜充电倍率过高     - D-4 / J-10 数量最多的高耗能设备
    3. 设备空载/低负载运行    - 空压机/风机/卷绕机
    4. 设备老化/能效衰减     - 对比历史同时段
    5. 工艺参数异常           - 卷绕张力/速度偏离设定
    6. 生产排班不合理        - 高峰电价时段满负荷
    7. 设备故障前兆           - 振动/温度持续上升伴随能效下降

后端同学：POST /api/v1/traceability/report 调用本类的 generate_trace_report，
        前端展示"设备溯源台账"页面。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.settings import (
    CARBON_FACTORS,
    EQUIPMENT_LIST,
    EQUIPMENT_TYPES,
)
from carbon_strategy.equipment_models import equipment_health_score


class TraceabilityAnalyzer:
    """碳排溯源分析器"""

    def __init__(self, data_loader=None, carbon_factor: Optional[float] = None):
        """
        Parameters
        ----------
        data_loader : feature_engineer.DataLoader 实例，用于加载历史数据
                      不传则只能用 equipment_data 入口（后端直接传 DataFrame）
        carbon_factor : 电力碳排因子，默认 config.CARBON_FACTORS['electricity']
        """
        self.data_loader = data_loader
        self.carbon_factor = (
            carbon_factor if carbon_factor is not None else CARBON_FACTORS['electricity']
        )

    # ---------------- 历史回溯 ----------------
    def get_equipment_history(
        self,
        equipment_id: str,
        hours: int = 72,
    ) -> pd.DataFrame:
        """
        查询设备近 N 小时运行参数（默认 72h）。

        若 data_loader 不可用，返回空 DataFrame，调用方应改用
        get_equipment_history_from_df 直接传历史 DataFrame。
        """
        if self.data_loader is None:
            return pd.DataFrame()
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        return self.data_loader.load_equipment_data(equipment_id, start_time, end_time)

    @staticmethod
    def get_equipment_history_from_df(
        full_data: pd.DataFrame,
        equipment_id: str,
        anomaly_time: datetime,
        hours: int = 72,
    ) -> pd.DataFrame:
        """从全量 DataFrame 中切出 72h 历史（开发期/联调期常用）"""
        if full_data is None or full_data.empty:
            return pd.DataFrame()
        if 'timestamp' not in full_data.columns:
            return pd.DataFrame()
        df = full_data[full_data['equipment_id'] == equipment_id].copy()
        if df.empty:
            return df
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        start = pd.Timestamp(anomaly_time) - timedelta(hours=hours)
        end = pd.Timestamp(anomaly_time)
        return df[(df['timestamp'] >= start) & (df['timestamp'] <= end)].reset_index(drop=True)

    # ---------------- 根因分析 ----------------
    def analyze_root_cause(
        self,
        equipment_id: str,
        anomaly_time: datetime,
        history_data: Optional[pd.DataFrame] = None,
    ) -> Dict:
        """
        高碳排根因分析。

        Parameters
        ----------
        equipment_id    : 设备 ID
        anomaly_time    : 异常发生时间
        history_data    : 设备近 72h 历史 DataFrame（不传则用 data_loader 查）

        Returns
        -------
        dict: 含 root_causes / baseline_emission / excess_emission
        """
        if history_data is None or history_data.empty:
            history_data = self.get_equipment_history(equipment_id)

        info = EQUIPMENT_LIST.get(equipment_id, {})
        eq_type = info.get('equipment_type', 'unknown')
        type_info = EQUIPMENT_TYPES.get(eq_type, {})

        # 基线/异常段对比
        anomaly_window_start = pd.Timestamp(anomaly_time) - timedelta(hours=1)
        anomaly_window_end = pd.Timestamp(anomaly_time)
        recent_data = pd.DataFrame()
        if not history_data.empty and 'timestamp' in history_data.columns:
            mask = (
                pd.to_datetime(history_data['timestamp']) >= anomaly_window_start
            ) & (pd.to_datetime(history_data['timestamp']) <= anomaly_window_end)
            recent_data = history_data[mask].copy()

        # 基线：异常前 24h（去掉最近 1h）
        baseline_data = pd.DataFrame()
        if not history_data.empty and 'timestamp' in history_data.columns:
            baseline_end = pd.Timestamp(anomaly_time) - timedelta(hours=1)
            baseline_start = baseline_end - timedelta(hours=24)
            mask = (
                pd.to_datetime(history_data['timestamp']) >= baseline_start
            ) & (pd.to_datetime(history_data['timestamp']) <= baseline_end)
            baseline_data = history_data[mask].copy()

        baseline_emission = self._emission_per_hour(baseline_data)
        anomaly_emission = self._emission_per_hour(recent_data)
        excess_emission = max(0, anomaly_emission - baseline_emission)

        root_causes = self._match_root_causes(
            equipment_id, eq_type, recent_data, baseline_data
        )

        return {
            'equipment_id': equipment_id,
            'equipment_name': info.get('name', equipment_id),
            'equipment_type': eq_type,
            'workshop_id': info.get('workshop_id'),
            'team_id': info.get('team_id'),
            'anomaly_time': anomaly_time.strftime('%Y-%m-%d %H:%M:%S'),
            'carbon_emission': round(float(anomaly_emission), 4),
            'baseline_emission': round(float(baseline_emission), 4),
            'excess_emission': round(float(excess_emission), 4),
            'root_causes': root_causes,
            'health_score': equipment_health_score(recent_data),
        }

    # ---------------- 完整溯源报告 ----------------
    def generate_trace_report(
        self,
        equipment_id: str,
        anomaly_time: datetime,
        history_data: Optional[pd.DataFrame] = None,
    ) -> Dict:
        """
        生成完整溯源报告（根因 + 72h 历史 + 改进建议）。
        """
        if history_data is None or history_data.empty:
            history_data = self.get_equipment_history(equipment_id)

        cause_result = self.analyze_root_cause(equipment_id, anomaly_time, history_data)
        summary = self._summarize_history(history_data)

        report = {
            **cause_result,
            'history_72h_summary': summary,
            'recommendation': self._build_recommendation(cause_result),
        }
        return report

    # ---------------- 与基线对比 ----------------
    def compare_with_baseline(
        self,
        equipment_id: str,
        history_data: pd.DataFrame,
        period: str = 'last_week',
    ) -> Dict:
        """
        与历史同期/同类设备基线对比。

        Returns
        -------
        dict:
            current_energy / baseline_energy / increase_percentage
            current_carbon / baseline_carbon
        """
        if history_data is None or history_data.empty:
            return {}
        current = history_data.tail(60 * 24)  # 最近 24h
        baseline = history_data.head(len(history_data) - 60 * 24) if len(history_data) > 60 * 24 else history_data
        cur_energy = float(current['power'].sum() * 60 / 1000) if 'power' in current.columns else 0
        base_energy = float(baseline['power'].sum() * 60 / 1000) if 'power' in baseline.columns else 0
        inc_pct = (cur_energy - base_energy) / base_energy * 100 if base_energy > 0 else 0
        return {
            'current_energy_kwh': round(cur_energy, 4),
            'baseline_energy_kwh': round(base_energy, 4),
            'increase_percentage': round(float(inc_pct), 2),
            'current_carbon_kg': round(cur_energy * self.carbon_factor, 4),
            'baseline_carbon_kg': round(base_energy * self.carbon_factor, 4),
        }

    # ---------------- 内部工具 ----------------
    def _emission_per_hour(self, df: pd.DataFrame) -> float:
        """计算每小时碳排(kgCO2/h)"""
        if df is None or df.empty or 'power' not in df.columns:
            return 0.0
        avg_power = float(df['power'].mean())
        return avg_power * self.carbon_factor

    def _match_root_causes(
        self,
        equipment_id: str,
        eq_type: str,
        recent_data: pd.DataFrame,
        baseline_data: pd.DataFrame,
    ) -> List[Dict]:
        """根据设备类型与数据特征匹配根因（规则引擎）"""
        causes: List[Dict] = []

        if recent_data is None or recent_data.empty:
            return causes

        recent = recent_data
        baseline = baseline_data if baseline_data is not None and not baseline_data.empty else recent

        # 1. 烘烤炉温控异常
        if eq_type == 'baking_oven' and 'temperature' in recent.columns:
            temp_mean = float(recent['temperature'].mean())
            temp_base = float(baseline['temperature'].mean()) if 'temperature' in baseline.columns else 120
            deviation = temp_mean - temp_base
            if abs(deviation) > 5:
                causes.append({
                    'cause': f'温控异常-{"保温温度偏高" if deviation > 0 else "保温温度偏低"}',
                    'confidence': round(min(0.95, 0.6 + abs(deviation) / 20), 2),
                    'detail': (
                        f'基线平均温度 {temp_base:.1f}℃，'
                        f'当前平均 {temp_mean:.1f}℃，'
                        f'偏离 {abs(deviation):.1f}℃，'
                        f'保温阶段功率比基准高 '
                        f'{(recent["power"].mean() / max(baseline["power"].mean(), 1e-6) - 1) * 100:.1f}%'
                    ),
                })

        # 2. 化成柜充电倍率异常
        if eq_type == 'formation_cabinet' and 'load_rate' in recent.columns:
            high_load_count = int((recent['load_rate'] > 0.85).sum())
            if high_load_count > 60:  # 60 分钟以上高负载
                causes.append({
                    'cause': '充电倍率过高-大电流充电持续过长',
                    'confidence': 0.82,
                    'detail': (
                        f'近 {high_load_count} 分钟负载率 > 0.85（疑似 1C 以上倍率），'
                        f'焦耳热损耗显著增加，建议降至 0.5C 恒流'
                    ),
                })

        # 3. 设备空载/低负载运行
        if 'load_rate' in recent.columns:
            low_load_count = int((recent['load_rate'] < 0.4).sum())
            if low_load_count > 30:
                causes.append({
                    'cause': '设备低负载运行-能效急剧下降',
                    'confidence': 0.78,
                    'detail': (
                        f'近 {low_load_count} 分钟负载率 < 40%，'
                        f'{"空压机低于 40% 能效骤降（建议群控切换）" if eq_type == "compressor" else "建议停机或合并负载"}'
                    ),
                })

        # 4. 设备老化/能效衰减
        if not baseline.empty and 'power' in recent.columns and 'power' in baseline.columns:
            cur_energy = float(recent['power'].mean())
            base_energy = float(baseline['power'].mean())
            if base_energy > 0:
                inc_pct = (cur_energy - base_energy) / base_energy * 100
                if inc_pct > 15:
                    causes.append({
                        'cause': '设备老化或保温层衰减',
                        'confidence': round(min(0.85, 0.5 + inc_pct / 50), 2),
                        'detail': (
                            f'对比基线 24h，相同负载下能耗上升 {inc_pct:.1f}%，'
                            f'{"疑似保温层老化（建议红外热成像检测）" if eq_type == "baking_oven" else "疑似机械磨损/润滑失效"}'
                        ),
                    })

        # 5. 振动/温度异常（设备故障前兆）
        if 'vibration' in recent.columns and not recent.empty:
            vib_mean = float(recent['vibration'].mean())
            vib_base = float(baseline['vibration'].mean()) if 'vibration' in baseline.columns else 2.0
            if vib_mean > vib_base * 1.5 and vib_mean > 3.0:
                causes.append({
                    'cause': '设备故障前兆-振动持续上升',
                    'confidence': 0.7,
                    'detail': (
                        f'振动均值 {vib_mean:.2f} mm/s（基线 {vib_base:.2f}），'
                        f'{"建议停机检查轴承/刀片（铣床）" if eq_type == "cnc_milling_machine" else "建议检查叶轮动平衡（风机）"}'
                    ),
                })

        # 兜底：没有命中任何规则时给一个通用建议
        if not causes:
            causes.append({
                'cause': '瞬时能耗波动-暂无明显规律',
                'confidence': 0.5,
                'detail': '未匹配到明显根因规则，建议延长观察窗口并人工排查设备日志',
            })

        # 按 confidence 降序排序
        causes.sort(key=lambda c: c['confidence'], reverse=True)
        return causes

    def _summarize_history(self, history_data: pd.DataFrame) -> Dict:
        """生成 72h 历史汇总"""
        if history_data is None or history_data.empty:
            return {
                'avg_load': 0.0, 'avg_emission': 0.0,
                'runtime': 0.0, 'avg_temp': 0.0, 'temp_deviation': 0.0,
            }
        df = history_data
        avg_load = float(df['load_rate'].mean()) if 'load_rate' in df.columns else 0
        avg_power = float(df['power'].mean()) if 'power' in df.columns else 0
        avg_temp = float(df['temperature'].mean()) if 'temperature' in df.columns else 0
        temp_dev = float(df['temperature'].std()) if 'temperature' in df.columns else 0
        runtime = float(len(df) / 60)  # 分钟 → 小时
        return {
            'avg_load': round(avg_load, 4),
            'avg_emission': round(avg_power * self.carbon_factor, 4),
            'runtime': round(runtime, 2),
            'avg_temp': round(avg_temp, 2),
            'temp_deviation': round(temp_dev, 2),
        }

    def _build_recommendation(self, cause_result: Dict) -> str:
        """根据根因生成改进建议（自然语言描述）"""
        top_cause = cause_result.get('root_causes', [{}])[0].get('cause', '')
        excess = cause_result.get('excess_emission', 0)
        if '温控' in top_cause:
            return (
                '建议校准温度传感器（PT100），检查保温层密封情况，'
                '优化升温曲线改为阶梯升温，预计可降碳 15%-20%。'
            )
        if '充电倍率' in top_cause:
            return (
                '建议优化化成充电倍率曲线，谷电时段 0.5C 恒流，'
                '峰电时段仅涓流补电，预计可降碳 8%-12%。'
            )
        if '低负载' in top_cause:
            return (
                '建议引入空压机群控，停用低负载设备，'
                '负载率提升至 60%-80% 区间，预计可降碳 25%-30%。'
            )
        if '老化' in top_cause:
            return '建议安排设备维护/保温层更换，预计可恢复 10%-15% 能效。'
        return '建议延长监控窗口并人工排查设备运行日志。'
