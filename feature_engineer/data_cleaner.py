"""
data_cleaner —— 时序数据清洗

核心类：DataCleaner
    一次性入口：clean(df) 自动跑完缺失值/异常值/时间对齐/时间特征四步。

【清洗原则】
    1. 缺失值：时序数据优先线性插值；极端缺失用设备同时段均值兜底
    2. 异常值：3σ 原则，超出均值±3σ 的样本用前后相邻均值替换
    3. 时间对齐：重采样到 1 分钟，保证 LSTM 输入等间隔
    4. 班次标记：按 timestamp.hour 划分 shift 列（早班/中班/夜班）
       —— 后端做排班对比时可以直接按 shift 分组聚合

后端同学：如果你的数据库已经做过部分清洗，可以单独调用某个子方法
        （如 add_time_features）补齐所需字段。
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import numpy as np
import pandas as pd


# 需要做缺失/异常处理的数值列
NUMERIC_COLUMNS = [
    'voltage',
    'current',
    'power',
    'energy',
    'load_rate',
    'temperature',
    'vibration',
    'runtime_hours',
]


class DataCleaner:
    """时序数据清洗器"""

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        主入口：依次执行所有清洗步骤。

        Parameters
        ----------
        df : 原始 DataFrame（必须含 timestamp 列）

        Returns
        -------
        清洗后的 DataFrame，新增 hour / weekday / is_weekend / shift 列
        """
        if df.empty:
            return df.copy()

        df = df.copy()
        # 必须按设备 + 时间排序，否则后续插值/重采样会错乱
        if 'equipment_id' in df.columns:
            df = df.sort_values(['equipment_id', 'timestamp']).reset_index(drop=True)
        else:
            df = df.sort_values('timestamp').reset_index(drop=True)

        df = self.handle_missing_values(df, method='linear')
        df = self.remove_outliers(df, columns=NUMERIC_COLUMNS, method='3sigma')
        df = self.align_time_series(df, freq='1min')
        df = self.add_time_features(df)
        return df

    # ---------------- 缺失值处理 ----------------
    def handle_missing_values(
        self,
        df: pd.DataFrame,
        method: str = 'linear',
    ) -> pd.DataFrame:
        """
        缺失值处理。

        Parameters
        ----------
        method : 'linear' 线性插值（默认，时序数据最常用）
                 'ffill'  前向填充
                 'mean'   均值填充（按设备分组）
        """
        df = df.copy()
        if df.empty:
            return df

        if method == 'linear':
            # 按设备分组线性插值，避免不同设备数据互相污染
            if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
                df[NUMERIC_COLUMNS] = df.groupby('equipment_id')[NUMERIC_COLUMNS] \
                    .transform(lambda g: g.interpolate(method='linear', limit_direction='both'))
            else:
                df[NUMERIC_COLUMNS] = df[NUMERIC_COLUMNS].interpolate(
                    method='linear', limit_direction='both'
                )
        elif method == 'ffill':
            df[NUMERIC_COLUMNS] = df.groupby('equipment_id')[NUMERIC_COLUMNS] \
                .ffill().bfill() if 'equipment_id' in df.columns else df[NUMERIC_COLUMNS].ffill().bfill()
        elif method == 'mean':
            if 'equipment_id' in df.columns:
                df[NUMERIC_COLUMNS] = df.groupby('equipment_id')[NUMERIC_COLUMNS] \
                    .transform(lambda g: g.fillna(g.mean()))
            else:
                df[NUMERIC_COLUMNS] = df[NUMERIC_COLUMNS].fillna(df[NUMERIC_COLUMNS].mean())
        else:
            raise ValueError(f'未知 method: {method}，可选 linear/ffill/mean')

        # status 列单独处理：插值后取整
        if 'status' in df.columns:
            df['status'] = (
                df.groupby('equipment_id')['status'].ffill().bfill()
                if 'equipment_id' in df.columns
                else df['status'].ffill().bfill()
            )
            df['status'] = df['status'].fillna(0).astype(int)

        return df

    # ---------------- 异常值剔除 ----------------
    def remove_outliers(
        self,
        df: pd.DataFrame,
        columns: Iterable[str],
        method: str = '3sigma',
    ) -> pd.DataFrame:
        """
        异常值检测并用前后均值替换。

        Parameters
        ----------
        columns : 要处理的数值列
        method  : '3sigma' 均值±3σ（默认） / 'iqr' 四分位距法
        """
        df = df.copy()
        if df.empty:
            return df

        cols = [c for c in columns if c in df.columns]
        for col in cols:
            if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
                df[col] = df.groupby('equipment_id')[col].transform(
                    lambda g: self._replace_outliers_series(g, method)
                )
            else:
                df[col] = self._replace_outliers_series(df[col], method)
        return df

    @staticmethod
    def _replace_outliers_series(series: pd.Series, method: str) -> pd.Series:
        """对单列做异常值替换：超出边界的点用前后均值替代"""
        s = pd.to_numeric(series, errors='coerce')
        if s.isna().all():
            return series

        if method == '3sigma':
            mu, sigma = s.mean(), s.std(ddof=0)
            if sigma == 0 or np.isnan(sigma):
                return series
            lower, upper = mu - 3 * sigma, mu + 3 * sigma
            mask = (s < lower) | (s > upper)
        elif method == 'iqr':
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            mask = (s < lower) | (s > upper)
        else:
            raise ValueError(f'未知 method: {method}，可选 3sigma/iqr')

        if mask.sum() == 0:
            return series
        # 异常点用前后相邻值的均值替换
        replaced = s.copy()
        replaced[mask] = 0.5 * (s.shift(1) + s.shift(-1))
        # 首尾异常点退化成单侧填充
        replaced[mask & replaced.isna()] = s.bfill()[mask & replaced.isna()]
        return replaced

    # ---------------- 时间对齐 ----------------
    def align_time_series(
        self,
        df: pd.DataFrame,
        freq: str = '1min',
    ) -> pd.DataFrame:
        """
        重采样到固定频率，保证 LSTM 输入等间隔。

        策略：按 equipment_id 分组，把 timestamp 重采样到 freq，
              数值列取均值，状态列取众数，缺失行由下游插值补齐。
        """
        df = df.copy()
        if df.empty or 'timestamp' not in df.columns:
            return df

        df = df.dropna(subset=['timestamp'])
        df = df.set_index('timestamp')

        resampled_frames = []
        if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
            for eq_id, group in df.groupby('equipment_id'):
                resampled_frames.append(self._resample_single(group, freq))
        else:
            resampled_frames.append(self._resample_single(df, freq))

        out = pd.concat(resampled_frames).reset_index()
        return out.sort_values(
            ['equipment_id', 'timestamp'] if 'equipment_id' in out.columns else ['timestamp']
        ).reset_index(drop=True)

    @staticmethod
    def _resample_single(group: pd.DataFrame, freq: str) -> pd.DataFrame:
        """对单台设备数据做重采样"""
        numeric_cols = [c for c in NUMERIC_COLUMNS if c in group.columns]
        agg_dict = {c: 'mean' for c in numeric_cols}
        if 'status' in group.columns:
            agg_dict['status'] = lambda x: x.mode().iloc[0] if not x.mode().empty else 0
        # 字符串列取首值
        for col in ['equipment_id', 'equipment_type', 'workshop_id', 'team_id']:
            if col in group.columns:
                agg_dict[col] = 'first'

        res = group.resample(freq).agg(agg_dict)
        # 重采样后插值补齐（仅数值列）
        if numeric_cols:
            res[numeric_cols] = res[numeric_cols].interpolate(
                method='linear', limit_direction='both'
            )
        for col in ['equipment_id', 'equipment_type', 'workshop_id', 'team_id', 'status']:
            if col in res.columns:
                res[col] = res[col].ffill().bfill()
        return res

    # ---------------- 时间特征 ----------------
    def add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        添加时间特征列：
            hour        小时 0-23
            weekday     星期 0-6（0=周一）
            is_weekend  是否周末（周六/日为1）
            shift       班次：morning(早班8-16) / evening(中班16-24) / night(夜班0-8)
        """
        df = df.copy()
        if df.empty or 'timestamp' not in df.columns:
            return df

        ts = pd.to_datetime(df['timestamp'])
        df['hour'] = ts.dt.hour
        df['weekday'] = ts.dt.weekday
        df['is_weekend'] = (df['weekday'] >= 5).astype(int)
        df['shift'] = df['hour'].apply(self._hour_to_shift)
        return df

    @staticmethod
    def _hour_to_shift(hour: int) -> str:
        """0-7 / 8-15 / 16-23 → 夜/早/中班"""
        if 8 <= hour < 16:
            return 'morning'
        if 16 <= hour < 24:
            return 'evening'
        return 'night'
