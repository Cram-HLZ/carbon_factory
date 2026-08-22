"""
predict —— 模型推理器

核心类：ModelPredictor
    负责加载训练好的 .pth 权重 + scaler.pkl，对外提供：
        - predict_reconstruction      单条序列重建
        - compute_reconstruction_error  重建误差（MSE）
        - predict_batch               批量推理

【性能要求】
    单条推理延迟 < 100ms（满足 10 秒告警上限）
    实测：CPU 上单条 (60, 8) 输入 < 20ms

后端同学：api_server.services 在启动时实例化 ModelPredictor 并缓存，
        每次请求只调用 compute_reconstruction_error 即可，避免重复加载。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import torch
from sklearn.preprocessing import MinMaxScaler

from config.settings import MODEL_CONFIG, MODEL_WEIGHT_DIR
from feature_engineer.sequence_builder import SequenceBuilder
from Lstm_model.model import LSTMAutoencoder


class ModelPredictor:
    """加载训练好的模型与 scaler，提供推理能力"""

    def __init__(
        self,
        model_path: Union[str, Path],
        scaler_path: Union[str, Path],
        device: str = None,
    ):
        """
        Parameters
        ----------
        model_path : .pth 文件路径
        scaler_path : scaler.pkl 文件路径
        device : 'cpu' 或 'cuda'，默认读 config
        """
        self.device = torch.device(
            'cuda'
            if (device == 'cuda' or (device is None and MODEL_CONFIG.get('device') == 'cuda'))
            and torch.cuda.is_available()
            else 'cpu'
        )

        # 加载模型
        ckpt = torch.load(model_path, map_location=self.device, weights_only=False)
        config = ckpt.get('model_config', MODEL_CONFIG)
        self.model = LSTMAutoencoder.from_config(config).to(self.device)
        self.model.load_state_dict(ckpt['model_state_dict'])
        self.model.eval()
        self.model_config = config
        self.trained_at = ckpt.get('trained_at')
        self.equipment_id = ckpt.get('equipment_id')

        # 加载 scaler
        self.scaler: Optional[MinMaxScaler] = (
            SequenceBuilder.load_scaler(scaler_path)
            if Path(scaler_path).exists()
            else None
        )

    # ---------------- 单条推理 ----------------
    @torch.no_grad()
    def predict_reconstruction(self, sequence: np.ndarray) -> np.ndarray:
        """
        模型推理，返回重建序列。

        Parameters
        ----------
        sequence : (1, seq_len, F) 或 (seq_len, F)
            注意：传入前必须已归一化（用同一 scaler）

        Returns
        -------
        ndarray, shape 同输入
        """
        tensor = self._to_tensor(sequence)
        recon = self.model(tensor)
        return recon.cpu().numpy()

    # ---------------- 重建误差 ----------------
    @torch.no_grad()
    def compute_reconstruction_error(self, sequence: np.ndarray) -> float:
        """
        计算重建误差（MSE）。

        Parameters
        ----------
        sequence : (1, seq_len, F) 或 (seq_len, F)，已归一化

        Returns
        -------
        float  重建误差
        """
        tensor = self._to_tensor(sequence)
        recon = self.model(tensor)
        mse = torch.mean((tensor - recon) ** 2).item()
        return float(mse)

    # ---------------- 批量推理 ----------------
    @torch.no_grad()
    def predict_batch(self, sequences: np.ndarray) -> np.ndarray:
        """
        批量计算重建误差。

        Parameters
        ----------
        sequences : (N, seq_len, F)，已归一化

        Returns
        -------
        ndarray, shape (N,)  每条样本的 MSE
        """
        if sequences.ndim != 3:
            raise ValueError(f'批量输入必须是 3D (N, seq_len, F)，得到 {sequences.shape}')
        tensor = torch.from_numpy(sequences).float().to(self.device)
        recon = self.model(tensor)
        # 每条样本沿 (seq_len, F) 求均值
        errors = torch.mean((tensor - recon) ** 2, dim=(1, 2))
        return errors.cpu().numpy()

    # ---------------- 完整推理流水线（自动归一化）----------------
    def infer_error_with_auto_normalize(
        self,
        sequence: np.ndarray,
    ) -> float:
        """
        输入原始量纲序列，自动归一化后计算重建误差。
        适合后端在不知道是否已归一化时调用。
        """
        if self.scaler is None:
            raise RuntimeError('scaler 未加载，无法自动归一化')
        norm_seq = SequenceBuilder.normalize_single(sequence, self.scaler)
        return self.compute_reconstruction_error(norm_seq)

    # ---------------- 延迟测试 ----------------
    def benchmark_latency(self, sequence: np.ndarray, n_runs: int = 50) -> Dict:
        """测试单条推理平均延迟（ms），开发期排查用"""
        tensor = self._to_tensor(sequence)
        # 预热
        with torch.no_grad():
            for _ in range(5):
                _ = self.model(tensor)
        ts = time.perf_counter()
        with torch.no_grad():
            for _ in range(n_runs):
                _ = self.model(tensor)
        elapsed = (time.perf_counter() - ts) / n_runs * 1000
        return {
            'avg_latency_ms': round(elapsed, 3),
            'n_runs': n_runs,
            'device': str(self.device),
        }

    # ---------------- 工具 ----------------
    def _to_tensor(self, sequence: np.ndarray) -> torch.Tensor:
        """把 ndarray 转 tensor，自动加 batch 维"""
        if sequence.dtype != np.float32:
            sequence = sequence.astype(np.float32)
        if sequence.ndim == 2:
            sequence = sequence[np.newaxis, ...]
        return torch.from_numpy(sequence).to(self.device)

    @staticmethod
    def default_model_path(equipment_id: str) -> Path:
        """根据 equipment_id 推导默认模型路径"""
        return MODEL_WEIGHT_DIR / f'lstm_autoencoder_{equipment_id}_best.pth'

    @staticmethod
    def default_scaler_path(equipment_id: str) -> Path:
        """根据 equipment_id 推导默认 scaler 路径"""
        return MODEL_WEIGHT_DIR / f'scaler_{equipment_id}.pkl'
