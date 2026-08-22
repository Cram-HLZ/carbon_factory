"""
train —— LSTM 自编码器训练脚本（竞赛答辩版）

================================================================================
【一句话概括】
    给单台设备的历史运行数据"看"30 遍（epochs=30），让 LSTM 自编码器学会
    重建这台设备的"正常运行模式"；训练好的权重存成 .pth，异常检测接口
    启动时自动加载，重建误差越大说明越偏离正常模式 → 判为异常。

================================================================================
【答辩必懂概念】
  1. epochs（训练轮次）
       把全部训练数据完整过一遍 = 1 个 epoch。
       epochs=30 意味着模型把同一批数据反复学习 30 次，
       每次都用反向传播微调神经网络权重，让重建误差越来越小。
       太少学不充分，太多会过拟合（死记硬背训练数据）。

  2. equipment_id（设备唯一编号）
       每台设备单独训练一个模型，因为不同设备的"正常模式"不同：
       烘烤炉(I-9-01)的正常温度 80-130℃，卷绕机(C-3-01)的正常功率 15kW，
       不能共用一个模型。命名规则：{类型编号}-{两位序号}，如 I-9-01。

  3. 输入矩阵 (batch, 60, 8)
       - 60 = 序列长度（sequence_length），用过去 60 分钟的分钟级数据
       - 8  = 特征维度（input_size），依次是：
           [0] load_rate        负载率 (0-1)
           [1] power            有功功率 (kW)
           [2] energy_diff      能耗增量 (kWh/min)
           [3] temperature      设备温度 (℃)
           [4] vibration        振动值 (mm/s)
           [5] carbon_emission  实时碳排 (kgCO2/min)
           [6] power_change_rate 功率变化率
           [7] runtime_hours    累计运行时长 (h)
       每条样本 = 一个 60×8 的矩阵，模型输出也是 60×8（重建输入）。

  4. 自编码器（Autoencoder）为什么能检测异常？
       训练时只喂"正常数据"，模型学会把正常输入重建得很像（误差小）。
       推理时如果输入是异常数据，模型没见过这种模式，重建就会很差
       （误差大）。所以"重建误差 MSE"就是异常分数，超过阈值即告警。

  5. 损失函数 MSELoss
       衡量模型输出与输入的逐元素均方误差，训练目标就是把它降到最小。

================================================================================
【训练产物】
    output/model_weight/lstm_autoencoder_{equipment_id}_best.pth   ← 模型权重
    output/model_weight/scaler_{equipment_id}.pkl                  ← 归一化器
    output/chart/training_curve_{equipment_id}.png                 ← 损失曲线
    output/log/train_{equipment_id}_{时间戳}.log                   ← 训练日志
    output/log/train_history_{equipment_id}.json                   ← 训练历史数据

================================================================================
【一键训练示例设备】
    python -m Lstm_model.train
    # 等价于：python -m Lstm_model.train --equipment_id I-9-01 --epochs 30

【训练其他设备】
    python -m Lstm_model.train --equipment_id COMP-01 --epochs 30
    python -m Lstm_model.train --equipment_id C-3-01 --epochs 50

【训练完成后】
    重启算法服务（python main.py），异常检测接口 /api/v1/anomaly/detect
    会自动检测到 .pth 文件并加载，无需改任何代码。
================================================================================
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config.settings import (
    EQUIPMENT_LIST,
    MODEL_CONFIG,
    MODEL_WEIGHT_DIR,
    CHART_DIR,
    LOG_DIR,
)
from feature_engineer.data_cleaner import DataCleaner
from feature_engineer.data_loader import DataLoader as FeDataLoader
from feature_engineer.feature_extractor import FEATURE_COLUMNS, FeatureExtractor
from feature_engineer.sequence_builder import SequenceBuilder
from Lstm_model.model import LSTMAutoencoder


# ============================================================
# 工具：设备选择（默认训练示例设备 I-9-01 电芯烘烤炉）
# ============================================================
DEFAULT_EQUIPMENT_ID = 'I-9-01'  # 电芯烘烤炉，高耗能重点设备，适合做演示
DEFAULT_EPOCHS = 30


def setup_logger(equipment_id: str) -> logging.Logger:
    """
    配置训练日志：同时输出到控制台 + 文件。
    文件路径：output/log/train_{equipment_id}_{YYYYMMDD_HHMMSS}.log
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = LOG_DIR / f'train_{equipment_id}_{timestamp}.log'

    logger = logging.getLogger(f'train_{equipment_id}')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # 避免重复添加 handler

    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    # 控制台输出
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件输出
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f'训练日志文件 → {log_file}')
    return logger


