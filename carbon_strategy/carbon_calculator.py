"""
carbon_calculator —— 碳排核算

核心类：CarbonCalculator

【四级聚合层级】
    factory   : 厂区级（全部设备 sum）
    workshop  : 车间级（按 workshop_id 分组）
    equipment : 设备级（每台设备每分钟）
    team      : 班组级（按 team_id 分组）

【核算公式】
    设备级碳排 = power(kW) × (1/60 h) × 0.5810(kgCO2/kWh)  ← 单位 kgCO2/min
    累计碳排   = sum(每分钟碳排)
    碳排强度   = 累计碳排 / 产量

【兼容性】
    算法基于 IPCC 2006 + 中国南方电网区域排放因子，
    兼容国标 GB/T 32150 温室气体核算规范（排放因子法）。
    后端做地域切换时，只需改 config.CARBON_FACTORS['electricity']。

后端同学：api_server.services.get_carbon_emission_data 调用本类做聚合。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

from config.settings import (
    CARBON_FACTORS,
    EQUIPMENT_LIST,
    EQUIPMENT_TYPES,
    HIERARCHY_LEVELS,
    WORKSHOPS,
    TEAMS,
)


class CarbonCalculator:
    """碳排核算器"""

    def __init__(self, carbon_factor: Optional[float] = None):
        """
        Parameters
        ----------
        carbon_factor : 电力碳排因子(kgCO2/kWh)，默认 config.CARBON_FACTORS['electricity']
        """
        self.carbon_factor = (
            carbon_factor if carbon_factor is not None else CARBON_FACTORS['electricity']
        )

    # ---------------- 单源换算 ----------------
    def calculate_emission(
        self,
        energy_type: str,
        energy_amount: float,
    ) -> float:
        """
        单一能源碳排换算。

        Parameters
        ----------
        energy_type   : 'electricity' / 'natural_gas' / 'coal' / 'diesel' / 'compressed_air'
        energy_amount : 能源消耗量（单位与能源类型对应）

        Returns
        -------
        碳排量 (kgCO2)，保留 4 位小数
        """
        factor = CARBON_FACTORS.get(energy_type)
        if factor is None:
            raise ValueError(f'未知能源类型: {energy_type}，可选 {list(CARBON_FACTORS.keys())}')
        return round(float(energy_amount) * factor, 4)

    # ---------------- 设备级 ----------------
    def calculate_equipment_emission(self, equipment_data: pd.DataFrame) -> pd.DataFrame:
        """
        给设备时序 DataFrame 添加 carbon_emission 列（kgCO2/min）。

        Parameters
        ----------
        equipment_data : 统一 DataFrame 格式（含 power 列）

        Returns
        -------
        DataFrame，新增 carbon_emission / carbon_emission_cum 两列
        """
        df = equipment_data.copy()
        if df.empty:
            df['carbon_emission'] = []
            df['carbon_emission_cum'] = []
            return df

        if 'power' not in df.columns:
            raise ValueError('设备数据缺少 power 列')

        # 单分钟碳排 = power(kW) × (1/60 h) × factor(kgCO2/kWh)
        df['carbon_emission'] = (df['power'] / 60.0 * self.carbon_factor).round(4)
        # 累计碳排（按设备分组）
        if 'equipment_id' in df.columns and df['equipment_id'].nunique() > 1:
            df['carbon_emission_cum'] = df.groupby('equipment_id')['carbon_emission'].cumsum()
        else:
            df['carbon_emission_cum'] = df['carbon_emission'].cumsum()
        return df

    # ---------------- 聚合入口 ----------------
    def aggregate_by_level(
        self,
        df: pd.DataFrame,
        level: str,
        node_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        按指定层级聚合碳排。

        Parameters
        ----------
        level : 'factory' / 'workshop' / 'equipment' / 'team'
        node_id : 节点 ID（factory 时忽略）
        """
        if level not in HIERARCHY_LEVELS:
            raise ValueError(f'level 必须是 {HIERARCHY_LEVELS} 之一')

        df = self.calculate_equipment_emission(df)
        if df.empty:
            return df

        # 先按 node_id 过滤
        if level == 'factory':
            filtered = df
        elif level == 'workshop':
            filtered = df[df['workshop_id'] == node_id] if node_id else df
        elif level == 'team':
            target_eqs = [
                eq_id for eq_id, info in EQUIPMENT_LIST.items()
                if info['team_id'] == node_id
            ]
            filtered = df[df['equipment_id'].isin(target_eqs)] if node_id else df
        else:  # equipment
            filtered = df[df['equipment_id'] == node_id] if node_id else df

        if filtered.empty:
            return filtered

        if level == 'equipment':
            agg = filtered.groupby(['equipment_id', 'equipment_type']).agg(
                carbon_emission=('carbon_emission', 'sum'),
                energy_consumption=('power', 'mean'),
            ).reset_index()
            agg['energy_consumption'] = (agg['energy_consumption'] * 60 / 1000).round(4)  # kW×min→kWh
            agg['carbon_emission'] = agg['carbon_emission'].round(4)
            return agg

        if level == 'workshop':
            agg = filtered.groupby(['workshop_id']).agg(
                carbon_emission=('carbon_emission', 'sum'),
                energy_consumption=('power', 'sum'),
                equipment_count=('equipment_id', 'nunique'),
            ).reset_index()
            agg['energy_consumption'] = (agg['energy_consumption'] * 60 / 1000).round(4)
            agg['carbon_emission'] = agg['carbon_emission'].round(4)
            agg['workshop_name'] = agg['workshop_id'].map(lambda x: WORKSHOPS.get(x, {}).get('name', x))
            return agg

        if level == 'team':
            agg = filtered.groupby(['team_id']).agg(
                carbon_emission=('carbon_emission', 'sum'),
                energy_consumption=('power', 'sum'),
                equipment_count=('equipment_id', 'nunique'),
            ).reset_index()
            agg['energy_consumption'] = (agg['energy_consumption'] * 60 / 1000).round(4)
            agg['carbon_emission'] = agg['carbon_emission'].round(4)
            agg['team_name'] = agg['team_id'].map(lambda x: TEAMS.get(x, {}).get('name', x))
            return agg

        # factory
        agg = pd.DataFrame([{
            'node_id': 'factory',
            'node_name': '全厂',
            'carbon_emission': round(float(filtered['carbon_emission'].sum()), 4),
            'energy_consumption': round(float(filtered['power'].sum() * 60 / 1000), 4),
            'equipment_count': int(filtered['equipment_id'].nunique()),
        }])
        return agg

    # ---------------- 厂区总览 ----------------
    def aggregate_factory(self, df: pd.DataFrame) -> Dict:
        """
        厂区级汇总：总碳排、趋势、强度、排名。

        Returns
        -------
        dict:
            total_emission         总碳排(kgCO2)
            total_energy           总能耗(kWh)
            by_workshop            车间级排名
            by_team                班组级对比
            by_equipment_top       高碳排设备 Top10
            hourly_trend           按小时聚合的趋势数据（折线图用）
        """
        df = self.calculate_equipment_emission(df)
        if df.empty:
            return {
                'total_emission': 0.0,
                'total_energy': 0.0,
                'by_workshop': [],
                'by_team': [],
                'by_equipment_top': [],
                'hourly_trend': [],
            }

        total_emission = round(float(df['carbon_emission'].sum()), 4)
        total_energy = round(float(df['power'].sum() * 60 / 1000), 4)

        # 按车间
        ws = self.aggregate_by_level(df, 'workshop').sort_values('carbon_emission', ascending=False)
        # 按班组
        tm = self.aggregate_by_level(df, 'team').sort_values('carbon_emission', ascending=False)
        # 按设备 Top10
        eq = self.aggregate_by_level(df, 'equipment').sort_values('carbon_emission', ascending=False).head(10)

        # 按小时趋势（折线图用）
        df_ts = df.copy()
        if 'timestamp' in df_ts.columns:
            df_ts['hour'] = pd.to_datetime(df_ts['timestamp']).dt.floor('H')
            hourly = df_ts.groupby('hour').agg(
                carbon_emission=('carbon_emission', 'sum'),
                energy_consumption=('power', 'sum'),
            ).reset_index()
            hourly['timestamp'] = hourly['hour'].astype(str)
            hourly = hourly[['timestamp', 'carbon_emission', 'energy_consumption']]
        else:
            hourly = pd.DataFrame(columns=['timestamp', 'carbon_emission', 'energy_consumption'])

        return {
            'total_emission': total_emission,
            'total_energy': total_energy,
            'by_workshop': ws.to_dict(orient='records'),
            'by_team': tm.to_dict(orient='records'),
            'by_equipment_top': eq.to_dict(orient='records'),
            'hourly_trend': hourly.to_dict(orient='records'),
        }

    # ---------------- 车间对比 ----------------
    def aggregate_workshop(self, df: pd.DataFrame) -> pd.DataFrame:
        """车间级对比"""
        return self.aggregate_by_level(df, 'workshop')

    # ---------------- 碳排强度 ----------------
    def calculate_carbon_intensity(
        self,
        df: pd.DataFrame,
        production_output: float,
    ) -> float:
        """
        单位产品碳排强度 (kgCO2/件)。

        Parameters
        ----------
        df : 设备时序数据（含 power 列）
        production_output : 同期产量（件/电芯）
        """
        if production_output <= 0:
            return 0.0
        df = self.calculate_equipment_emission(df)
        total = float(df['carbon_emission'].sum()) if not df.empty else 0.0
        return round(total / production_output, 4)

    # ---------------- 热力图数据 ----------------
    def heatmap_data(
        self,
        df: pd.DataFrame,
        agg_col: str = 'equipment_id',
    ) -> List[Dict]:
        """
        生成热力图数据（按设备维度，给前端 CarbonHeatmap 组件）。

        Returns
        -------
        list of dict: {equipment_id, equipment_name, workshop_id, carbon_emission, intensity}
        """
        df = self.calculate_equipment_emission(df)
        if df.empty:
            return []
        agg = df.groupby(['equipment_id', 'workshop_id']).agg(
            carbon_emission=('carbon_emission', 'sum'),
            power_mean=('power', 'mean'),
            runtime=('equipment_id', 'count'),
        ).reset_index()
        agg['equipment_name'] = agg['equipment_id'].map(
            lambda x: EQUIPMENT_LIST.get(x, {}).get('name', x)
        )
        agg['equipment_type'] = agg['equipment_id'].map(
            lambda x: EQUIPMENT_LIST.get(x, {}).get('equipment_type', '')
        )
        # carbon_emission 取整 + power_mean 取整
        agg['carbon_emission'] = agg['carbon_emission'].round(4)
        agg['power_mean'] = agg['power_mean'].round(3)
        return agg.to_dict(orient='records')
