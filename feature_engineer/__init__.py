"""
feature_engineer —— 数据与特征工程包

包含四个核心类，组成数据处理流水线：
    DataLoader        : 加载 CSV / 按设备/时间范围查询原始时序数据
    DataCleaner       : 缺失值填充 / 异常值剔除 / 时间对齐 / 班次标记
    FeatureExtractor  : 提取 8 维模型输入特征 + 滑窗统计特征 + 碳排特征
    SequenceBuilder   : 切成 LSTM 输入序列 (N, 60, 8) + 训练/测试划分 + 归一化

后端同学：本包是算法侧与原始数据之间的隔离层，
        后端只要把数据库查出的时序数据拼成下面这个统一 DataFrame 格式，
        直接喂给 DataLoader / DataCleaner 即可，无需关心内部细节。
"""

from feature_engineer.data_loader import DataLoader
from feature_engineer.data_cleaner import DataCleaner
from feature_engineer.feature_extractor import FeatureExtractor
from feature_engineer.sequence_builder import SequenceBuilder

__all__ = ['DataLoader', 'DataCleaner', 'FeatureExtractor', 'SequenceBuilder']
