"""
feature_extractor —— 特征提取

核心类：FeatureExtractor
    一次性入口：extract(df) 输出含 8 维模型输入特征 + 滑窗统计 + 碳排特征的 DataFrame。

【8 维 LSTM 输入特征】（对应 config.MODEL_CONFIG['input_size']=8）
    1. load_rate           负载率
    2. power                有功功率 (kW)
    3. energy_diff          能耗增量 (kWh/min)
    4. temperature          设备温度
    5. vibration            振动值
    6. carbon_emission      实时碳排 (kgCO2/min)
    7. power_change_rate    功率变化率
    8. runtime_hours        累计运行时长

【设计要点】
    - 碳排特征用 IPCC 电力因子 0.5810 kgCO2/kWh 计算
    - 滑窗统计用过去 N 步（默认 N=10）的均值/标准差/最大/最小/斜率
    - 单位产量能耗需要调用方传入产量列 production_output（开发期可选）
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from config.settings import CARBON_FACTORS, EQUIPMENT_TYPES, MODEL_CONFIG


# LSTM 输入的 8 维特征列顺序（sequence_builder 严格按此顺序切序列）
FEATURE_COLUMNS: List[str] = [
    'load_rate',
    'power',
    'energy_diff',
    'temperature',
    'vibration',
    'carbon_emission',
    'power_change_rate',
    'runtime_hours',
]

# 特征中文展示名（可解释性：top 特征贡献的前端展示用）
FEATURE_DISPLAY_NAMES: dict = {
    'load_rate': '负载率',
    'power': '有功功率',
    'energy_diff': '能耗增量',
    'temperature': '设备温度',
    'vibration': '振动值',
    'carbon_emission': '碳排放',
    'power_change_rate': '功率变化率',
    'runtime_hours': '累计运行时长',
}

# 验证：必须与 config.MODEL_CONFIG['input_size'] 一致
assert len(FEATURE_COLUMNS) == MODEL_CONFIG['input_size'], (
    'FEATURE_COLUMNS 长度必须等于 MODEL_CONFIG.input_size，'
    f'当前 {len(FEATURE_COLUMNS)} != {MODEL_CONFIG["input_size"]}'
)


class FeatureExtractor:
    """特征提取器"""

    def __init__(self, carbon_factor: Optional[float] = None):
        """
        Parameters
        ----------
        carbon_factor : 电力碳排因子(kgCO2/kWh)，默认用 config.CARBON_FACTORS['electricity']
        """
        self.carbon_factor = (
            carbon_factor if carbon_factor is not None else CARBON_FACTORS['electricity']
        )

    def extract(
        self,
        df: pd.DataFrame,
        window: int = 10,
    ) -> pd.DataFrame:
        """
        主入口：提取全部特征。

        Parameters
        ----------
        df : 清洗后的 DataFrame（含 timestamp / power / energy / load_rate 等）
        window : 滑窗统计的窗口大小，默认 10 分钟

        Returns
        -------
        特征 DataFrame，新增以下列：
            energy_diff, carbon_emission, power_change_rate
            load_rate_mean / std / max / min / slope（滑窗统计）
            power_mean / std / max / min / slope
        """
        if df.empty:
            return df.copy()

        df = df.copy()
        df = self.energy_features(df)
        df = self.carbon_features(df)
        df = self.statistical_features(df, window=window)
        df = self.equipment_health_features(df, window=window)
        return df

    # ---------------- 能耗特征 ----------------
    def energy_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        能耗特征：
            energy_diff         能耗增量（每分钟 kWh），用 diff
            power_change_rate   功率变化率（kW/min）
        """
        df = df.copy()
        if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
            group = df.groupby('equipment_id')
            df['energy_diff'] = group['energy'].diff().fillna(0)
            df['power_change_rate'] = group['power'].diff().fillna(0)
        else:
            df['energy_diff'] = df['energy'].diff().fillna(0)
            df['power_change_rate'] = df['power'].diff().fillna(0)
        # 防止 diff 出现异常值
        df['energy_diff'] = df['energy_diff'].clip(lower=0)
        return df

    # ---------------- 碳排特征 ----------------
    def carbon_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        碳排特征：
            carbon_emission  实时碳排 (kgCO2/min) = power(kW) * (1/60) * factor
        推理：1 分钟 = 1/60 小时，所以 power(kW) * (1/60 h) * 0.5810 = kgCO2/min
        """
        df = df.copy()
        if 'power' not in df.columns:
            df['carbon_emission'] = 0.0
            return df
        # power(kW) × 1/60 (h) × factor(kgCO2/kWh)
        df['carbon_emission'] = (df['power'] / 60.0 * self.carbon_factor).round(4)
        return df

    # ---------------- 滑窗统计 ----------------
    def statistical_features(
        self,
        df: pd.DataFrame,
        window: int = 10,
    ) -> pd.DataFrame:
        """
        滑窗统计：对 load_rate 和 power 计算过去 N 步的
            均值 / 标准差 / 最大 / 最小 / 斜率（线性回归斜率近似）
        """
        df = df.copy()
        base_cols = ['load_rate', 'power']
        for col in base_cols:
            if col not in df.columns:
                continue
            if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
                g = df.groupby('equipment_id')[col]
            else:
                g = df[col]
            df[f'{col}_mean'] = g.transform(lambda s: s.rolling(window, min_periods=1).mean())
            df[f'{col}_std'] = g.transform(lambda s: s.rolling(window, min_periods=1).std().fillna(0))
            df[f'{col}_max'] = g.transform(lambda s: s.rolling(window, min_periods=1).max())
            df[f'{col}_min'] = g.transform(lambda s: s.rolling(window, min_periods=1).min())
            df[f'{col}_slope'] = g.transform(lambda s: self._rolling_slope(s, window))
        return df

    @staticmethod
    def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
        """滑动窗口内的线性斜率（近似：用末值-初值除以窗口长度）"""
        x = np.arange(window, dtype=float)
        if len(x) < 2:
            return pd.Series(np.zeros(len(series)), index=series.index)

        def _slope(arr: np.ndarray) -> float:
            if len(arr) < 2:
                return 0.0
            return float((arr[-1] - arr[0]) / (len(arr) - 1))

        return series.rolling(window, min_periods=2).apply(_slope, raw=True).fillna(0)

    # ---------------- 设备健康特征 ----------------
    def equipment_health_features(
        self,
        df: pd.DataFrame,
        window: int = 10,
    ) -> pd.DataFrame:
        """
        设备健康特征：
            temp_change_rate   温升率 (℃/min)
            vibration_trend    振动趋势
            load_volatility    负载波动（std）
        """
        df = df.copy()
        if 'temperature' in df.columns:
            if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
                df['temp_change_rate'] = df.groupby('equipment_id')['temperature'] \
                    .diff().fillna(0)
            else:
                df['temp_change_rate'] = df['temperature'].diff().fillna(0)
        if 'vibration' in df.columns:
            if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
                df['vibration_trend'] = df.groupby('equipment_id')['vibration'] \
                    .transform(lambda s: s.rolling(window, min_periods=1).mean())
            else:
                df['vibration_trend'] = df['vibration'].rolling(window, min_periods=1).mean()
        if 'load_rate' in df.columns:
            if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
                df['load_volatility'] = df.groupby('equipment_id')['load_rate'] \
                    .transform(lambda s: s.rolling(window, min_periods=1).std().fillna(0))
            else:
                df['load_volatility'] = df['load_rate'].rolling(window, min_periods=1).std().fillna(0)
        return df

    # ---------------- 设备健康评分 ----------------
    @staticmethod
    def equipment_health_score(df: pd.DataFrame) -> pd.Series:
        """
        设备健康评分 (0-100)：综合温度、振动、能效衰减。
        后端可在仪表盘展示，越接近100越健康。
        """
        if df.empty:
            return pd.Series(dtype=float)
        score = pd.Series(np.full(len(df), 100.0), index=df.index)
        if 'temperature' in df.columns:
            temp_pen = (df['temperature'] - 50).clip(lower=0) * 0.5
            score -= temp_pen.fillna(0)
        if 'vibration' in df.columns:
            vib_pen = (df['vibration'] - 2).clip(lower=0) * 5
            score -= vib_pen.fillna(0)
        if 'load_rate' in df.columns and 'power' in df.columns:
            # 负载过低扣分（设备空载）
            low_load_pen = (0.4 - df['load_rate'].fillna(0.4)).clip(lower=0) * 50
            score -= low_load_pen
        return score.clip(lower=0, upper=100).round(2)
