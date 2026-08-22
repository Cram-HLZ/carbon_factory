"""
Lstm_model —— LSTM 异常检测模型包

包含：
    LSTMAutoencoder  : LSTM 自编码器模型定义（PyTorch）
    AnomalyDetector  : 自适应阈值 + 告警冷却
    ModelPredictor   : 加载模型 + 推理 + 重建误差
    （train.py / evaluate.py 为脚本，不在此处导出）

【为什么选 LSTM 自编码器】
    1. 无需标注异常数据，正常数据训练即可
    2. 重建误差大的样本视为异常，符合"偏离正常模式即异常"的直觉
    3. LSTM 适合时序数据，能学到负载/温度的动态规律

后端同学：你不需要直接 import 本包的类，所有能力都通过 /api/v1/anomaly/detect 暴露。
        本包主要用于模型训练与离线评估，部署时由 api_server.services 调用。
"""

from Lstm_model.model import LSTMAutoencoder
from Lstm_model.anomaly_detector import AnomalyDetector
from Lstm_model.predict import ModelPredictor

__all__ = ['LSTMAutoencoder', 'AnomalyDetector', 'ModelPredictor']
