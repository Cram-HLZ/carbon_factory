"""
evaluate —— 模型评估

提供四个工具函数：
    evaluate_model             : 用测试集 DataLoader 计算整体重建误差分布
    classification_report      : 输出 accuracy / precision / recall / F1 / 混淆矩阵
    plot_error_distribution    : 保存误差分布图
    save_evaluation_report     : 保存评估报告 JSON

【目标指标】
    异常检测 F1 ≥ 0.85（对应方案生成的"AI 准确率 ≥ 85%"）
    单条推理延迟 < 100ms（在 predict.benchmark_latency 验证）

后端同学：本模块用于离线评估，不在 API 链路里。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader

from config.settings import CHART_DIR, LOG_DIR, MODEL_WEIGHT_DIR
from Lstm_model.model import LSTMAutoencoder


@torch.no_grad()
def evaluate_model(
    model: LSTMAutoencoder,
    test_loader: DataLoader,
    device: torch.device = None,
) -> Dict:
    """
    计算整体重建误差分布。

    Returns
    -------
    dict:
        errors            : 每条样本的 MSE 列表
        mean_error        : 平均误差
        std_error         : 标准差
        max_error / min_error
        p95 / p99         : 95/99 分位数
    """
    if device is None:
        device = torch.device('cpu')
    model.eval().to(device)

    errors: List[float] = []
    for xb, _ in test_loader:
        xb = xb.to(device)
        recon = model(xb)
        mse = torch.mean((xb - recon) ** 2, dim=(1, 2))
        errors.extend(mse.cpu().numpy().tolist())

    if not errors:
        return {'errors': [], 'mean_error': 0.0, 'std_error': 0.0,
                'max_error': 0.0, 'min_error': 0.0,
                'p95': 0.0, 'p99': 0.0}

    arr = np.array(errors)
    return {
        'errors': errors,
        'mean_error': float(arr.mean()),
        'std_error': float(arr.std(ddof=0)),
        'max_error': float(arr.max()),
        'min_error': float(arr.min()),
        'p95': float(np.percentile(arr, 95)),
        'p99': float(np.percentile(arr, 99)),
    }


def classification_report(
    y_true: List[int],
    y_pred: List[int],
) -> Dict:
    """
    输出准确率/召回率/F1/混淆矩阵。

    Parameters
    ----------
    y_true : 真实标签，0=正常, 1=异常
    y_pred : 预测标签
    """
    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    n = len(y_true_arr)
    if n == 0:
        return {'accuracy': 0, 'precision': 0, 'recall': 0, 'f1': 0,
                'confusion_matrix': [[0, 0], [0, 0]], 'support': 0}

    tp = int(np.sum((y_pred_arr == 1) & (y_true_arr == 1)))
    fp = int(np.sum((y_pred_arr == 1) & (y_true_arr == 0)))
    fn = int(np.sum((y_pred_arr == 0) & (y_true_arr == 1)))
    tn = int(np.sum((y_pred_arr == 0) & (y_true_arr == 0)))

    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )
    return {
        'accuracy': round(accuracy, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'confusion_matrix': [[tn, fp], [fn, tp]],
        'support': int(n),
    }


def plot_error_distribution(
    errors: List[float],
    threshold: float,
    save_path: Optional[Path] = None,
) -> Path:
    """保存误差分布图到 output/chart/error_distribution.png"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(errors, bins=50, color='steelblue', alpha=0.7, edgecolor='white')
    ax.axvline(threshold, color='red', linestyle='--', label=f'threshold={threshold:.4f}')
    ax.set_xlabel('reconstruction MSE')
    ax.set_ylabel('count')
    ax.set_title('Reconstruction Error Distribution')
    ax.legend()
    fig.tight_layout()

    if save_path is None:
        CHART_DIR.mkdir(parents=True, exist_ok=True)
        save_path = CHART_DIR / 'error_distribution.png'
    fig.savefig(save_path)
    plt.close(fig)
    return Path(save_path)


def save_evaluation_report(
    results: Dict,
    save_path: Optional[Path] = None,
    equipment_id: Optional[str] = None,
) -> Path:
    """保存评估报告 JSON 到 output/log/evaluation_report_{equipment_id}.json"""
    suffix = f'_{equipment_id}' if equipment_id else ''
    if save_path is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        save_path = LOG_DIR / f'evaluation_report{suffix}.json'
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    # errors 数组可能很大，单独切出来单独存
    errors = results.pop('errors', [])
    summary = {
        'evaluated_at': datetime.now().isoformat(),
        'equipment_id': equipment_id,
        **results,
        'n_samples': len(errors),
    }
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f'[evaluate] report saved → {save_path}')
    return Path(save_path)


def load_test_errors(
    model: LSTMAutoencoder,
    test_loader: DataLoader,
    device: torch.device = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """返回 (errors, indices) 方便上层做异常判定"""
    res = evaluate_model(model, test_loader, device)
    errors = np.array(res['errors'])
    return errors, np.arange(len(errors))