def get_device(name: str = None) -> torch.device:
    """根据 config 中的 device 名称返回 torch.device（CPU 优先，保证部署兼容）"""
    name = name or MODEL_CONFIG.get('device', 'cpu')
    if name == 'cuda' and torch.cuda.is_available():
        return torch.device('cuda')
    return torch.device('cpu')


# ============================================================
# 数据流水线：CSV → 清洗 → 特征提取 → 序列构建 → 划分 → 归一化
# ============================================================
def prepare_sequences(
    equipment_id: str,
    csv_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, object]:
    """
    完整数据流水线，把原始 CSV 变成模型可吃的 (N, 60, 8) 归一化序列。

    流程（答辩时可按此讲解）：
      ① DataLoader      从 CSV 读出该设备的分钟级原始数据
      ② DataCleaner     去重、缺失值插值、异常值截断
      ③ FeatureExtractor 计算 8 维特征（含碳排、功率变化率等衍生特征）
      ④ SequenceBuilder 滑窗切成 60 分钟一段，y = X（自编码器）
      ⑤ 按时间前 80%/后 20% 划分训练/测试集（时序数据不能随机打乱）
      ⑥ MinMax 归一化到 [0,1]，scaler 存盘供推理时复用

    Returns
    -------
    X_train, X_test, y_train, y_test, scaler
    """
    log = logger or logging.getLogger(__name__)

    # ① 加载原始数据
    loader = FeDataLoader()
    df = loader.load_equipment_data(equipment_id, file_path=csv_path)
    if df.empty:
        raise ValueError(f'设备 {equipment_id} 无可用数据，请检查 CSV 中是否包含该设备')
    log.info(f'① 原始数据: {len(df)} 行，时间范围 {df["timestamp"].min()} ~ {df["timestamp"].max()}')

    # ② 清洗
    cleaner = DataCleaner()
    df_clean = cleaner.clean(df)
    log.info(f'② 清洗后: {len(df_clean)} 行')

    # ③ 特征提取（8 维）
    extractor = FeatureExtractor()
    df_feat = extractor.extract(df_clean)
    log.info(f'③ 特征提取: {len(df_feat)} 行，特征列 = {list(FEATURE_COLUMNS)}')

    # ④ 序列构建（滑窗 60 分钟）
    builder = SequenceBuilder()
    X, y = builder.build_sequences(df_feat)
    if X.shape[0] == 0:
        raise ValueError(f'设备 {equipment_id} 数据不足以构建 60 分钟序列')
    log.info(f'④ 序列构建: {X.shape[0]} 条样本，每条 shape = {X.shape[1:]} (60分钟×8特征)')

    # ⑤ 训练/测试划分（时序顺序，不打乱）
    X_train, X_test, y_train, y_test = builder.train_test_split(X, y, test_size=0.2)
    log.info(f'⑤ 数据集划分: 训练 {X_train.shape[0]} 条 / 测试 {X_test.shape[0]} 条')

    # ⑥ 归一化 + 保存 scaler
    scaler_path = MODEL_WEIGHT_DIR / f'scaler_{equipment_id}.pkl'
    X_train_norm, X_test_norm, scaler = builder.normalize(
        X_train, X_test,
        save_path=scaler_path,
    )
    # 自编码器：目标 = 输入（重建任务）
    y_train_norm = X_train_norm.copy()
    y_test_norm = X_test_norm.copy() if X_test_norm is not None else None
    log.info(f'⑥ 归一化完成，scaler 已保存 → {scaler_path}')

    return X_train_norm, X_test_norm, y_train_norm, y_test_norm, scaler


