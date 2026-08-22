"""
train —— LSTM 自编码器训练脚本

训练流程：
    1. 优化器：Adam(lr=0.001)
    2. 损失函数：MSELoss（重建误差）
    3. 学习率调度：ReduceLROnPlateau（验证损失不降则降 lr）
    4. 早停：验证损失连续 patience 个 epoch 不下降则停止
    5. 保存最佳模型到 output/model_weight/lstm_autoencoder_{equipment_id}_best.pth
    6. 保存训练曲线到 output/chart/training_curve_{equipment_id}.png

命令行入口（建议为每类设备单独训练一个模型）：
    python -m Lstm_model.train --data data/raw_data/sample_equipment_data.csv \
        --equipment_id I-9-01
    python -m Lstm_model.train --equipment_id COMP-01
    python -m Lstm_model.train --equipment_id C-3-01

后端同学：本脚本只在算法侧执行，部署后无需调用。
        训练好的 .pth 权重由 ModelPredictor 在 api_server 启动时一次性加载。
"""

from __future__ import annotations

import argparse
import json
import os
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
from feature_engineer.feature_extractor import FeatureExtractor
from feature_engineer.sequence_builder import SequenceBuilder
from Lstm_model.model import LSTMAutoencoder


def get_device(name: str = None) -> torch.device:
    """根据 config 中的 device 名称返回 torch.device"""
    name = name or MODEL_CONFIG.get('device', 'cpu')
    if name == 'cuda' and torch.cuda.is_available():
        return torch.device('cuda')
    return torch.device('cpu')


def prepare_sequences(
    equipment_id: str,
    csv_path: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, object]:
    """
    完整数据流水线：CSV → 清洗 → 特征提取 → 序列构建 → 划分 → 归一化

    Returns
    -------
    X_train, X_test, y_train, y_test, scaler
    """
    loader = FeDataLoader()
    df = loader.load_equipment_data(equipment_id, file_path=csv_path)
    if df.empty:
        raise ValueError(f'设备 {equipment_id} 无可用数据')

    cleaner = DataCleaner()
    df_clean = cleaner.clean(df)

    extractor = FeatureExtractor()
    df_feat = extractor.extract(df_clean)

    builder = SequenceBuilder()
    X, y = builder.build_sequences(df_feat)
    if X.shape[0] == 0:
        raise ValueError(f'设备 {equipment_id} 数据不足以构建序列')

    X_train, X_test, y_train, y_test = builder.train_test_split(X, y, test_size=0.2)
    X_train_norm, X_test_norm, scaler = builder.normalize(
        X_train, X_test,
        save_path=MODEL_WEIGHT_DIR / f'scaler_{equipment_id}.pkl',
    )
    y_train_norm = X_train_norm.copy()
    y_test_norm = X_test_norm.copy() if X_test_norm is not None else None
    return X_train_norm, X_test_norm, y_train_norm, y_test_norm, scaler


def make_dataloader(
    X: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    shuffle: bool,
) -> DataLoader:
    """把 numpy 序列包装成 DataLoader"""
    tensor_x = torch.from_numpy(X).float()
    tensor_y = torch.from_numpy(y).float()
    dataset = TensorDataset(tensor_x, tensor_y)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


