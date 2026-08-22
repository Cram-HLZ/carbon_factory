"""
model —— LSTM 自编码器模型定义

架构：
    输入序列 (batch, seq_len=60, input_size=8)
        ↓ Encoder LSTM(2层, hidden=128, bidirectional=False)
        ↓ 取最后时刻隐向量 (batch, hidden)
        ↓ RepeatVector(60)  ← 把隐向量复制成序列
        ↓ Decoder LSTM(2层, hidden=128)
        ↓ Linear(hidden, output_size=8)
        ↓ 输出序列 (batch, seq_len=60, output_size=8)

要点：
    - 自编码器：y = X（输入即输出），学习"重建"正常模式
    - 推理时用重建误差（MSE）作为异常分数
    - dropout=0.2 在两层 LSTM 之间生效
"""

from __future__ import annotations

from typing import Dict

import torch
import torch.nn as nn


class LSTMAutoencoder(nn.Module):
    """LSTM 自编码器"""

    def __init__(
        self,
        input_size: int = 8,
        hidden_size: int = 128,
        num_layers: int = 2,
        output_size: int = 8,
        dropout: float = 0.2,
    ):
        """
        Parameters
        ----------
        input_size   : 输入特征维度（对应 feature_extractor.FEATURE_COLUMNS）
        hidden_size  : LSTM 隐藏层维度
        num_layers   : LSTM 层数（Encoder 和 Decoder 各 num_layers 层）
        output_size  : 输出维度（= input_size，重建输入）
        dropout      : LSTM 层间 dropout
        """
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.output_size = output_size

        # Encoder：双向关闭，batch_first=True，输入 (B, T, F)
        self.encoder = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        # 把编码隐向量再变回序列（RepeatVector 的 PyTorch 实现）
        self.repeat_dim = 60  # 默认 seq_len=60，运行时会用 forward 时的实际长度
        # Decoder：输入是 RepeatVector 后的 (B, T, hidden)
        self.decoder = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        # 把 decoder 输出映射到 output_size
        self.output_layer = nn.Linear(hidden_size, output_size)

    # ---------------- 前向传播 ----------------
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        前向传播，重建输入。

        Parameters
        ----------
        x : (batch, seq_len, input_size)

        Returns
        -------
        reconstruction : (batch, seq_len, output_size)
        """
        batch_size, seq_len, _ = x.shape
        # Encoder：取最后一个时间步的隐向量作为瓶颈
        _, (h_n, _) = self.encoder(x)
        # h_n shape: (num_layers, batch, hidden)，取最后一层
        bottleneck = h_n[-1].unsqueeze(1)  # (batch, 1, hidden)
        # RepeatVector：复制成 (batch, seq_len, hidden)
        repeated = bottleneck.repeat(1, seq_len, 1)
        # Decoder
        dec_out, _ = self.decoder(repeated)
        # 投影到 output_size
        out = self.output_layer(dec_out)
        return out

    # ---------------- 编码 ----------------
    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """编码为瓶颈隐向量 (batch, hidden_size)"""
        _, (h_n, _) = self.encoder(x)
        return h_n[-1]

    # ---------------- 解码 ----------------
    def decode(self, h: torch.Tensor, seq_len: int) -> torch.Tensor:
        """
        解码重建序列。

        Parameters
        ----------
        h        : (batch, hidden_size) 瓶颈向量
        seq_len  : 重建序列长度
        """
        repeated = h.unsqueeze(1).repeat(1, seq_len, 1)
        dec_out, _ = self.decoder(repeated)
        return self.output_layer(dec_out)

    # ---------------- 模型信息 ----------------
    def get_config(self) -> Dict:
        """返回模型配置，便于训练脚本保存到 checkpoint"""
        return {
            'input_size': self.input_size,
            'hidden_size': self.hidden_size,
            'num_layers': self.num_layers,
            'output_size': self.output_size,
            'dropout': self.encoder.dropout if hasattr(self.encoder, 'dropout') else 0.0,
        }

    @classmethod
    def from_config(cls, config: Dict) -> 'LSTMAutoencoder':
        """从配置字典构造模型（加载 checkpoint 时用）"""
        return cls(
            input_size=config['input_size'],
            hidden_size=config['hidden_size'],
            num_layers=config['num_layers'],
            output_size=config['output_size'],
            dropout=config.get('dropout', 0.2),
        )
