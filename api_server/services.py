"""
services —— 业务逻辑层

每个 service 函数只做三件事：
    1. 调用算法模块（CarbonCalculator / AnomalyDetector / TraceabilityAnalyzer / CarbonStrategyEngine）
    2. 组装返回数据
    3. 异常兜底，出错返回 code=500 和错误信息

【缓存策略】
    高频查询接口（overview / heatmap / realtime）加内存缓存 TTL=30s，
    避免每次请求都重算。模型与算法实例在模块加载时一次性构造，避免重复开销。

【后端联调建议】
    后端调用时统一走 routes.py 暴露的 HTTP 端点，
    不要直接 import services 内的函数。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import (
    CARBON_FACTORS,
    EQUIPMENT_LIST,
    EQUIPMENT_TYPES,
    MODEL_CONFIG,
    MODEL_WEIGHT_DIR,
    RAW_DATA_DIR,
    WORKSHOPS,
)
from carbon_strategy.carbon_calculator import CarbonCalculator
from carbon_strategy.strategy_engine import CarbonStrategyEngine
from carbon_strategy.traceability import TraceabilityAnalyzer
from feature_engineer.data_cleaner import DataCleaner
from feature_engineer.data_loader import DataLoader as FeDataLoader
from feature_engineer.feature_extractor import (
    FEATURE_COLUMNS,
    FEATURE_DISPLAY_NAMES,
    FeatureExtractor,
)
from feature_engineer.sequence_builder import SequenceBuilder
from Lstm_model.anomaly_detector import AnomalyDetector
try:
    from Lstm_model.predict import ModelPredictor
except ImportError:
    # torch 未安装时降级，异常检测接口退化为统计方法
    ModelPredictor = None  # type: ignore[assignment,misc]


logger = logging.getLogger(__name__)


# ============================================================
# 模块级单例：算法实例在 import 时构造一次，全局复用
# ============================================================
_data_loader = FeDataLoader()
_cleaner = DataCleaner()
_extractor = FeatureExtractor()
_builder = SequenceBuilder()
_calculator = CarbonCalculator()
_strategy_engine = CarbonStrategyEngine()
_anomaly_detector = AnomalyDetector()

# 模型预测器按 equipment_id 懒加载（避免无对应权重时启动失败）
_predictor_cache: Dict[str, ModelPredictor] = {}


def _get_predictor(equipment_id: str) -> Optional[Any]:
    """懒加载 ModelPredictor，未训练或 torch 未安装时返回 None（API 用兜底逻辑判定异常）"""
    if ModelPredictor is None:
        return None
    if equipment_id in _predictor_cache:
        return _predictor_cache[equipment_id]
    model_path = ModelPredictor.default_model_path(equipment_id)
    scaler_path = ModelPredictor.default_scaler_path(equipment_id)
    if not Path(model_path).exists() or not Path(scaler_path).exists():
        return None
    try:
        predictor = ModelPredictor(model_path, scaler_path, device='cpu')
        _predictor_cache[equipment_id] = predictor
        return predictor
    except Exception as exc:
        logger.warning(f'加载模型 {equipment_id} 失败: {exc}，退化为兜底异常检测')
        return None


# ============================================================
# 内存缓存（开发期 TTL=30s）
# ============================================================
_cache: Dict[str, Tuple[float, Any]] = {}
_CACHE_TTL = 30.0


def _cache_get(key: str) -> Optional[Any]:
    item = _cache.get(key)
    if item is None:
        return None
    ts, val = item
    if time.time() - ts > _CACHE_TTL:
        _cache.pop(key, None)
        return None
    return val


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


# ============================================================
# 内部：数据装载
# ============================================================
def _load_raw_data(start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None) -> pd.DataFrame:
    """从 raw_data 加载全量数据，按时间过滤后返回"""
    frames = []
    for csv_path in sorted(RAW_DATA_DIR.glob('*.csv')):
        try:
            frames.append(_data_loader.load_csv(csv_path))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        if start_time is not None:
            df = df[df['timestamp'] >= pd.Timestamp(start_time)]
        if end_time is not None:
            df = df[df['timestamp'] <= pd.Timestamp(end_time)]
    return df


# ============================================================
# 碳排数据查询服务
# ============================================================
def get_carbon_emission_data(request) -> Dict:
    """碳排数据查询：按 level + node_id + 时间范围聚合"""
    try:
        cache_key = f'carbon:{request.level}:{request.node_id}:{request.start_time}:{request.end_time}'
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        df = _load_raw_data(request.start_time, request.end_time)
        if df.empty:
            # 没有真实数据时返回空结构，方便前端联调
            return {
                'level': request.level,
                'node_id': request.node_id,
                'records': [],
                'total_emission': 0.0,
                'message': '查询时间范围内无数据，请确认 raw_data 目录或调整时间范围',
            }

        agg = _calculator.aggregate_by_level(df, request.level, request.node_id)
        result = {
            'level': request.level,
            'node_id': request.node_id,
            'records': agg.to_dict(orient='records'),
            'total_emission': float(agg['carbon_emission'].sum()) if 'carbon_emission' in agg.columns else 0.0,
        }
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.exception('carbon query failed')
        return {'error': str(exc), 'level': request.level, 'node_id': request.node_id}


def get_factory_overview() -> Dict:
    """厂区碳排总览（首页数据）"""
    cache_key = 'factory_overview'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        df = _load_raw_data()
        if df.empty:
            # 没有数据时返回模拟结构，保证前端不崩
            overview = {
                'total_emission': 0.0,
                'total_energy': 0.0,
                'by_workshop': [],
                'by_team': [],
                'by_equipment_top': [],
                'hourly_trend': [],
                'message': '当前 raw_data 无数据，请联系算法侧生成 sample_equipment_data.csv',
            }
        else:
            overview = _calculator.aggregate_factory(df)
        _cache_set(cache_key, overview)
        return overview
    except Exception as exc:
        logger.exception('overview failed')
        return {'error': str(exc)}


def get_heatmap_data(start_time: datetime, end_time: datetime) -> Dict:
    """热力图数据：各设备碳排强度用于渲染"""
    cache_key = f'heatmap:{start_time}:{end_time}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        df = _load_raw_data(start_time, end_time)
        if df.empty:
            return {'records': [], 'message': '查询时间范围内无数据'}
        records = _calculator.heatmap_data(df)
        result = {'records': records, 'count': len(records)}
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.exception('heatmap failed')
        return {'error': str(exc)}


# ============================================================
# 异常检测服务
# ============================================================
def detect_anomaly(request) -> Dict:
    """
    异常检测：输入 60×8 时序数据矩阵，返回是否异常 + 严重程度。

    流程：
        1. 把 60×8 list → ndarray
        2. 若该 equipment_id 有训练好的模型：调 LSTM 算重建误差
        3. 若无模型：退化为兜底（用前 1 分钟数据与最近 60 分钟均值的偏离度作误差）
        4. 调 AnomalyDetector 判定，输出 severity + 是否告警
    """
    try:
        eq_id = request.equipment_id
        if eq_id not in EQUIPMENT_LIST:
            return {'error': f'未知 equipment_id: {eq_id}'}

        seq = np.array(request.sequence_data, dtype=np.float32)
        if seq.shape != (60, MODEL_CONFIG['input_size']):
            return {
                'error': (
                    f'sequence_data 必须是 60×{MODEL_CONFIG["input_size"]} 矩阵，'
                    f'实际 {seq.shape}'
                )
            }

        predictor = _get_predictor(eq_id)
        contributions: List[Dict] = []
        if predictor is None:
            # 兜底：用统计偏离度作为重建误差
            error = _fallback_reconstruction_error(seq)
            threshold_type = 'fallback'
            contributions = _fallback_feature_contributions(seq)
        else:
            # 注：根据约定，调用方传入的 sequence_data 已归一化
            # 若没归一化，请改用 predictor.infer_error_with_auto_normalize(seq)
            error = predictor.compute_reconstruction_error(seq)
            threshold_type = 'lstm'
            try:
                contributions = predictor.explain_contributions(seq)
            except Exception as exc:
                logger.warning(f'explain contributions failed: {exc}')

        result = _anomaly_detector.detect(
            error, eq_id, timestamp=datetime.now(),
            feature_contributions=contributions or None,
        )
        result['threshold_type'] = threshold_type
        return result
    except Exception as exc:
        logger.exception('anomaly detect failed')
        return {'error': str(exc), 'equipment_id': request.equipment_id}


def _fallback_reconstruction_error(sequence: np.ndarray) -> float:
    """
    无模型时的兜底：用前 1 分钟数据与最近 N 分钟均值的偏离度。
    不依赖任何训练权重，便于后端联调阶段无模型时也能跑通。
    """
    # 取最后 5 分钟作为"近期正常基线"，看最后一分钟与基线的偏差
    if sequence.shape[0] < 6:
        return 0.0
    baseline = sequence[:-1].mean(axis=0)
    last = sequence[-1]
    diff = last - baseline
    return float(np.mean(diff ** 2))


def _fallback_feature_contributions(sequence: np.ndarray, top_k: int = 8) -> List[Dict]:
    """
    无模型时的可解释性兜底：逐特征 |最后一分钟 − 近期基线| 归一化为贡献占比。
    与 ModelPredictor.explain_contributions 返回结构一致。
    """
    if sequence.shape[0] < 6:
        return []
    baseline = sequence[:-1].mean(axis=0)
    err = np.abs(sequence[-1] - baseline)
    total = float(err.sum())
    contributions: List[Dict] = []
    for i, feat in enumerate(FEATURE_COLUMNS):
        share = float(err[i] / total) if total > 0 else 0.0
        contributions.append({
            'feature': feat,
            'feature_name': FEATURE_DISPLAY_NAMES.get(feat, feat),
            'reconstruction_error': float(err[i]),
            'contribution': round(share, 4),
        })
    contributions.sort(key=lambda x: x['contribution'], reverse=True)
    return contributions[:top_k]


def _inject_synthetic_anomalies(
    sequences: np.ndarray,
    n: int,
    feature_dim: int,
    scale: float = 2.0,
    seed: int = 42,
) -> np.ndarray:
    """
    向正常序列注入合成异常（构建 ground truth）：
    随机挑样本，对随机一个特征整窗加尖峰并裁剪回 [0,1]。
    归一化数据被大幅抬升后，模型重建误差会显著增大 → 判为异常。
    """
    rng = np.random.RandomState(seed)
    n = min(int(n), sequences.shape[0])
    idxs = rng.choice(sequences.shape[0], size=n, replace=False)
    anoms = sequences[idxs].copy()
    for a in anoms:
        feat = int(rng.randint(0, feature_dim))
        a[:, feat] = a[:, feat] * scale + 0.5
        np.clip(a, 0.0, 1.0, out=a)
    return anoms


def evaluate_model(equipment_id: str, n_anomalies: Optional[int] = None) -> Dict:
    """
    AI 模型评估指标：把无监督异常检测的「黑盒」变可量化评估。

    用「注入式合成异常」构造 ground truth，复用 Lstm_model.evaluate.classification_report
    计算 accuracy / precision / recall / F1 / 混淆矩阵。

    流程：
        1. 加载该设备模型 + 训练 scaler
        2. 用后 20% 正常序列算重建误差分布 → 阈值 = mean + 3σ
        3. 向正常序列注入合成异常作为正样本
        4. 以阈值判定预测标签，与真实标签对比输出分类指标
    """
    try:
        if equipment_id not in EQUIPMENT_LIST:
            return {'error': f'未知 equipment_id: {equipment_id}'}

        # 显式校验模型权重与 scaler 是否就绪（与 ModelPredictor 默认路径一致），
        # 缺任一个都给出「先训练」的明确提示
        model_path = MODEL_WEIGHT_DIR / f'lstm_autoencoder_{equipment_id}_best.pth'
        scaler_path = MODEL_WEIGHT_DIR / f'scaler_{equipment_id}.pkl'
        missing = [str(p) for p in (model_path, scaler_path) if not p.exists()]
        if missing:
            return {
                'error': f'设备 {equipment_id} 未训练模型，无法评估。缺少文件: {missing}',
                'hint': f'先运行 python -m Lstm_model.train --equipment_id {equipment_id}',
            }

        predictor = _get_predictor(equipment_id)
        if predictor is None:
            return {
                'error': f'设备 {equipment_id} 模型存在但加载失败，无法评估。',
                'hint': '请确认 torch 已安装且权重文件未损坏后重试',
            }
        if predictor.scaler is None:
            return {'error': f'设备 {equipment_id} 未加载 scaler，无法归一化评估数据'}

        df = _data_loader.load_equipment_data(equipment_id)
        if df.empty:
            return {'error': f'设备 {equipment_id} 无历史数据'}

        cleaned = _cleaner.clean(df)
        feats = _extractor.extract(cleaned)
        X, _ = _builder.build_sequences(feats)
        if X.shape[0] < 10:
            return {'error': f'设备 {equipment_id} 数据不足以构建序列（仅 {X.shape[0]} 条）'}

        # 后 20% 作为「正常」测试集（时序顺序，不打乱）
        _, X_test, _, _ = _builder.train_test_split(X, X, test_size=0.2)
        flat = X_test.reshape(-1, X_test.shape[-1])
        X_test_norm = predictor.scaler.transform(flat).reshape(X_test.shape).astype(np.float32)

        f_dim = int(X_test_norm.shape[-1])
        normal_errors = predictor.predict_batch(X_test_norm)
        threshold = float(np.mean(normal_errors) + 3.0 * np.std(normal_errors))
        threshold = max(threshold, 1e-6)

        n_anom = n_anomalies or max(3, int(len(X_test_norm) * 0.3))
        anom_norm = _inject_synthetic_anomalies(X_test_norm, n_anom, f_dim)
        anom_errors = predictor.predict_batch(anom_norm)

        all_errors = np.concatenate([normal_errors, anom_errors])
        y_true = [0] * len(normal_errors) + [1] * len(anom_errors)
        y_pred = [1 if float(e) > threshold else 0 for e in all_errors]

        from Lstm_model.evaluate import classification_report
        metrics = classification_report(y_true, y_pred)

        return {
            'equipment_id': equipment_id,
            'equipment_name': EQUIPMENT_LIST[equipment_id].get('name', equipment_id),
            'n_normal': int(len(normal_errors)),
            'n_anomaly': int(len(anom_errors)),
            'threshold': round(threshold, 6),
            'threshold_method': 'reconstruction error mean + 3σ',
            'metrics': metrics,
        }
    except Exception as exc:
        logger.exception('model evaluate failed')
        return {'error': str(exc), 'equipment_id': equipment_id}


def get_equipment_anomaly_status(equipment_id: str) -> Dict:
    """获取设备当前异常状态（从最近一条数据计算）"""
    try:
        if equipment_id not in EQUIPMENT_LIST:
            return {'error': f'未知 equipment_id: {equipment_id}'}
        df = _data_loader.load_equipment_data(
            equipment_id,
            start_time=datetime.now() - timedelta(hours=2),
        )
        if df.empty:
            return {
                'equipment_id': equipment_id,
                'is_anomaly': False,
                'message': '近 2 小时无数据',
            }
        # 用最近 60 分钟做兜底异常检测（不需要模型）
        cleaned = _cleaner.clean(df)
        feats = _extractor.extract(cleaned)
        if len(feats) < MODEL_CONFIG['sequence_length']:
            return {
                'equipment_id': equipment_id,
                'is_anomaly': False,
                'message': '数据不足以做异常检测',
            }
        seq = _builder.build_single_sequence(feats, end_idx=len(feats) - 1)
        predictor = _get_predictor(equipment_id)
        if predictor is not None and predictor.scaler is not None:
            seq_norm = SequenceBuilder.normalize_single(seq, predictor.scaler)
            error = predictor.compute_reconstruction_error(seq_norm)
        else:
            error = _fallback_reconstruction_error(seq[0])
        return _anomaly_detector.detect(error, equipment_id, timestamp=datetime.now())
    except Exception as exc:
        logger.exception('equipment anomaly status failed')
        return {'error': str(exc), 'equipment_id': equipment_id}


# ============================================================
# 溯源报告服务
# ============================================================
def get_traceability_report(request) -> Dict:
    """设备碳排溯源：近 72h 历史 + 根因分析"""
    try:
        eq_id = request.equipment_id
        if eq_id not in EQUIPMENT_LIST:
            return {'error': f'未知 equipment_id: {eq_id}'}

        # 装载该设备的全部历史数据，从中切 72h
        df = _data_loader.load_equipment_data(eq_id)
        if df.empty:
            return {
                'equipment_id': eq_id,
                'message': '该设备无历史数据，无法溯源',
            }
        analyzer = TraceabilityAnalyzer(data_loader=_data_loader)
        report = analyzer.generate_trace_report(
            eq_id,
            request.anomaly_time,
            history_data=df,
        )
        return report
    except Exception as exc:
        logger.exception('traceability failed')
        return {'error': str(exc), 'equipment_id': request.equipment_id}


# ============================================================
# 降碳方案生成服务
# ============================================================
def generate_strategies(request) -> Dict:
    """AI 降碳方案生成：输出设备运维/生产排班/工艺优化三类方案"""
    try:
        eq_id = request.equipment_id
        if eq_id not in EQUIPMENT_LIST:
            return {'error': f'未知 equipment_id: {eq_id}'}
        strategies = _strategy_engine.generate_strategies(
            eq_id, request.analysis_result
        )
        return {
            'equipment_id': eq_id,
            'strategies': strategies,
            'count': len(strategies),
        }
    except Exception as exc:
        logger.exception('strategy generate failed')
        return {'error': str(exc), 'equipment_id': request.equipment_id}


# ============================================================
# 设备实时数据服务
# ============================================================
def get_equipment_realtime(equipment_id: str) -> Dict:
    """设备实时数据：功率、负载率、碳排、温度、异常状态"""
    try:
        if equipment_id not in EQUIPMENT_LIST:
            return {'error': f'未知 equipment_id: {equipment_id}'}
        cache_key = f'realtime:{equipment_id}'
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        df = _data_loader.load_equipment_data(
            equipment_id,
            start_time=datetime.now() - timedelta(hours=1),
        )
        info = EQUIPMENT_LIST[equipment_id]
        if df.empty:
            # 没数据时返回设备元信息 + 占位状态
            return {
                'equipment_id': equipment_id,
                'equipment_name': info.get('name', equipment_id),
                'equipment_type': info.get('equipment_type', ''),
                'workshop_id': info.get('workshop_id'),
                'timestamp': datetime.now().isoformat(),
                'power': 0.0,
                'load_rate': 0.0,
                'carbon_emission': 0.0,
                'temperature': 0.0,
                'status': 0,
                'is_anomaly': False,
                'message': '近 1 小时无数据',
            }

        latest = df.sort_values('timestamp').iloc[-1]
        power = float(latest.get('power', 0))
        carbon = float(power / 60 * CARBON_FACTORS['electricity'])
        result = {
            'equipment_id': equipment_id,
            'equipment_name': info.get('name', equipment_id),
            'equipment_type': info.get('equipment_type', ''),
            'workshop_id': info.get('workshop_id'),
            'timestamp': pd.Timestamp(latest['timestamp']).isoformat(),
            'power': round(power, 4),
            'load_rate': round(float(latest.get('load_rate', 0)), 4),
            'carbon_emission': round(carbon, 4),
            'temperature': round(float(latest.get('temperature', 0)), 2),
            'status': int(latest.get('status', 0)),
            'is_anomaly': False,  # 真实异常状态由前端单独拉 anomaly/detect 接口
        }
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.exception('equipment realtime failed')
        return {'error': str(exc), 'equipment_id': equipment_id}


def list_equipment(workshop_id: Optional[str] = None) -> Dict:
    """设备列表：可按车间筛选"""
    try:
        items = []
        for eq_id, info in EQUIPMENT_LIST.items():
            if workshop_id and info.get('workshop_id') != workshop_id:
                continue
            type_info = EQUIPMENT_TYPES.get(info['equipment_type'], {})
            items.append({
                'equipment_id': eq_id,
                'equipment_name': info.get('name', eq_id),
                'equipment_type': info.get('equipment_type', ''),
                'workshop_id': info.get('workshop_id', ''),
                'team_id': info.get('team_id', ''),
                'rated_power': float(type_info.get('rated_power', 0)),
                'category': type_info.get('category', ''),
            })
        return {
            'count': len(items),
            'items': items,
            'workshop_filter': workshop_id,
        }
    except Exception as exc:
        logger.exception('list equipment failed')
        return {'error': str(exc)}