def make_dataloader(
    X: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    shuffle: bool,
) -> DataLoader:
    """把 numpy 序列包装成 PyTorch DataLoader（分批喂给模型）"""
    tensor_x = torch.from_numpy(X).float()
    tensor_y = torch.from_numpy(y).float()
    dataset = TensorDataset(tensor_x, tensor_y)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


# ============================================================
# 训练主循环
# ============================================================
def train_model(
    train_loader: DataLoader,
    val_loader: DataLoader,
    model: LSTMAutoencoder,
    config: Dict,
    equipment_id: str,
    save_dir: Path = None,
    logger: Optional[logging.Logger] = None,
) -> Dict:
    """
    训练入口：执行 epochs 轮训练，保存最佳权重 + 训练曲线 + 历史 JSON。

    训练策略（答辩要点）：
      - 优化器 Adam(lr=0.001)：自适应学习率，收敛快
      - 损失函数 MSELoss：重建误差均方误差
      - 学习率调度 ReduceLROnPlateau：验证损失不降时自动把 lr 减半
      - 早停 Early Stopping：验证损失连续 10 轮不下降就停止，防止过拟合
      - 只保存验证损失最低的那轮权重（best checkpoint）

    Parameters
    ----------
    train_loader, val_loader : 已打包好的 DataLoader
    model        : LSTMAutoencoder 实例
    config       : MODEL_CONFIG 字典（含 epochs / batch_size / lr 等）
    equipment_id : 用于命名 checkpoint 和日志
    save_dir     : 模型保存目录，默认 output/model_weight
    logger       : 日志器
    """
    log = logger or logging.getLogger(__name__)
    save_dir = Path(save_dir) if save_dir else MODEL_WEIGHT_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    device = get_device(config.get('device'))
    model = model.to(device)
    log.info(f'训练设备: {device}')
    log.info(f'模型结构: LSTM自编码器 input={config["input_size"]} '
             f'hidden={config["hidden_size"]} layers={config["num_layers"]} '
             f'dropout={config["dropout"]}')

    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])
    criterion = nn.MSELoss()
    # 验证损失连续 3 轮不降 → lr 减半；最少降到 1e-6
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=3, min_lr=1e-6
    )

    epochs = config['epochs']
    patience = config.get('early_stopping_patience', 10)
    best_val_loss = float('inf')
    best_epoch = 0
    best_state = None
    bad_epochs = 0
    history = {'train_loss': [], 'val_loss': [], 'lr': []}

    log.info(f'开始训练: epochs={epochs}, batch_size={config["batch_size"]}, '
             f'early_stop_patience={patience}')
    log.info('=' * 70)

    for epoch in range(1, epochs + 1):
        # ---------- 训练阶段 ----------
        model.train()  # 开启 dropout / batchnorm 训练模式
        train_losses: List[float] = []
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()       # 清空上一轮梯度
            pred = model(xb)            # 前向传播：重建输入
            loss = criterion(pred, yb)  # 计算 MSE 重建误差
            loss.backward()             # 反向传播：算梯度
            optimizer.step()            # 更新权重
            train_losses.append(loss.item())
        train_loss = float(np.mean(train_losses)) if train_losses else float('nan')

        # ---------- 验证阶段 ----------
        model.eval()  # 关闭 dropout，固定权重
        val_losses: List[float] = []
        with torch.no_grad():  # 验证不计算梯度，省内存
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                loss = criterion(pred, yb)
                val_losses.append(loss.item())
        val_loss = float(np.mean(val_losses)) if val_losses else float('nan')

        # 记录历史
        current_lr = optimizer.param_groups[0]['lr']
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['lr'].append(current_lr)
        scheduler.step(val_loss)

        # 每轮打印日志
        log.info(
            f'epoch {epoch:03d}/{epochs} | '
            f'train_loss={train_loss:.6f}  val_loss={val_loss:.6f}  '
            f'lr={current_lr:.2e}'
        )

        # ---------- 早停判断 ----------
        # 验证损失下降超过 1e-7 才算"真正改善"（避免浮点抖动误判）
        if val_loss < best_val_loss - 1e-7:
            best_val_loss = val_loss
            best_epoch = epoch
            # 深拷贝当前权重（保存 CPU 版本，部署机无需 GPU 也能加载）
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= patience:
                log.info(f'早停触发: 连续 {patience} 轮验证损失未下降，'
                         f'最佳 epoch={best_epoch}, best_val_loss={best_val_loss:.6f}')
                break

    log.info('=' * 70)
    log.info(f'训练结束: 共运行 {len(history["train_loss"])} 轮，'
             f'最佳 epoch={best_epoch}, best_val_loss={best_val_loss:.6f}')

    # ---------- 保存最佳权重 ----------
    if best_state is not None:
        model.load_state_dict(best_state)
    model.cpu()  # 统一存 CPU 版本
    ckpt_path = save_dir / f'lstm_autoencoder_{equipment_id}_best.pth'
    torch.save(
        {
            'model_state_dict': model.state_dict(),   # 神经网络权重
            'model_config': model.get_config(),        # 模型结构参数（推理时重建模型用）
            'best_val_loss': best_val_loss,            # 最佳验证损失
            'best_epoch': best_epoch,                  # 最佳轮次
            'trained_at': datetime.now().isoformat(),  # 训练时间
            'equipment_id': equipment_id,              # 对应设备
            'feature_columns': list(FEATURE_COLUMNS),  # 8 维特征顺序（防推理时列错位）
        },
        ckpt_path,
    )
    log.info(f'✅ 模型权重已保存 → {ckpt_path}')

    # ---------- 保存训练历史 JSON ----------
    history_path = LOG_DIR / f'train_history_{equipment_id}.json'
    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump({
            'equipment_id': equipment_id,
            'best_val_loss': best_val_loss,
            'best_epoch': best_epoch,
            'epochs_run': len(history['train_loss']),
            'history': history,
        }, f, ensure_ascii=False, indent=2)
    log.info(f'✅ 训练历史已保存 → {history_path}')

    # ---------- 绘制损失曲线 ----------
    try:
        curve_path = plot_training_curve(history, equipment_id, best_epoch)
        log.info(f'✅ 训练曲线已保存 → {curve_path}')
    except Exception as exc:
        log.warning(f'绘制训练曲线失败（不影响权重）: {exc}')

    # ---------- 验证权重可加载（训练后自检）----------
    try:
        from Lstm_model.predict import ModelPredictor
        scaler_path = MODEL_WEIGHT_DIR / f'scaler_{equipment_id}.pkl'
        predictor = ModelPredictor(str(ckpt_path), str(scaler_path), device='cpu')
        log.info(f'✅ 权重自检通过: ModelPredictor 加载成功，'
                 f'设备={predictor.equipment_id}, 训练时间={predictor.trained_at}')
    except Exception as exc:
        log.warning(f'权重自检失败（请检查 predict.py 兼容性）: {exc}')

    return {
        'equipment_id': equipment_id,
        'best_val_loss': best_val_loss,
        'best_epoch': best_epoch,
        'epochs_run': len(history['train_loss']),
        'checkpoint': str(ckpt_path),
        'history': history,
    }


