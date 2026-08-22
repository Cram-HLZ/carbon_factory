"""
anomaly_detector —— 异常检测器

核心类：AnomalyDetector
    根据重建误差 + 阈值策略，输出异常检测结果。

【阈值策略】
    adaptive（默认）：用过去 adaptive_window 小时（默认 24h）的重建误差
                    均值 + sigma_multiplier(默认3) × 标准差 作为告警线
    fixed：固定阈值 fixed_threshold（默认 0.5）

【严重程度分级】
    score = error / threshold
    score > 2.0 → high
    score > 1.5 → medium
    score > 1.0 → low
    score ≤ 1.0 → normal

【告警冷却】
    同一设备在 alert_cooldown_seconds（默认 600s=10min）内只告警一次，
    避免短时间内重复推送给前端。

后端同学：api_server.services.detect_anomaly 调用本类，
        告警冷却基线数据保存在内存 dict 中（开发期），
        生产环境可换成 Redis（替换 update_baseline 的存储后端即可）。
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Optional

import numpy as np

from config.settings import EQUIPMENT_LIST, THRESHOLD_CONFIG


class AnomalyDetector:
    """异常检测器"""

    def __init__(self, threshold_config: Optional[Dict] = None):
        """
        Parameters
        ----------
        threshold_config : THRESHOLD_CONFIG 字典，不传则用默认
        """
        config = dict(THRESHOLD_CONFIG if threshold_config is None else threshold_config)
        self.method = config.get('method', 'adaptive')
        self.fixed_threshold = config.get('fixed_threshold', 0.5)
        self.adaptive_window = config.get('adaptive_window', 24)
        self.sigma_multiplier = config.get('sigma_multiplier', 3.0)
        self.alert_cooldown = config.get('alert_cooldown_seconds', 600)

        # 自适应基线：每个设备一条 deque，存最近 N 个误差样本
        # N = adaptive_window * 60（1 分钟 1 个样本）
        self._baseline_capacity = max(self.adaptive_window * 60, 100)
        self._baselines: Dict[str, Deque[float]] = {}
        # 告警冷却时间戳：equipment_id → 上次告警的 unix 时间
        self._last_alert_ts: Dict[str, float] = {}

    # ---------------- 基线管理 ----------------
    def update_baseline(self, errors: List[float], equipment_id: str) -> None:
        """把历史误差数组喂给基线（设备级独立）"""
        if equipment_id not in self._baselines:
            self._baselines[equipment_id] = deque(
                maxlen=self._baseline_capacity
            )
        dq = self._baselines[equipment_id]
        for e in errors:
            dq.append(float(e))

    def append_error(self, error: float, equipment_id: str) -> None:
        """追加单条误差到基线"""
        if equipment_id not in self._baselines:
            self._baselines[equipment_id] = deque(maxlen=self._baseline_capacity)
        self._baselines[equipment_id].append(float(error))

    # ---------------- 阈值计算 ----------------
    def get_adaptive_threshold(self, equipment_id: str) -> float:
        """计算设备级自适应阈值：mean + N × sigma"""
        dq = self._baselines.get(equipment_id)
        if not dq or len(dq) < 5:
            # 基线不足时退化为固定阈值
            return self.fixed_threshold
        arr = np.array(dq)
        mu = arr.mean()
        sigma = arr.std(ddof=0)
        threshold = mu + self.sigma_multiplier * sigma
        # 下限保护：阈值不能过低（否则小波动就误报）
        return max(threshold, self.fixed_threshold * 0.1)

    def get_threshold(self, equipment_id: str) -> tuple:
        """返回 (阈值, 阈值类型)"""
        if self.method == 'fixed':
            return self.fixed_threshold, 'fixed'
        return self.get_adaptive_threshold(equipment_id), 'adaptive'

    # ---------------- 检测主流程 ----------------
    def detect(
        self,
        reconstruction_error: float,
        equipment_id: str,
        timestamp: Optional[datetime] = None,
    ) -> Dict:
        """
        判断单条样本是否异常，返回结构化检测结果。

        Parameters
        ----------
        reconstruction_error : 重建误差（MSE）
        equipment_id : 设备 ID（用于查基线 + 告警冷却）
        timestamp : 异常发生时间，默认当前时间

        Returns
        -------
        dict，含 is_anomaly / severity / threshold / anomaly_score 等
        """
        ts = timestamp or datetime.now()
        threshold, threshold_type = self.get_threshold(equipment_id)

        # anomaly_score = 误差 / 阈值（>1 即异常）
        score = reconstruction_error / threshold if threshold > 0 else 0.0
        is_anomaly = score > 1.0

        severity = self._classify_severity(score)

        # 把当前误差喂回基线（注意：异常样本不进基线，避免污染）
        if not is_anomaly:
            self.append_error(reconstruction_error, equipment_id)

        # 告警冷却判断
        should_alert = self.should_alert(equipment_id, is_anomaly)

        result = {
            'is_anomaly': bool(is_anomaly),
            'reconstruction_error': round(float(reconstruction_error), 6),
            'threshold': round(float(threshold), 6),
            'threshold_type': threshold_type,
            'anomaly_score': round(float(score), 4),
            'equipment_id': equipment_id,
            'equipment_name': self._equipment_name(equipment_id),
            'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S'),
            'severity': severity,
            'should_alert': should_alert,
        }
        return result

    # ---------------- 告警冷却 ----------------
    def should_alert(self, equipment_id: str, is_anomaly: bool) -> bool:
        """
        判断是否应该发告警：仅在异常 & 冷却窗口外 才返回 True。

        策略：
            is_anomaly=False → 直接 False
            is_anomaly=True  → 检查距上次告警是否超过冷却时间
                              是 → 记录当前时间，返回 True
                              否 → 返回 False（短时间内重复）
        """
        if not is_anomaly:
            return False
        now = time.time()
        last = self._last_alert_ts.get(equipment_id, 0.0)
        if now - last >= self.alert_cooldown:
            self._last_alert_ts[equipment_id] = now
            return True
        return False

    # ---------------- 内部工具 ----------------
    @staticmethod
    def _classify_severity(score: float) -> str:
        """根据 score（误差/阈值）分级"""
        if score > 2.0:
            return 'high'
        if score > 1.5:
            return 'medium'
        if score > 1.0:
            return 'low'
        return 'normal'

    @staticmethod
    def _equipment_name(equipment_id: str) -> str:
        info = EQUIPMENT_LIST.get(equipment_id)
        return info['name'] if info else equipment_id
