"""
data_loader —— 时序数据加载层

核心类：DataLoader
    提供 CSV 加载、按 equipment_id + 时间范围 加载单台 / 批量设备数据，
    以及按层级（factory / workshop / equipment / team）聚合查询的入口。

【统一 DataFrame 格式】所有下游模块（清洗 / 特征提取 / 序列构建）都依赖该格式：
    timestamp        datetime  时间戳（分钟级）
    equipment_id     str       设备唯一编号，如 'C-3-01'、'I-9-01'、'COMP-01'
    equipment_type   str       设备类型标识，共12类，见 config.EQUIPMENT_TYPES
    workshop_id      str       所属车间编号 WS-01 ~ WS-05
    team_id          str       所属班组编号 TEAM-A / TEAM-B / TEAM-C
    voltage          float     电压 (V)
    current          float     电流 (A)
    power            float     有功功率 (kW)
    energy           float     累计能耗 (kWh)
    load_rate        float     负载率 (0-1)
    temperature      float     设备温度 (℃)
    vibration        float     振动值 (mm/s)
    runtime_hours    float     累计运行时长 (h)
    status           int       运行状态：1=运行, 0=停机, 2=待机

后端同学接入真实数据库时，只需要保证从你那查出来的字段顺序/名称与上面一致即可，
建议实现一个 SqlDataLoader 子类继承 DataLoader 并重写 load_equipment_data。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

from config.settings import (
    EQUIPMENT_LIST,
    EQUIPMENT_TYPES,
    HIERARCHY_LEVELS,
    RAW_DATA_DIR,
    WORKSHOPS,
)


# 统一 DataFrame 的列定义（顺序也作为 load_csv 的列校验依据）
UNIFIED_COLUMNS = [
    'timestamp',
    'equipment_id',
    'equipment_type',
    'workshop_id',
    'team_id',
    'voltage',
    'current',
    'power',
    'energy',
    'load_rate',
    'temperature',
    'vibration',
    'runtime_hours',
    'status',
]


class DataLoader:
    """时序数据加载器，所有数据访问都走这个类，方便后续接入数据库"""

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        """
        Parameters
        ----------
        data_dir : str | Path | None
            CSV 根目录，默认使用 config.settings.RAW_DATA_DIR
        """
        self.data_dir = Path(data_dir) if data_dir else RAW_DATA_DIR

    # ---------------- 基础加载 ----------------
    def load_csv(self, file_path: Union[str, Path]) -> pd.DataFrame:
        """
        加载单个 CSV 文件，并保证列结构与 UNIFIED_COLUMNS 一致。

        Parameters
        ----------
        file_path : 文件路径，绝对路径或相对 self.data_dir 的相对路径

        Returns
        -------
        DataFrame，timestamp 解析为 datetime，缺失字段自动补 NaN
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.data_dir / path
        if not path.exists():
            raise FileNotFoundError(f'数据文件不存在: {path}')

        df = pd.read_csv(path)
        # 解析时间列
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        # 校验并补齐统一列
        for col in UNIFIED_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[UNIFIED_COLUMNS]

    # ---------------- 单设备查询 ----------------
    def load_equipment_data(
        self,
        equipment_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        file_path: Optional[Union[str, Path]] = None,
    ) -> pd.DataFrame:
        """
        加载指定设备在指定时间范围内的时序数据。

        Parameters
        ----------
        equipment_id : 设备唯一编号，如 'I-9-01'
        start_time, end_time : 时间范围过滤（含），None 表示不过滤
        file_path : 指定 CSV 文件；不传则扫描 self.data_dir 下所有 csv
        """
        if equipment_id not in EQUIPMENT_LIST:
            raise ValueError(
                f'未知 equipment_id: {equipment_id}，请检查 config.EQUIPMENT_LIST'
            )

        # 装载候选数据
        if file_path is not None:
            df = self.load_csv(file_path)
        else:
            frames = []
            for csv_path in sorted(self.data_dir.glob('*.csv')):
                try:
                    frames.append(self.load_csv(csv_path))
                except Exception:
                    # 容错：跳过损坏的 CSV，避免一个文件挂导致整体不可用
                    continue
            if not frames:
                return pd.DataFrame(columns=UNIFIED_COLUMNS)
            df = pd.concat(frames, ignore_index=True)

        df = df[df['equipment_id'] == equipment_id].copy()
        if df.empty:
            return df

        # 时间范围过滤
        if start_time is not None:
            df = df[df['timestamp'] >= pd.Timestamp(start_time)]
        if end_time is not None:
            df = df[df['timestamp'] <= pd.Timestamp(end_time)]

        return df.sort_values('timestamp').reset_index(drop=True)

    # ---------------- 批量查询 ----------------
    def load_batch_data(
        self,
        equipment_ids: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        file_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        批量加载多设备数据，返回 {equipment_id: DataFrame}。

        后端联调建议：若你后端数据库一次能查出多设备数据，
        可以直接调用 DataLoader._enforce_schema 把 DataFrame 转为统一格式，
        然后构造 dict 返回，避免重复扫盘。
        """
        result: Dict[str, pd.DataFrame] = {}
        for eq_id in equipment_ids:
            result[eq_id] = self.load_equipment_data(
                eq_id, start_time, end_time, file_path
            )
        return result

    # ---------------- 层级聚合查询 ----------------
    def load_hierarchy_data(
        self,
        level: str,
        node_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        file_path: Optional[Union[str, Path]] = None,
    ) -> pd.DataFrame:
        """
        按层级聚合加载数据。

        Parameters
        ----------
        level : 'factory' / 'workshop' / 'equipment' / 'team'
            factory      : 全厂数据（node_id 忽略）
            workshop     : 指定车间（node_id=WS-01）全部设备
            equipment    : 单台设备（node_id=equipment_id）
            team         : 指定班组（node_id=TEAM-A）全部设备
        node_id : 节点 ID，level=factory 时忽略
        start_time, end_time : 时间范围过滤
        file_path : 指定 CSV 文件
        """
        if level not in HIERARCHY_LEVELS:
            raise ValueError(
                f'level 必须是 {HIERARCHY_LEVELS} 之一，得到 {level}'
            )

        # 装载基础数据
        if file_path is not None:
            df = self.load_csv(file_path)
        else:
            frames = []
            for csv_path in sorted(self.data_dir.glob('*.csv')):
                try:
                    frames.append(self.load_csv(csv_path))
                except Exception:
                    continue
            df = (
                pd.concat(frames, ignore_index=True)
                if frames
                else pd.DataFrame(columns=UNIFIED_COLUMNS)
            )

        if df.empty:
            return df

        # 时间过滤
        if start_time is not None:
            df = df[df['timestamp'] >= pd.Timestamp(start_time)]
        if end_time is not None:
            df = df[df['timestamp'] <= pd.Timestamp(end_time)]

        # 层级过滤
        if level == 'factory':
            return df.reset_index(drop=True)
        if level == 'workshop':
            if node_id is None or node_id not in WORKSHOPS:
                raise ValueError(f'workshop 需要 node_id 取自 WORKSHOPS: {node_id}')
            return df[df['workshop_id'] == node_id].reset_index(drop=True)
        if level == 'team':
            target_eqs = [
                eq_id
                for eq_id, info in EQUIPMENT_LIST.items()
                if info['team_id'] == node_id
            ]
            return df[df['equipment_id'].isin(target_eqs)].reset_index(drop=True)
        # equipment
        if node_id is None or node_id not in EQUIPMENT_LIST:
            raise ValueError(f'equipment 需要 node_id 取自 EQUIPMENT_LIST: {node_id}')
        return df[df['equipment_id'] == node_id].reset_index(drop=True)

    # ---------------- 工具方法 ----------------
    @staticmethod
    def _enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
        """把外部 DataFrame 规整为统一 schema（后端可调用）"""
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        for col in UNIFIED_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[UNIFIED_COLUMNS]

    @staticmethod
    def list_equipment_ids() -> List[str]:
        """列出所有设备 ID（开发期排查用）"""
        return list(EQUIPMENT_LIST.keys())

    @staticmethod
    def list_equipment_types() -> List[str]:
        """列出所有设备类型"""
        return list(EQUIPMENT_TYPES.keys())