# ============================================================
# 损失可视化（双轴：损失 + 学习率，标注最佳 epoch）
# ============================================================
def plot_training_curve(
    history: Dict,
    equipment_id: str,
    best_epoch: int = 0,
) -> Path:
    """
    保存训练曲线 PNG 到 output/chart/training_curve_{equipment_id}.png

    图中包含：
      - 左 Y 轴：train_loss / val_loss（MSE 重建误差，越低越好）
      - 右 Y 轴：学习率 lr（随训练衰减）
      - 垂直虚线标注最佳 epoch（验证损失最低的那一轮）
      - 中文标题，便于直接放进答辩 PPT
    """
    import matplotlib
    matplotlib.use('Agg')  # 无界面环境（服务器/容器）必须设这个
    import matplotlib.pyplot as plt

    # 尝试设置中文字体（答辩 PPT 直接用图时中文不乱码）
    for font in ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']:
        try:
            matplotlib.rcParams['font.sans-serif'] = [font]
            matplotlib.rcParams['axes.unicode_minus'] = False
            break
        except Exception:
            continue

    fig, ax1 = plt.subplots(figsize=(10, 6))

    epochs_range = range(1, len(history['train_loss']) + 1)

    # 左轴：损失
    ax1.plot(epochs_range, history['train_loss'], 'b-o', markersize=3,
             label='Train Loss (训练集)', linewidth=1.5)
    ax1.plot(epochs_range, history['val_loss'], 'r-s', markersize=3,
             label='Val Loss (验证集)', linewidth=1.5)
    ax1.set_xlabel('Epoch (训练轮次)', fontsize=12)
    ax1.set_ylabel('MSE Reconstruction Error (重建误差)', fontsize=12, color='black')
    ax1.tick_params(axis='y', labelcolor='black')
    ax1.grid(True, alpha=0.3)

    # 标注最佳 epoch
    if best_epoch > 0:
        ax1.axvline(x=best_epoch, color='green', linestyle='--', alpha=0.7,
                    label=f'Best Epoch = {best_epoch}')
        if best_epoch <= len(history['val_loss']):
            ax1.scatter([best_epoch], [history['val_loss'][best_epoch - 1]],
                        color='green', s=100, zorder=5, edgecolors='black')

    # 右轴：学习率
    ax2 = ax1.twinx()
    ax2.plot(epochs_range, history['lr'], 'g--', alpha=0.5,
             label='Learning Rate (学习率)', linewidth=1)
    ax2.set_ylabel('Learning Rate', fontsize=12, color='green')
    ax2.tick_params(axis='y', labelcolor='green')
    ax2.set_yscale('log')

    # 合并图例
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=10)

    eq_name = EQUIPMENT_LIST.get(equipment_id, {}).get('equipment_name', equipment_id)
    plt.title(f'LSTM 自编码器训练曲线 — {equipment_id} ({eq_name})\n'
              f'输入: 60分钟 × 8维特征 | 最佳验证损失: {min(history["val_loss"]):.6f}',
              fontsize=13)
    fig.tight_layout()

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CHART_DIR / f'training_curve_{equipment_id}.png'
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    return out_path


