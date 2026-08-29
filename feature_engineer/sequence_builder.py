"""
sequence_builder —— LSTM 序列构建

核心类：SequenceBuilder
    把特征 DataFrame 切成 (N, 60, 8) 的训练序列，并保存 scaler 供推理时复用。

【自编码器模式】y = X，模型学习重建正常数据，重建误差大的样本判异常。
【训练/测试划分】按时间顺序前 80% 训练，后 20% 测试（时序数据不能随机打乱）。
【归一化】MinMax 归一化到 [0,1]，scaler 保存到 output/model_weight/scaler.pkl
        推理时必须用同一 scaler，否则重建误差会失真。

后端同学：调用 /api/v1/anomaly/detect 时，前端传的 60×8 矩阵已经是
        归一化后的数据（由后端采集→清洗→特征提取→归一化之后传入）。
        归一化统一用本类的 normalize 方法 + 训练时保存的 scaler。
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Tuple, Union

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from config.settings import MODEL_CONFIG, MODEL_WEIGHT_DIR
from feature_engineer.feature_extractor import FEATURE_COLUMNS


class SequenceBuilder:
    """序列构建器"""

    def __init__(self, sequence_length: int = None):
        """
        Parameters
        ----------
        sequence_length : 序列长度，默认用 config.MODEL_CONFIG['sequence_length']=60
        """
        self.sequence_length = sequence_length or MODEL_CONFIG['sequence_length']
        self.feature_columns = list(FEATURE_COLUMNS)

    # ---------------- 序列构建 ----------------
    def build_sequences(
        self,
        features_df: pd.DataFrame,
        seq_length: int = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        把特征 DataFrame 切成训练序列。

        Parameters
        ----------
        features_df : 特征 DataFrame，必须含 self.feature_columns 列
        seq_length : 序列长度，默认 60

        Returns
        -------
        X : ndarray, shape (N, seq_length, input_size)
        y : ndarray, shape (N, seq_length, input_size)  ← 自编码器 y = X
        """
        seq_len = seq_length or self.sequence_length
        if features_df.empty:
            return np.empty((0, seq_len, len(self.feature_columns))), np.empty(0)

        missing = [c for c in self.feature_columns if c not in features_df.columns]
        if missing:
            raise ValueError(f'features_df 缺少特征列: {missing}')

        # 按设备切序列（避免跨设备拼接）
        if 'equipment_id' in features_df.columns and features_df['equipment_id'].nunique() > 1:
            sequences = []
            for _, group in features_df.groupby('equipment_id'):
                data = group[self.feature_columns].values.astype(np.float32)
                seqs = self._slide_window(data, seq_len)
                if seqs is not None:
                    sequences.append(seqs)
            if not sequences:
                return np.empty((0, seq_len, len(self.feature_columns))), np.empty(0)
            X = np.concatenate(sequences, axis=0)
        else:
            data = features_df[self.feature_columns].values.astype(np.float32)
            X = self._slide_window(data, seq_len)
            if X is None:
                return np.empty((0, seq_len, len(self.feature_columns))), np.empty(0)

        y = X.copy()  # 自编码器：y = X
        return X, y

    @staticmethod
    def _slide_window(data: np.ndarray, seq_length: int) -> np.ndarray:
        """
        滑窗切片：data shape (T, F) → (N, seq_length, F)
        N = T - seq_length + 1，步长=1
        """
        if data.shape[0] < seq_length:
            return None
        n_samples = data.shape[0] - seq_length + 1
        return np.array(
            [data[i:i + seq_length] for i in range(n_samples)],
            dtype=np.float32,
        )

    def build_single_sequence(
        self,
        features_df: pd.DataFrame,
        end_idx: int = None,
        seq_length: int = None,
    ) -> np.ndarray:
        """
        构建单条推理序列（实时预测用）。

        Parameters
        ----------
        features_df : 特征 DataFrame
        end_idx : 序列结束位置（默认取最后一行）
        seq_length : 序列长度，默认 60

        Returns
        -------
        ndarray, shape (1, seq_length, input_size)
        """
        seq_len = seq_length or self.sequence_length
        if end_idx is None:
            end_idx = len(features_df) - 1
        start_idx = end_idx - seq_len + 1
        if start_idx < 0:
            raise ValueError(
                f'features_df 长度 {len(features_df)} 不足以构建长度 {seq_len} 的序列'
            )
        missing = [c for c in self.feature_columns if c not in features_df.columns]
        if missing:
            raise ValueError(f'features_df 缺少特征列: {missing}')

        seq = features_df.iloc[start_idx:end_idx + 1][self.feature_columns].values
        return seq[np.newaxis, ...].astype(np.float32)

    # ---------------- 训练/测试划分 ----------------
    def train_test_split(
        self,
        X: np.ndarray,
        y: np.ndarray,
        test_size: float = 0.2,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        按时间顺序划分训练/测试集（**不能随机打乱**）。

        Parameters
        ----------
        X, y : 序列数据，shape (N, seq_len, F)
        test_size : 测试集比例，默认 0.2

        Returns
        -------
        X_train, X_test, y_train, y_test
        """
        if X.shape[0] == 0:
            return X, X, y, y
        n_total = X.shape[0]
        n_test = max(1, int(n_total * test_size)) if n_total > 1 else 0
        n_train = n_total - n_test
        return (
            X[:n_train], X[n_train:],
            y[:n_train], y[n_train:],
        )

    # ---------------- 归一化 ----------------
    def normalize(
        self,
        X_train: np.ndarray,
        X_test: np.ndarray = None,
        save_path: Union[str, Path] = None,
    ) -> Tuple[np.ndarray, np.ndarray, MinMaxScaler]:
        """
        用 MinMaxScaler 把序列归一化到 [0,1]。

        Parameters
        ----------
        X_train : 训练序列，shape (N1, seq_len, F)
        X_test  : 测试序列，shape (N2, seq_len, F)，可为 None
        save_path : scaler 保存路径，默认 output/model_weight/scaler.pkl

        Returns
        -------
        X_train_norm, X_test_norm, scaler
        """
        if X_train.shape[0] == 0:
            return X_train, (X_test if X_test is not None else np.array([])), None

        # 把 (N, seq_len, F) 摊平成 (N*seq_len, F) 拟合 scaler
        flat_train = X_train.reshape(-1, X_train.shape[-1])
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaler.fit(flat_train)

        X_train_norm = scaler.transform(flat_train).reshape(X_train.shape).astype(np.float32)
        X_test_norm = None
        if X_test is not None and X_test.shape[0] > 0:
            flat_test = X_test.reshape(-1, X_test.shape[-1])
            X_test_norm = scaler.transform(flat_test).reshape(X_test.shape).astype(np.float32)

        if save_path is None:
            # 注意：训练脚本应显式传 scaler_{equipment_id}.pkl（按设备隔离），
            # 这里只提供通用兜底名，避免产生与设备混淆的 scaler.pkl 残留
            save_path = MODEL_WEIGHT_DIR / 'scaler_generic.pkl'
        self.save_scaler(scaler, save_path)

        return X_train_norm, X_test_norm, scaler

    # ---------------- scaler 持久化 ----------------
    @staticmethod
    def save_scaler(scaler: MinMaxScaler, path: Union[str, Path]) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(scaler, f)

    @staticmethod
    def load_scaler(path: Union[str, Path]) -> MinMaxScaler:
        with open(path, 'rb') as f:
            return pickle.load(f)

    # ---------------- 单条序列归一化（推理时用）----------------
    @staticmethod
    def normalize_single(
        sequence: np.ndarray,
        scaler: MinMaxScaler,
    ) -> np.ndarray:
        """
        推理时归一化单条序列。
        sequence : (1, seq_len, F) 或 (seq_len, F)
        """
        squeezed = False
        if sequence.ndim == 3:
            sequence = sequence[0]
            squeezed = True
        flat = sequence.reshape(-1, sequence.shape[-1])
        norm = scaler.transform(flat).reshape(sequence.shape).astype(np.float32)
        if squeezed:
            norm = norm[np.newaxis, ...]
        return norm

    # ---------------- 反归一化（评估可视化时用）----------------
    @staticmethod
    def denormalize(
        sequence: np.ndarray,
        scaler: MinMaxScaler,
    ) -> np.ndarray:
        """反归一化（还原到原始量纲）"""
        flat = sequence.reshape(-1, sequence.shape[-1])
        return scaler.inverse_transform(flat).reshape(sequence.shape)