def train_model(
    train_loader: DataLoader,
    val_loader: DataLoader,
    model: LSTMAutoencoder,
    config: Dict,
    equipment_id: str,
    save_dir: Path = None,
) -> Dict:
    """
    训练入口：返回训练历史 + 保存 checkpoint / 训练曲线。

    Parameters
    ----------
    train_loader, val_loader : 已打包好的 DataLoader
    model : LSTMAutoencoder 实例
    config : MODEL_CONFIG 字典
    equipment_id : 用于命名 checkpoint
    save_dir : 模型保存目录，默认 output/model_weight
    """
    save_dir = Path(save_dir) if save_dir else MODEL_WEIGHT_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    device = get_device(config.get('device'))
    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])
    criterion = nn.MSELoss()
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=3, verbose=False
    )

    epochs = config['epochs']
    patience = config.get('early_stopping_patience', 10)
    best_val_loss = float('inf')
    best_state = None
    bad_epochs = 0
    history = {'train_loss': [], 'val_loss': [], 'lr': []}

    for epoch in range(1, epochs + 1):
        # 训练
        model.train()
        train_losses: List[float] = []
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
            train_losses.append(loss.item())
        train_loss = float(np.mean(train_losses)) if train_losses else float('nan')

        # 验证
        model.eval()
        val_losses: List[float] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                loss = criterion(pred, yb)
                val_losses.append(loss.item())
        val_loss = float(np.mean(val_losses)) if val_losses else float('nan')

        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['lr'].append(optimizer.param_groups[0]['lr'])
        scheduler.step(val_loss)

        # 打印训练日志（精简版，每个 epoch 一行）
        print(
            f'[{equipment_id}] epoch {epoch:03d}/{epochs} '
            f'train_loss={train_loss:.6f} val_loss={val_loss:.6f} '
            f'lr={optimizer.param_groups[0]["lr"]:.6f}'
        )

        # 早停判断
        if val_loss < best_val_loss - 1e-7:
            best_val_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= patience:
                print(f'[{equipment_id}] early stop at epoch {epoch}, best_val={best_val_loss:.6f}')
                break

    # 恢复最佳权重并保存
    if best_state is not None:
        model.load_state_dict(best_state)
    model.cpu()  # 保存为 CPU 版本，便于部署机无需 GPU 也能加载
    ckpt_path = save_dir / f'lstm_autoencoder_{equipment_id}_best.pth'
    torch.save(
        {
            'model_state_dict': model.state_dict(),
            'model_config': model.get_config(),
            'best_val_loss': best_val_loss,
            'trained_at': datetime.now().isoformat(),
            'equipment_id': equipment_id,
        },
        ckpt_path,
    )
    print(f'[{equipment_id}] checkpoint saved → {ckpt_path}')

    # 保存训练曲线
    try:
        plot_training_curve(history, equipment_id)
    except Exception as exc:  # matplotlib 出问题不影响主流程
        print(f'[{equipment_id}] plot training curve failed: {exc}')

    return {
        'equipment_id': equipment_id,
        'best_val_loss': best_val_loss,
        'epochs_run': len(history['train_loss']),
        'checkpoint': str(ckpt_path),
        'history': history,
    }


def plot_training_curve(history: Dict, equipment_id: str) -> Path:
    """保存训练曲线 PNG 到 output/chart/training_curve_{equipment_id}.png"""
    import matplotlib
    matplotlib.use('Agg')  # 无界面环境
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(history['train_loss'], label='train')
    ax.plot(history['val_loss'], label='val')
    ax.set_xlabel('epoch')
    ax.set_ylabel('MSE loss')
    ax.set_title(f'Training Curve - {equipment_id}')
    ax.legend()
    fig.tight_layout()
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CHART_DIR / f'training_curve_{equipment_id}.png'
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ---------------- 命令行入口 ----------------
def main():
    parser = argparse.ArgumentParser(description='训练 LSTM 自编码器（按设备）')
    parser.add_argument(
        '--data',
        type=str,
        default=None,
        help='CSV 路径，不传则扫描 data/raw_data/*.csv',
    )
    parser.add_argument(
        '--equipment_id',
        type=str,
        required=True,
        help='设备 ID，如 I-9-01 / COMP-01 / C-3-01',
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=None,
        help='覆盖 config.MODEL_CONFIG 中的 epochs',
    )
    args = parser.parse_args()

    if args.equipment_id not in EQUIPMENT_LIST:
        sys.exit(f'未知 equipment_id: {args.equipment_id}')

    # 覆盖 epochs
    config = dict(MODEL_CONFIG)
    if args.epochs is not None:
        config['epochs'] = args.epochs

    # 准备数据
    print(f'[prepare] loading data for {args.equipment_id} ...')
    X_train, X_test, y_train, y_test, _ = prepare_sequences(
        args.equipment_id, csv_path=args.data
    )
    print(f'[prepare] X_train={X_train.shape} X_test={X_test.shape}')

    train_loader = make_dataloader(X_train, y_train, config['batch_size'], shuffle=True)
    val_loader = make_dataloader(
        X_test if X_test is not None else X_train,
        y_test if y_test is not None else y_train,
        config['batch_size'],
        shuffle=False,
    )

    # 构造模型
    model = LSTMAutoencoder(
        input_size=config['input_size'],
        hidden_size=config['hidden_size'],
        num_layers=config['num_layers'],
        output_size=config['output_size'],
        dropout=config['dropout'],
    )

    result = train_model(train_loader, val_loader, model, config, args.equipment_id)
    print(f'[done] {json.dumps({k: v for k, v in result.items() if k != "history"}, ensure_ascii=False)}')


if __name__ == '__main__':
    main()