# ============================================================
# 命令行入口（一键训练：默认 I-9-01，epochs=30）
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description='LSTM 自编码器训练脚本（默认训练示例设备 I-9-01，30 轮）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m Lstm_model.train                              # 一键训练 I-9-01，30轮
  python -m Lstm_model.train --equipment_id COMP-01       # 训练空压机
  python -m Lstm_model.train --equipment_id C-3-01 --epochs 50  # 训练卷绕机，50轮
  python -m Lstm_model.train --save_dir D:/my_models      # 自定义权重保存目录
        """,
    )
    parser.add_argument(
        '--equipment_id',
        type=str,
        default=DEFAULT_EQUIPMENT_ID,
        help=f'设备 ID，默认 {DEFAULT_EQUIPMENT_ID}（电芯烘烤炉，示例设备）',
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=DEFAULT_EPOCHS,
        help=f'训练轮次，默认 {DEFAULT_EPOCHS}',
    )
    parser.add_argument(
        '--data',
        type=str,
        default=None,
        help='CSV 路径，不传则自动扫描 data/raw_data/*.csv',
    )
    parser.add_argument(
        '--save_dir',
        type=str,
        default=None,
        help='模型权重保存目录，默认 output/model_weight',
    )
    parser.add_argument(
        '--batch_size',
        type=int,
        default=None,
        help='覆盖 config 中的 batch_size（默认 32）',
    )
    args = parser.parse_args()

    # 校验设备 ID
    if args.equipment_id not in EQUIPMENT_LIST:
        sys.exit(f'❌ 未知 equipment_id: {args.equipment_id}\n'
                 f'可用设备: {list(EQUIPMENT_LIST.keys())[:10]}...（共 {len(EQUIPMENT_LIST)} 台）')

    eq_info = EQUIPMENT_LIST[args.equipment_id]
    print()
    print('=' * 70)
    print(f'  设备: {args.equipment_id} — {eq_info.get("equipment_name", "?")}')
    print(f'  车间: {eq_info.get("workshop_id", "?")} | '
          f'类型: {eq_info.get("equipment_type", "?")} | '
          f'额定功率: {eq_info.get("rated_power", "?")} kW')
    print(f'  训练轮次: {args.epochs} | 输入: 60分钟 × 8维特征')
    print('=' * 70)
    print()

    # 初始化日志
    logger = setup_logger(args.equipment_id)

    # 合并配置（命令行参数覆盖 config 默认值）
    config = dict(MODEL_CONFIG)
    config['epochs'] = args.epochs
    if args.batch_size is not None:
        config['batch_size'] = args.batch_size

    save_dir = Path(args.save_dir) if args.save_dir else MODEL_WEIGHT_DIR

    # ---------- 第一步：准备数据 ----------
    logger.info('[Step 1/4] 数据准备中...')
    X_train, X_test, y_train, y_test, scaler = prepare_sequences(
        args.equipment_id, csv_path=args.data, logger=logger
    )
    logger.info(f'[Step 1/4] 数据就绪: X_train={X_train.shape}, X_test={X_test.shape}')

    # ---------- 第二步：构建 DataLoader ----------
    logger.info('[Step 2/4] 构建 DataLoader...')
    train_loader = make_dataloader(X_train, y_train, config['batch_size'], shuffle=True)
    # 验证集不打乱（保持时序）
    val_loader = make_dataloader(
        X_test if X_test is not None and X_test.shape[0] > 0 else X_train,
        y_test if y_test is not None and y_test.shape[0] > 0 else y_train,
        config['batch_size'],
        shuffle=False,
    )

    # ---------- 第三步：构造模型 ----------
    logger.info('[Step 3/4] 构造 LSTM 自编码器模型...')
    model = LSTMAutoencoder(
        input_size=config['input_size'],
        hidden_size=config['hidden_size'],
        num_layers=config['num_layers'],
        output_size=config['output_size'],
        dropout=config['dropout'],
    )
    total_params = sum(p.numel() for p in model.parameters())
    logger.info(f'[Step 3/4] 模型参数量: {total_params:,}')

    # ---------- 第四步：训练 ----------
    logger.info('[Step 4/4] 开始训练...')
    result = train_model(
        train_loader, val_loader, model, config,
        equipment_id=args.equipment_id,
        save_dir=save_dir,
        logger=logger,
    )

    # ---------- 训练完成总结 ----------
    print()
    print('=' * 70)
    print('  🎉 训练完成！')
    print(f'  设备:       {result["equipment_id"]}')
    print(f'  运行轮次:   {result["epochs_run"]}')
    print(f'  最佳轮次:   {result["best_epoch"]}')
    print(f'  最佳验证损失: {result["best_val_loss"]:.6f}')
    print(f'  权重文件:   {result["checkpoint"]}')
    print(f'  归一化器:   {MODEL_WEIGHT_DIR / f"scaler_{args.equipment_id}.pkl"}')
    print(f'  训练曲线:   {CHART_DIR / f"training_curve_{args.equipment_id}.png"}')
    print(f'  训练日志:   output/log/train_{args.equipment_id}_*.log')
    print()
    print('  👉 下一步: 重启算法服务 python main.py')
    print('     异常检测接口 /api/v1/anomaly/detect 会自动加载该权重，')
    print('     无需修改任何代码。')
    print('=' * 70)
    print()

    summary = {k: v for k, v in result.items() if k != 'history'}
    logger.info(f'训练总结: {json.dumps(summary, ensure_ascii=False)}')


if __name__ == '__main__':
    main()
