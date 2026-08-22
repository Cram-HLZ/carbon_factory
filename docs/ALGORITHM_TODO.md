# 算法模块开发任务清单（队长·算法负责人执行）

> 项目：数字孪生赋能锂电工厂碳排AI监测与溯源系统
> 负责人：队长（算法）
> 最后更新：2026-08-21（已根据《设备清单.xlsx》更新全部设备配置）

---

## 一、项目现状盘点

### 已完成
- [x] 项目目录结构搭建
- [x] `.gitignore` 配置
- [x] `.vscode/` 团队统一配置（prettier 格式化、4空格缩进、单引号）
- [x] `main.py` FastAPI 骨架（仅 hello world）

### 未完成（全部为空）
- [ ] `config/` — 配置模块
- [ ] `feature_engineer/` — 数据加载与特征工程
- [ ] `Lstm_model/` — LSTM异常检测模型
- [ ] `carbon_strategy/` — 碳排核算、溯源、降碳方案引擎
- [ ] `api_server/` — 算法API服务层
- [ ] `requirements.txt` — 依赖清单（空文件）
- [ ] `docs/algorithm_interface.md` — 算法接口文档（空文件）
- [ ] `docs/model_intro.md` — 模型说明文档（空文件）
- [ ] `data/raw_data/` — 模拟测试数据

---

## 一点五、设备清单对照（基于《设备清单.xlsx》）

### 完整设备清单

| 清单编号 | 设备名称 | 数量 | 设备类型标识(equipment_type) | 估算额定功率(kW) | 能效曲线类型 |
|----------|----------|------|-------------------------------|-------------------|--------------|
| A-1 | 电芯外观检测机 | 10 | `appearance_inspector` | 3.0 | linear |
| B-2 | 电芯尺寸检测机 | 5 | `dimension_inspector` | 2.5 | linear |
| C-3 | 电芯卷绕机 | 15 | `winding_machine` | 15.0 | linear |
| D-4 | 电芯化成柜 | 10 | `formation_cabinet` | 8.0 | polynomial |
| E-5 | 电芯分选机 | 5 | `sorting_machine` | 4.0 | linear |
| F-6 | 电芯外观检测机 | 5 | `appearance_inspector` | 3.0 | linear |
| G-7 | 电芯分选机 | 5 | `sorting_machine` | 4.0 | linear |
| H-8 | 电芯输送流水线 | 1 | `conveyor_line` | 5.5 | quadratic |
| I-9 | 电芯烘烤炉 | 1 | `baking_oven` | 45.0 | polynomial |
| J-10 | 电芯化成柜 | 6 | `formation_cabinet` | 8.0 | polynomial |
| K-11 | 自动导引运输车AGV | 2 | `agv` | 1.5（充电功率） | linear |
| L-12 | 数控龙门铣床 | 4 | `cnc_milling_machine` | 18.5 | polynomial |

> **说明**：A-1与F-6同为外观检测机、D-4与J-10同为化成柜、E-5与G-7同为分选机，属不同产线/车间的同类型设备，`equipment_type`相同但`equipment_id`不同。

### 公用动力设备（清单未列但项目方案要求监测）

项目方案明确要求监测空压机、冷却风机等公用动力设备，需在设备清单基础上补充：

| 设备类型标识 | 设备名称 | 建议数量 | 估算额定功率(kW) | 能效曲线类型 |
|--------------|----------|----------|-------------------|--------------|
| `compressor` | 空压机 | 3 | 75.0 | polynomial |
| `cooling_fan` | 冷却风机 | 4 | 15.0 | quadratic |
| `chiller` | 冷水机组 | 2 | 55.0 | polynomial |

### 设备ID命名规则

**格式：`{清单编号}-{两位序号}`**

| 示例 | 含义 |
|------|------|
| `A-1-01` ~ `A-1-10` | A-1批次的10台外观检测机 |
| `C-3-01` ~ `C-3-15` | C-3批次的15台卷绕机 |
| `I-9-01` | 唯一1台烘烤炉 |
| `COMP-01` ~ `COMP-03` | 公用空压机（公用设备用类型缩写+序号） |
| `FAN-01` ~ `FAN-04` | 公用冷却风机 |

### 车间划分建议

| 车间编号 | 车间名称 | 包含设备 |
|----------|----------|----------|
| WS-01 | 电芯制备车间 | C-3卷绕机、H-8输送流水线、I-9烘烤炉 |
| WS-02 | 电芯化成车间 | D-4化成柜、J-10化成柜 |
| WS-03 | 电芯检测分选车间 | A-1外观检测机、B-2尺寸检测机、E-5分选机、F-6外观检测机、G-7分选机 |
| WS-04 | 模具加工车间 | L-12数控龙门铣床 |
| WS-05 | 物流动力区 | K-11 AGV、空压机、冷却风机、冷水机组 |

### 班组划分建议

| 班组编号 | 班组名称 | 班次 |
|----------|----------|------|
| TEAM-A | 甲班（早班） | 8:00-16:00 |
| TEAM-B | 乙班（中班） | 16:00-0:00 |
| TEAM-C | 丙班（夜班） | 0:00-8:00 |

---

## 二、需要编写的文件清单（按开发顺序）

### 阶段0：基础设施（先写这3个）

| 序号 | 文件路径 | 作用 | 优先级 |
|------|----------|------|--------|
| 0-1 | `requirements.txt` | 声明所有Python依赖 | 🔴最高 |
| 0-2 | `config/__init__.py` | 包初始化 | 🔴最高 |
| 0-3 | `config/settings.py` | 全局配置：模型超参、碳排因子、阈值、路径 | 🔴最高 |

### 阶段1：数据与特征工程

| 序号 | 文件路径 | 作用 | 优先级 |
|------|----------|------|--------|
| 1-1 | `feature_engineer/__init__.py` | 包初始化 | 🔴高 |
| 1-2 | `feature_engineer/data_loader.py` | 加载CSV/数据库数据，统一DataFrame格式 | 🔴高 |
| 1-3 | `feature_engineer/data_cleaner.py` | 缺失值填充、异常值剔除、时间对齐 | 🔴高 |
| 1-4 | `feature_engineer/feature_extractor.py` | 提取负载率、运行时长、能耗统计、滑窗统计特征 | 🔴高 |
| 1-5 | `feature_engineer/sequence_builder.py` | 将时序数据切成LSTM输入序列（滑窗） | 🔴高 |

### 阶段2：LSTM异常检测模型

| 序号 | 文件路径 | 作用 | 优先级 |
|------|----------|------|--------|
| 2-1 | `Lstm_model/__init__.py` | 包初始化 | 🔴高 |
| 2-2 | `Lstm_model/model.py` | PyTorch LSTM模型定义（Encoder结构） | 🔴高 |
| 2-3 | `Lstm_model/train.py` | 模型训练脚本（含早停、 checkpoint保存） | 🔴高 |
| 2-4 | `Lstm_model/predict.py` | 单步/多步预测，输出预测值与重建误差 | 🔴高 |
| 2-5 | `Lstm_model/anomaly_detector.py` | 异常检测：自适应阈值、基线学习、超标判定 | 🔴高 |
| 2-6 | `Lstm_model/evaluate.py` | 模型评估：准确率/召回率/F1、混淆矩阵 | 🟡中 |

### 阶段3：碳排核算与降碳策略

| 序号 | 文件路径 | 作用 | 优先级 |
|------|----------|------|--------|
| 3-1 | `carbon_strategy/__init__.py` | 包初始化 | 🔴高 |
| 3-2 | `carbon_strategy/carbon_calculator.py` | IPCC因子碳排换算 + 四级聚合（厂区/车间/设备/班组） | 🔴高 |
| 3-3 | `carbon_strategy/equipment_models.py` | 设备机理模型：烘烤炉温控曲线、化成柜充放电能效、空压机能效曲线、风机特性方程 | 🟡中 |
| 3-4 | `carbon_strategy/traceability.py` | 溯源：72小时历史查询、高碳排根因定位 | 🔴高 |
| 3-5 | `carbon_strategy/strategy_engine.py` | 降碳方案推理：多目标优化，输出三类方案 | 🔴高 |

### 阶段4：API服务层（对接后端）

| 序号 | 文件路径 | 作用 | 优先级 |
|------|----------|------|--------|
| 4-1 | `api_server/__init__.py` | 包初始化 | 🔴高 |
| 4-2 | `api_server/schemas.py` | Pydantic请求/响应数据模型 | 🔴高 |
| 4-3 | `api_server/services.py` | 业务逻辑层：调用算法模块，组装返回数据 | 🔴高 |
| 4-4 | `api_server/routes.py` | FastAPI路由：所有算法接口端点 | 🔴高 |

### 阶段5：入口与文档

| 序号 | 文件路径 | 作用 | 优先级 |
|------|----------|------|--------|
| 5-1 | `main.py`（重写） | FastAPI应用入口，挂载所有路由 | 🔴高 |
| 5-2 | `docs/algorithm_interface.md` | 算法接口文档（给后端同学） | 🔴高 |
| 5-3 | `docs/model_intro.md` | 模型原理与使用说明 | 🟡中 |
| 5-4 | `data/raw_data/sample_equipment_data.csv` | 模拟设备数据（测试用） | 🟡中 |

---

## 三、每个文件的详细编写指令

### 阶段0：基础设施

#### 0-1 `requirements.txt`

直接写入以下内容（团队Python版本建议3.10+）：

```
# === Web框架 ===
fastapi==0.115.0
uvicorn==0.30.6
pydantic==2.9.2

# === 数据处理 ===
pandas==2.2.2
numpy==1.26.4

# === 深度学习 ===
torch==2.4.0
scikit-learn==1.5.1

# === 数据库（后端对接用） ===
sqlalchemy==2.0.35
pymysql==1.1.1

# === 工具 ===
python-dotenv==1.0.1
joblib==1.4.2
matplotlib==3.9.2
```

> 注意：torch安装可能需要根据CUDA版本调整，开发阶段用CPU版即可。

#### 0-2 `config/__init__.py`

```python
from config.settings import (
    settings, CARBON_FACTORS, MODEL_CONFIG, THRESHOLD_CONFIG,
    EQUIPMENT_TYPES, EQUIPMENT_LIST, WORKSHOPS, TEAMS,
)

__all__ = [
    'settings', 'CARBON_FACTORS', 'MODEL_CONFIG', 'THRESHOLD_CONFIG',
    'EQUIPMENT_TYPES', 'EQUIPMENT_LIST', 'WORKSHOPS', 'TEAMS',
]
```

#### 0-3 `config/settings.py`

需要包含以下配置字典，**所有硬编码参数都放这里，不要散落在各模块**：

```python
import os
from pathlib import Path

# === 项目路径 ===
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
RAW_DATA_DIR = DATA_DIR / 'raw_data'
PROCESS_DATA_DIR = DATA_DIR / 'process_data'
OUTPUT_DIR = BASE_DIR / 'output'
MODEL_WEIGHT_DIR = OUTPUT_DIR / 'model_weight'
LOG_DIR = OUTPUT_DIR / 'log'
CHART_DIR = OUTPUT_DIR / 'chart'

# 确保目录存在
for d in [PROCESS_DATA_DIR, MODEL_WEIGHT_DIR, LOG_DIR, CHART_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === IPCC碳排放核算因子（单位：kgCO2/单位能源）===
# 数据来源：IPCC 2006 Guidelines + 中国区域电网平均排放因子
CARBON_FACTORS = {
    'electricity': 0.5810,       # kgCO2/kWh（中国南方电网区域因子）
    'natural_gas': 2.1622,       # kgCO2/m³
    'coal': 2.6600,               # kgCO2/kg
    'diesel': 3.0959,             # kgCO2/L
    'compressed_air': 0.12,       # kgCO2/m³（估算，基于空压机能耗换算）
}

# === LSTM模型超参数 ===
MODEL_CONFIG = {
    'input_size': 8,              # 输入特征维度（负载率、电压、电流、功率、能耗、温度、振动、运行时长）
    'hidden_size': 128,           # LSTM隐藏层维度
    'num_layers': 2,              # LSTM层数
    'output_size': 8,             # 输出维度（重建输入，自编码器模式）
    'dropout': 0.2,
    'sequence_length': 60,        # 输入序列长度（60分钟数据）
    'prediction_steps': 1,        # 预测步数
    'batch_size': 32,
    'learning_rate': 0.001,
    'epochs': 100,
    'early_stopping_patience': 10,
    'device': 'cpu',              # 开发用cpu，部署可改cuda
}

# === 异常检测阈值配置 ===
THRESHOLD_CONFIG = {
    'method': 'adaptive',         # adaptive=自适应阈值, fixed=固定阈值
    'fixed_threshold': 0.5,       # 固定阈值（重建误差MSE）
    'adaptive_window': 24,        # 自适应窗口（小时），用过去24小时误差均值+3σ
    'sigma_multiplier': 3.0,      # 标准差倍数
    'alert_cooldown_seconds': 600, # 同一设备告警冷却时间（10分钟），避免频繁告警
}

# === 设备类型配置（基于《设备清单.xlsx》+ 公用动力设备）===
# key = equipment_type标识，value = 设备元信息
# 额定功率为估算值，实际部署时以设备铭牌为准
EQUIPMENT_TYPES = {
    # === 生产设备（来自设备清单）===
    'appearance_inspector': {
        'name': '电芯外观检测机', 'rated_power': 3.0,
        'efficiency_curve': 'linear', 'category': '检测设备',
    },
    'dimension_inspector': {
        'name': '电芯尺寸检测机', 'rated_power': 2.5,
        'efficiency_curve': 'linear', 'category': '检测设备',
    },
    'winding_machine': {
        'name': '电芯卷绕机', 'rated_power': 15.0,
        'efficiency_curve': 'linear', 'category': '生产设备',
    },
    'formation_cabinet': {
        'name': '电芯化成柜', 'rated_power': 8.0,
        'efficiency_curve': 'polynomial', 'category': '生产设备',
    },
    'sorting_machine': {
        'name': '电芯分选机', 'rated_power': 4.0,
        'efficiency_curve': 'linear', 'category': '检测设备',
    },
    'conveyor_line': {
        'name': '电芯输送流水线', 'rated_power': 5.5,
        'efficiency_curve': 'quadratic', 'category': '物流设备',
    },
    'baking_oven': {
        'name': '电芯烘烤炉', 'rated_power': 45.0,
        'efficiency_curve': 'polynomial', 'category': '生产设备',
    },
    'agv': {
        'name': '自动导引运输车AGV', 'rated_power': 1.5,
        'efficiency_curve': 'linear', 'category': '物流设备',
    },
    'cnc_milling_machine': {
        'name': '数控龙门铣床', 'rated_power': 18.5,
        'efficiency_curve': 'polynomial', 'category': '加工设备',
    },
    # === 公用动力设备（清单未列但项目方案要求监测）===
    'compressor': {
        'name': '空压机', 'rated_power': 75.0,
        'efficiency_curve': 'polynomial', 'category': '公用动力',
    },
    'cooling_fan': {
        'name': '冷却风机', 'rated_power': 15.0,
        'efficiency_curve': 'quadratic', 'category': '公用动力',
    },
    'chiller': {
        'name': '冷水机组', 'rated_power': 55.0,
        'efficiency_curve': 'polynomial', 'category': '公用动力',
    },
}

# === 设备清单明细（每台设备的唯一ID映射）===
# key = equipment_id, value = {equipment_type, name, workshop_id, team_id}
# 命名规则：{清单编号}-{两位序号}，公用设备用{类型缩写}-{两位序号}
EQUIPMENT_LIST = {
    # A-1 电芯外观检测机 ×10（WS-03检测车间）
    **{f'A-1-{i:02d}': {'equipment_type': 'appearance_inspector', 'name': f'外观检测机{i}号',
                          'workshop_id': 'WS-03', 'team_id': 'TEAM-A'} for i in range(1, 11)},
    # B-2 电芯尺寸检测机 ×5（WS-03检测车间）
    **{f'B-2-{i:02d}': {'equipment_type': 'dimension_inspector', 'name': f'尺寸检测机{i}号',
                          'workshop_id': 'WS-03', 'team_id': 'TEAM-A'} for i in range(1, 6)},
    # C-3 电芯卷绕机 ×15（WS-01制备车间）
    **{f'C-3-{i:02d}': {'equipment_type': 'winding_machine', 'name': f'卷绕机{i}号',
                          'workshop_id': 'WS-01', 'team_id': 'TEAM-A'} for i in range(1, 16)},
    # D-4 电芯化成柜 ×10（WS-02化成车间，24小时运行）
    **{f'D-4-{i:02d}': {'equipment_type': 'formation_cabinet', 'name': f'化成柜{i}号',
                          'workshop_id': 'WS-02', 'team_id': 'TEAM-A'} for i in range(1, 11)},
    # E-5 电芯分选机 ×5（WS-03检测车间）
    **{f'E-5-{i:02d}': {'equipment_type': 'sorting_machine', 'name': f'分选机{i}号',
                          'workshop_id': 'WS-03', 'team_id': 'TEAM-A'} for i in range(1, 6)},
    # F-6 电芯外观检测机 ×5（WS-03检测车间，第二条检测线）
    **{f'F-6-{i:02d}': {'equipment_type': 'appearance_inspector', 'name': f'外观检测机{10+i}号',
                          'workshop_id': 'WS-03', 'team_id': 'TEAM-B'} for i in range(1, 6)},
    # G-7 电芯分选机 ×5（WS-03检测车间，第二条分选线）
    **{f'G-7-{i:02d}': {'equipment_type': 'sorting_machine', 'name': f'分选机{5+i}号',
                          'workshop_id': 'WS-03', 'team_id': 'TEAM-B'} for i in range(1, 6)},
    # H-8 电芯输送流水线 ×1（WS-01制备车间）
    'H-8-01': {'equipment_type': 'conveyor_line', 'name': '主输送流水线',
                'workshop_id': 'WS-01', 'team_id': 'TEAM-A'},
    # I-9 电芯烘烤炉 ×1（WS-01制备车间，高耗能重点监测）
    'I-9-01': {'equipment_type': 'baking_oven', 'name': '电芯烘烤炉',
                'workshop_id': 'WS-01', 'team_id': 'TEAM-A'},
    # J-10 电芯化成柜 ×6（WS-02化成车间，第二条化成线）
    **{f'J-10-{i:02d}': {'equipment_type': 'formation_cabinet', 'name': f'化成柜{10+i}号',
                           'workshop_id': 'WS-02', 'team_id': 'TEAM-B'} for i in range(1, 7)},
    # K-11 AGV ×2（WS-05物流区，充电时计入能耗）
    **{f'K-11-{i:02d}': {'equipment_type': 'agv', 'name': f'AGV{i}号',
                          'workshop_id': 'WS-05', 'team_id': 'TEAM-A'} for i in range(1, 3)},
    # L-12 数控龙门铣床 ×4（WS-04加工车间）
    **{f'L-12-{i:02d}': {'equipment_type': 'cnc_milling_machine', 'name': f'龙门铣床{i}号',
                          'workshop_id': 'WS-04', 'team_id': 'TEAM-A'} for i in range(1, 5)},
    # 公用动力设备
    **{f'COMP-{i:02d}': {'equipment_type': 'compressor', 'name': f'空压机{i}号',
                          'workshop_id': 'WS-05', 'team_id': 'TEAM-A'} for i in range(1, 4)},
    **{f'FAN-{i:02d}': {'equipment_type': 'cooling_fan', 'name': f'冷却风机{i}号',
                         'workshop_id': 'WS-05', 'team_id': 'TEAM-A'} for i in range(1, 5)},
    **{f'CHILL-{i:02d}': {'equipment_type': 'chiller', 'name': f'冷水机组{i}号',
                           'workshop_id': 'WS-05', 'team_id': 'TEAM-A'} for i in range(1, 3)},
}

# === 车间配置 ===
WORKSHOPS = {
    'WS-01': {'name': '电芯制备车间', 'equipment_count': 17},
    'WS-02': {'name': '电芯化成车间', 'equipment_count': 16},
    'WS-03': {'name': '电芯检测分选车间', 'equipment_count': 30},
    'WS-04': {'name': '模具加工车间', 'equipment_count': 4},
    'WS-05': {'name': '物流动力区', 'equipment_count': 11},
}

# === 班组配置 ===
TEAMS = {
    'TEAM-A': {'name': '甲班（早班）', 'shift': '8:00-16:00'},
    'TEAM-B': {'name': '乙班（中班）', 'shift': '16:00-0:00'},
    'TEAM-C': {'name': '丙班（夜班）', 'shift': '0:00-8:00'},
}

# === 四级层级配置 ===
HIERARCHY_LEVELS = ['factory', 'workshop', 'equipment', 'team']

# === API配置 ===
API_CONFIG = {
    'host': '0.0.0.0',
    'port': 8000,
    'reload': True,
}

# 统一导出
settings = {
    'BASE_DIR': BASE_DIR,
    'DATA_DIR': DATA_DIR,
    'RAW_DATA_DIR': RAW_DATA_DIR,
    'PROCESS_DATA_DIR': PROCESS_DATA_DIR,
    'OUTPUT_DIR': OUTPUT_DIR,
    'MODEL_WEIGHT_DIR': MODEL_WEIGHT_DIR,
    'LOG_DIR': LOG_DIR,
    'CHART_DIR': CHART_DIR,
    'API_CONFIG': API_CONFIG,
    'HIERARCHY_LEVELS': HIERARCHY_LEVELS,
    'EQUIPMENT_TYPES': EQUIPMENT_TYPES,
    'EQUIPMENT_LIST': EQUIPMENT_LIST,
    'WORKSHOPS': WORKSHOPS,
    'TEAMS': TEAMS,
}
```

---

### 阶段1：数据与特征工程

#### 1-1 `feature_engineer/__init__.py`

```python
from feature_engineer.data_loader import DataLoader
from feature_engineer.data_cleaner import DataCleaner
from feature_engineer.feature_extractor import FeatureExtractor
from feature_engineer.sequence_builder import SequenceBuilder

__all__ = ['DataLoader', 'DataCleaner', 'FeatureExtractor', 'SequenceBuilder']
```

#### 1-2 `feature_engineer/data_loader.py`

**核心类：`DataLoader`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `load_csv(file_path)` | 文件路径 | pd.DataFrame | 加载单个CSV |
| `load_equipment_data(equipment_id, start_time, end_time)` | 设备ID+时间范围 | pd.DataFrame | 从数据库/CSV加载指定设备时序数据 |
| `load_batch_data(equipment_ids, start_time, end_time)` | 设备ID列表+时间范围 | dict[str, DataFrame] | 批量加载多设备数据 |
| `load_hierarchy_data(level, node_id)` | 层级+节点ID | pd.DataFrame | 加载指定层级聚合数据 |

**DataFrame统一格式要求（所有下游模块都依赖这个格式）：**

| 列名 | 类型 | 说明 |
|------|------|------|
| `timestamp` | datetime | 时间戳（分钟级） |
| `equipment_id` | str | 设备唯一编号，如'C-3-01'（卷绕机1号）、'I-9-01'（烘烤炉）、'COMP-01'（空压机1号）。命名规则见「一点五、设备清单对照」 |
| `equipment_type` | str | 设备类型标识：winding_machine/formation_cabinet/baking_oven/compressor/cooling_fan等，共12类（9类生产设备+3类公用动力），见EQUIPMENT_TYPES |
| `workshop_id` | str | 所属车间编号：WS-01制备/WS-02化成/WS-03检测/WS-04加工/WS-05物流动力 |
| `team_id` | str | 所属班组编号：TEAM-A甲班/TEAM-B乙班/TEAM-C丙班 |
| `voltage` | float | 电压(V) |
| `current` | float | 电流(A) |
| `power` | float | 有功功率(kW) |
| `energy` | float | 累计能耗(kWh) |
| `load_rate` | float | 负载率(0-1) |
| `temperature` | float | 设备温度(℃) |
| `vibration` | float | 振动值(mm/s) |
| `runtime_hours` | float | 累计运行时长(h) |
| `status` | int | 运行状态：1=运行, 0=停机, 2=待机 |

#### 1-3 `feature_engineer/data_cleaner.py`

**核心类：`DataCleaner`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `clean(df)` | 原始DataFrame | 清洗后DataFrame | 主入口，依次执行所有清洗步骤 |
| `handle_missing_values(df, method)` | DataFrame, 填充方法 | DataFrame | 缺失值处理：前向填充/插值/均值 |
| `remove_outliers(df, columns, method)` | DataFrame, 列名, 方法 | DataFrame | 异常值剔除：3σ原则/IQR方法 |
| `align_time_series(df, freq)` | DataFrame, 频率 | DataFrame | 时间对齐：重采样到固定频率（分钟级） |
| `add_time_features(df)` | DataFrame | DataFrame | 添加时间特征：小时、星期、是否工作日、班次 |

**关键实现要点：**
- 缺失值优先用线性插值（时序数据），极端缺失用设备同时段均值
- 异常值用3σ原则，超过均值±3σ的标记为异常并用前后均值替换
- 时间对齐到1分钟频率，确保LSTM输入等间隔
- 添加`shift`列：早班(8-16)/中班(16-24)/夜班(0-8)

#### 1-4 `feature_engineer/feature_extractor.py`

**核心类：`FeatureExtractor`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `extract(df)` | 清洗后DataFrame | 特征DataFrame | 主入口，提取全部特征 |
| `statistical_features(df, window)` | DataFrame, 窗口大小 | DataFrame | 滑窗统计特征：均值/标准差/最大/最小/斜率 |
| `energy_features(df)` | DataFrame | DataFrame | 能耗特征：瞬时功率、功率变化率、单位产量能耗 |
| `equipment_health_features(df)` | DataFrame | DataFrame | 设备健康特征：温升率、振动趋势、负载波动 |
| `carbon_features(df)` | DataFrame | DataFrame | 碳排特征：实时碳排、碳排强度、累计碳排 |

**提取的特征列表（共8维输入，对应MODEL_CONFIG.input_size=8）：**

1. `load_rate` — 负载率
2. `power` — 有功功率(kW)
3. `energy_diff` — 能耗增量(kWh/min)
4. `temperature` — 设备温度
5. `vibration` — 振动值
6. `carbon_emission` — 实时碳排(kgCO2/min)
7. `power_change_rate` — 功率变化率
8. `runtime_hours` — 累计运行时长

#### 1-5 `feature_engineer/sequence_builder.py`

**核心类：`SequenceBuilder`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `build_sequences(features_df, seq_length)` | 特征DataFrame, 序列长度 | (X, y) numpy数组 | 构建LSTM训练序列 |
| `build_single_sequence(features_df, end_idx, seq_length)` | 特征DataFrame, 结束位置, 序列长度 | numpy数组 | 构建单条推理序列（实时预测用） |
| `train_test_split(X, y, test_size)` | 序列数据, 测试集比例 | (X_train, y_train, X_test, y_test) | 按时间顺序划分（不能随机打乱！） |
| `normalize(X_train, X_test)` | 训练/测试序列 | (归一化数据, scaler对象) | MinMax归一化，保存scaler供推理时反归一化 |

**关键实现要点：**
- 序列形状：`(样本数, sequence_length, input_size)` = `(N, 60, 8)`
- 自编码器模式：y = X（输入即输出，学习重建）
- 训练测试集必须按时间顺序划分，前80%训练，后20%测试
- 归一化用MinMaxScaler，保存到`output/model_weight/scaler.pkl`

---

### 阶段2：LSTM异常检测模型

#### 2-1 `Lstm_model/__init__.py`

```python
from Lstm_model.model import LSTMAutoencoder
from Lstm_model.anomaly_detector import AnomalyDetector
from Lstm_model.predict import ModelPredictor

__all__ = ['LSTMAutoencoder', 'AnomalyDetector', 'ModelPredictor']
```

#### 2-2 `Lstm_model/model.py`

**核心类：`LSTMAutoencoder(nn.Module)`**

采用LSTM自编码器架构（无监督学习，不需要标注异常数据）：

```
输入序列(60,8) → Encoder LSTM(2层,128隐层) → 隐向量(128,)
→ RepeatVector(60) → Decoder LSTM(2层,128隐层) → 输出序列(60,8)
```

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `forward(x)` | (batch, seq_len, input_size) | (batch, seq_len, input_size) | 前向传播，重建输入 |
| `encode(x)` | 输入序列 | (batch, hidden_size) | 编码为隐向量 |
| `decode(h, seq_len)` | 隐向量, 序列长度 | 重建序列 | 解码重建 |

**关键实现要点：**
- 使用PyTorch nn.LSTM，bidirectional=False
- Encoder和Decoder各2层，hidden_size=128
- 最后一层接Linear(hidden_size, output_size)
- dropout=0.2
- 损失函数：MSELoss（重建误差）

#### 2-3 `Lstm_model/train.py`

**核心函数：`train_model(train_loader, val_loader, model, config)`**

| 参数 | 说明 |
|------|------|
| `train_loader` | 训练集DataLoader |
| `val_loader` | 验证集DataLoader |
| `model` | LSTMAutoencoder实例 |
| `config` | MODEL_CONFIG字典 |

**训练流程：**
1. 优化器：Adam(lr=0.001)
2. 损失函数：MSELoss
3. 学习率调度：ReduceLROnPlateau（验证损失不降则降lr）
4. 早停：验证损失连续10个epoch不下降则停止
5. 保存最佳模型到`output/model_weight/lstm_autoencoder_best.pth`
6. 保存训练曲线到`output/chart/training_curve.png`

**命令行入口：**
```bash
# 训练指定设备的模型（以烘烤炉I-9-01为例，高耗能重点设备）
python -m Lstm_model.train --data data/raw_data/sample_equipment_data.csv --equipment_id I-9-01

# 训练空压机模型（公用动力重点设备）
python -m Lstm_model.train --data data/raw_data/sample_equipment_data.csv --equipment_id COMP-01

# 训练卷绕机模型
python -m Lstm_model.train --data data/raw_data/sample_equipment_data.csv --equipment_id C-3-01
```

> 建议为每类设备单独训练一个模型，同类设备可共用一个模型。优先训练高耗能设备：baking_oven(45kW)、compressor(75kW)、chiller(55kW)、cnc_milling_machine(18.5kW)、winding_machine(15kW)。

#### 2-4 `Lstm_model/predict.py`

**核心类：`ModelPredictor`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `__init__(model_path, scaler_path, device)` | 模型路径, scaler路径, 设备 | - | 加载训练好的模型和scaler |
| `predict_reconstruction(sequence)` | 单条序列(60,8) | 重建序列(60,8) | 模型推理，返回重建结果 |
| `compute_reconstruction_error(sequence)` | 单条序列 | float | 计算重建误差（MSE） |
| `predict_batch(sequences)` | 批量序列 | 误差数组 | 批量计算重建误差 |

**关键实现要点：**
- 模型加载时用`model.eval()`和`torch.no_grad()`
- 输入数据必须先用训练时保存的scaler归一化
- 重建误差 = mean((输入 - 输出)^2)
- 单条推理延迟应<100ms（满足10秒告警要求）

#### 2-5 `Lstm_model/anomaly_detector.py`

**核心类：`AnomalyDetector`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `__init__(threshold_config)` | THRESHOLD_CONFIG | - | 初始化阈值策略 |
| `update_baseline(errors)` | 历史误差数组 | None | 更新正常基线（自适应阈值用） |
| `detect(reconstruction_error, equipment_id)` | 重建误差, 设备ID | dict | 判断是否异常，返回检测结果 |
| `get_adaptive_threshold()` | - | float | 计算当前自适应阈值（均值+Nσ） |
| `should_alert(equipment_id, is_anomaly)` | 设备ID, 是否异常 | bool | 判断是否应该发告警（冷却时间控制） |

**检测结果dict格式：**
```python
{
    'is_anomaly': True/False,
    'reconstruction_error': 0.35,
    'threshold': 0.28,
    'threshold_type': 'adaptive',
    'anomaly_score': 1.25,  # 误差/阈值的比值
    'equipment_id': 'I-9-01',
    'equipment_name': '电芯烘烤炉',
    'timestamp': '2026-08-21 14:30:00',
    'severity': 'high',  # high/medium/low
}
```

**关键实现要点：**
- 自适应阈值：用过去24小时（1440条）重建误差的均值 + 3×标准差
- 严重程度分级：error/threshold > 2 = high, >1.5 = medium, >1 = low
- 告警冷却：同一设备10分钟内只告警一次，避免频繁弹窗
- 基线数据保存在内存中（开发阶段），生产环境可放Redis

#### 2-6 `Lstm_model/evaluate.py`

**核心函数：**
- `evaluate_model(model, test_loader, device)` — 计算整体重建误差分布
- `classification_report(y_true, y_pred)` — 输出准确率/召回率/F1/混淆矩阵
- `plot_error_distribution(errors, threshold, save_path)` — 绘制误差分布图
- `save_evaluation_report(results, save_path)` — 保存评估报告到JSON

> 目标指标：AI方案生成准确率≥85%（对应异常检测F1≥0.85）

---

### 阶段3：碳排核算与降碳策略

#### 3-1 `carbon_strategy/__init__.py`

```python
from carbon_strategy.carbon_calculator import CarbonCalculator
from carbon_strategy.traceability import TraceabilityAnalyzer
from carbon_strategy.strategy_engine import CarbonStrategyEngine

__all__ = ['CarbonCalculator', 'TraceabilityAnalyzer', 'CarbonStrategyEngine']
```

#### 3-2 `carbon_strategy/carbon_calculator.py`

**核心类：`CarbonCalculator`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `calculate_emission(energy_type, energy_amount)` | 能源类型, 消耗量 | float(kgCO2) | 单能源碳排换算 |
| `calculate_equipment_emission(equipment_data)` | 设备时序DataFrame | DataFrame | 计算单设备实时碳排（添加carbon_emission列） |
| `aggregate_by_level(df, level)` | DataFrame, 层级 | DataFrame | 按指定层级聚合碳排 |
| `aggregate_factory(df)` | 全量DataFrame | dict | 厂区级汇总：总碳排、趋势、强度 |
| `aggregate_workshop(df)` | 全量DataFrame | DataFrame | 车间级对比 |
| `calculate_carbon_intensity(df, production_output)` | 数据, 产量 | float | 单位产品碳排强度(kgCO2/件) |

**四级聚合逻辑：**
- **设备级**：每台设备每分钟碳排 = 功率(kW) × 时间(h) × 电力排放因子
- **班组级**：按team_id分组，sum(设备碳排)，计算单位电芯碳排
- **车间级**：按workshop_id分组，sum(班组碳排)，车间对比
- **厂区级**：sum(车间碳排)，全厂总览 + 月度/年度趋势

**关键实现要点：**
- 电力碳排 = 能耗(kWh) × 0.5810(kgCO2/kWh)
- 压缩空气碳排需通过空压机能耗间接换算
- 所有计算结果保留4位小数
- 兼容国标GB/T 32150温室气体核算规范

#### 3-3 `carbon_strategy/equipment_models.py`

**核心类/函数（按设备类型分类，覆盖清单中9类生产设备+3类公用动力设备）：**

| 名称 | 类型 | 适用设备 | 说明 |
|------|------|----------|------|
| `baking_oven_curve(temperature_set, ambient_temp)` | 函数 | 电芯烘烤炉(I-9) | 烘烤炉温控曲线：升温/保温/降温三阶段能耗模型，温度设定值与功率关系 |
| `formation_cabinet_efficiency(charge_rate, soc)` | 函数 | 电芯化成柜(D-4, J-10) | 化成柜充放电能效：不同充电倍率(C-rate)和SOC下的能效曲线，化成阶段能耗占比高 |
| `winding_machine_power(tension, speed)` | 函数 | 电芯卷绕机(C-3) | 卷绕机功率模型：张力和卷绕速度对功率的影响，启停冲击能耗 |
| `cnc_milling_power(spindle_speed, feed_rate, depth)` | 函数 | 数控龙门铣床(L-12) | 铣床功率模型：主轴转速、进给率、切削深度的经验公式 |
| `conveyor_power(load_weight, speed)` | 函数 | 输送流水线(H-8) | 输送线功率模型：负载重量和运行速度的二次关系 |
| `inspector_power(inspection_rate)` | 函数 | 外观/尺寸检测机(A-1,B-2,F-6) | 检测设备功率模型：检测速率与功率近似线性关系 |
| `sorting_power(sorting_speed)` | 函数 | 电芯分选机(E-5,G-7) | 分选机功率模型：分选速度与功率关系 |
| `agv_charging_power(battery_soc)` | 函数 | AGV(K-11) | AGV充电功率模型：SOC与充电功率的关系，充电时段能耗 |
| `compressor_efficiency(power, pressure)` | 函数 | 空压机(公用) | 空压机能效曲线：比功率(kW/(m³/min))随负载率变化 |
| `fan_curve(flow_rate, static_pressure)` | 函数 | 冷却风机(公用) | 风机特性方程：风量-风压-功率关系（相似定律） |
| `chiller_cop(outlet_temp, ambient_temp)` | 函数 | 冷水机组(公用) | 冷水机组COP模型：出水温度和环境温度对能效比的影响 |
| `equipment_health_score(equipment_data)` | 函数 | 所有设备 | 设备健康评分(0-100)：基于温度、振动、能效衰减 |
| `estimate_energy_savings(equipment_id, current_state, target_state)` | 函数 | 所有设备 | 估算调整工况后的节能量，根据设备类型调用对应模型 |

**重点设备机理模型说明：**

**① 电芯烘烤炉温控曲线（最高耗能设备，45kW，重点监测）：**
```
三阶段能耗模型：
- 升温阶段：P = P_rated × (1 - e^(-k×t))，功率从额定值逐渐下降
- 保温阶段：P = P_heat_loss = U×A×(T_set - T_ambient)，仅补偿热损失
- 降温阶段：P = 0（自然冷却或辅助风机）
升温阶段能耗占比约60%，优化升温速率和保温温度是降碳关键
```

**② 电芯化成柜充放电能效（16台，总功率128kW，数量最多的高耗能设备）：**
```
能效 = 放电能量 / 充电能量 × 100%
- 充电倍率0.5C时能效约92%，1C时约88%，2C时约82%
- SOC在20%-80%区间能效最优，低于10%或高于95%能效下降
- 化成阶段的焦耳热损耗 = I²×R，大电流充电损耗显著
降碳策略：优化充电倍率曲线，避免高倍率长时间充电
```

**③ 空压机能效曲线（公用动力，75kW，能效优化空间大）：**
```
比功率 = a0 + a1×负载率 + a2×负载率² + a3×负载率³
（负载率在60%-80%区间能效最优，低于40%能效急剧下降）
```

**④ 风机特性方程（冷却风机，15kW×4台）：**
```
功率 ∝ 风量³（相似定律）
风量下调20%，功率可下降约50%
变频改造是风机降碳最有效手段
```

**⑤ 数控龙门铣床功率模型（L-12，18.5kW×4台）：**
```
P = P_idle + k1×spindle_speed + k2×feed_rate×depth
空载功率约占额定30%，切削功率与材料去除率正相关
降碳策略：优化切削参数，减少空载等待时间
```

#### 3-4 `carbon_strategy/traceability.py`

**核心类：`TraceabilityAnalyzer`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `get_equipment_history(equipment_id, hours=72)` | 设备ID, 回溯小时数 | DataFrame | 查询设备近72小时运行参数 |
| `analyze_root_cause(equipment_id, anomaly_time)` | 设备ID, 异常时间点 | dict | 高碳排根因分析 |
| `compare_with_baseline(equipment_id, period)` | 设备ID, 对比周期 | dict | 与历史同期/同类设备基线对比 |
| `generate_trace_report(equipment_id, anomaly_time)` | 设备ID, 异常时间 | dict | 生成完整溯源报告 |

**根因分析逻辑（按可能性排序，针对锂电工厂设备特性）：**
1. **烘烤炉温控异常** — 实际温度偏离设定值>5℃，或升温时间超过标准30%（I-9烘烤炉最常见，高耗能）
2. **化成柜充电倍率过高** — 充电倍率>1C持续超过化成工艺标准时间，导致焦耳热损耗增加（D-4/J-10化成柜）
3. **设备空载/低负载运行** — 负载率<40%持续超过30分钟（空压机/风机最常见，卷绕机待机也常见）
4. **设备老化/能效衰减** — 对比历史同时段，相同负载下能耗上升>15%
5. **工艺参数异常** — 卷绕张力/速度偏离设定值，铣床切削参数不合理
6. **生产排班不合理** — 高峰电价时段满负荷，低谷时段停机
7. **设备故障前兆** — 振动值/温度持续上升，伴随能效下降（铣床、风机、空压机）

**溯源报告dict格式（以烘烤炉I-9-01为例）：**
```python
{
    'equipment_id': 'I-9-01',
    'equipment_name': '电芯烘烤炉',
    'equipment_type': 'baking_oven',
    'workshop_id': 'WS-01',
    'anomaly_time': '2026-08-21 14:30:00',
    'carbon_emission': 26.2,  # kgCO2/h
    'baseline_emission': 18.5,
    'excess_emission': 7.7,
    'root_causes': [
        {'cause': '温控异常-保温温度偏高', 'confidence': 0.88,
         'detail': '设定温度120℃，实际平均132℃，超温12℃，保温阶段功率比基准高42%'},
        {'cause': '升温时间过长', 'confidence': 0.72,
         'detail': '标准升温时间35min，实际52min，升温阶段多耗能约3.2kWh'},
        {'cause': '设备老化-保温层衰减', 'confidence': 0.55,
         'detail': '对比上月同期，相同设定温度下能耗上升18%，疑似保温层老化'},
    ],
    'history_72h_summary': {'avg_load': 0.78, 'avg_emission': 21.3, 'runtime': 71.5,
                              'avg_temp': 125.6, 'temp_deviation': 5.6},
    'recommendation': '建议校准温度传感器，检查保温层密封情况，优化升温曲线（阶梯升温），预计可降碳15%',
}
```

#### 3-5 `carbon_strategy/strategy_engine.py`

**核心类：`CarbonStrategyEngine`**

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `generate_strategies(equipment_id, analysis_result)` | 设备ID, 溯源结果 | list[dict] | 生成全部三类降碳方案 |
| `equipment_maintenance_strategy(equipment_id, analysis)` | 设备ID, 分析 | dict | 设备运维方案 |
| `production_scheduling_strategy(workshop_id, data)` | 车间ID, 数据 | dict | 生产排班方案 |
| `process_optimization_strategy(equipment_id, data)` | 设备ID, 数据 | dict | 工艺优化方案 |
| `estimate_savings(strategy)` | 方案dict | dict | 估算方案预期节能/减碳量/经济效益 |
| `rank_strategies(strategies)` | 方案列表 | list[dict] | 按投入产出比排序 |

**三类方案输出格式（基于实际设备清单）：**

**① 设备运维方案（以烘烤炉I-9-01为例，最高耗能设备）：**
```python
{
    'strategy_type': 'equipment_maintenance',
    'title': '电芯烘烤炉温控校准与保温层维护',
    'target_equipment': 'I-9-01',
    'target_equipment_name': '电芯烘烤炉',
    'workshop_id': 'WS-01',
    'actions': [
        '校准温度传感器：实测温度偏高12℃，需重新校准PT100传感器（已运行6800h）',
        '检查炉门密封与保温层：红外热成像检测热泄漏点，更换老化密封条',
        '优化升温曲线：从线性升温改为阶梯升温（80℃保温10min→120℃），减少升温过冲',
        '建立定期维护台账：每3个月校准一次温控，每6个月检查保温层',
    ],
    'estimated_energy_saving': '15.2%',
    'estimated_carbon_reduction': '23.8 kgCO2/天',
    'estimated_cost_saving': '¥6,800/月',
    'investment': '¥2,000（传感器校准+密封条更换）',
    'payback_period': '0.3个月',
    'priority': 'high',
    'equipment_type': 'baking_oven',
}
```

**② 生产排班方案（以化成车间WS-02为例，16台化成柜24h运行）：**
```python
{
    'strategy_type': 'production_scheduling',
    'title': '化成车间错峰充电排班优化',
    'target_workshop': 'WS-02（电芯化成车间）',
    'equipment_count': 16,
    'current_schedule': '全天均匀充电，峰电时段(8:00-22:00)充电占比65%',
    'recommended_schedule': '大电流充电集中在谷电时段(0:00-8:00)，峰电时段仅小电流涓流补电',
    'actions': [
        '将化成柜恒流充电阶段(0.5C-1C)安排在谷电时段0:00-8:00',
        '峰电时段8:00-22:00仅进行恒压涓流补电(<0.1C)和静置老化',
        '16台化成柜分两批轮换：第一批0:00-8:00大电流，第二批8:00-16:00小电流',
        '配合MES系统排产，确保化成完成时间满足下工序节拍',
    ],
    'estimated_energy_saving': '0%（总电量不变）',
    'estimated_carbon_reduction': '8.5%（谷电时段电网碳排因子更低）',
    'estimated_cost_saving': '¥18,600/月（峰谷电价差，工业用电峰谷比约3:1）',
    'investment': '¥0（仅MES排产参数调整）',
    'payback_period': '即时',
    'priority': 'high',
    'constraints': '需确保化成工艺时间满足质量要求，大电流充电时段需人员值守',
}
```

**③ 工艺优化方案（以卷绕机C-3系列为例，15台数量最多）：**
```python
{
    'strategy_type': 'process_optimization',
    'title': '卷绕机启停时序与张力参数优化',
    'target_equipment': 'C-3-01 ~ C-3-15（15台卷绕机）',
    'target_equipment_name': '电芯卷绕机',
    'workshop_id': 'WS-01',
    'actions': [
        '优化启停时序：换卷停机时主轴降至待机转速(30%)而非全停，减少启动冲击电流',
        '15台卷绕机错峰启动：每台间隔30秒启动，避免同时启动造成车间电网峰值',
        '张力参数优化：当前平均张力12N，根据极片材质优化为分段张力(起步8N→稳态10N→收尾12N)，降低驱动电机负载',
        '卷绕速度优化：从恒定速度改为变速卷绕(内层慢→中层快→外层慢)，减少惯性能耗',
        '待机模式：换卷超过2分钟自动进入节能模式(加热辊降温至保温温度)',
    ],
    'estimated_energy_saving': '12.6%',
    'estimated_carbon_reduction': '41.5 kgCO2/天（15台合计）',
    'estimated_cost_saving': '¥11,200/月',
    'investment': '¥0（PLC程序参数调整）',
    'payback_period': '即时',
    'priority': 'medium',
    'constraints': '需验证卷绕质量（极片对齐度、隔膜张力均匀性），先在C-3-01单机测试1周',
}
```

**补充：公用动力设备降碳方案（空压机COMP-01为例）：**
```python
{
    'strategy_type': 'equipment_maintenance',
    'title': '空压机群控与泄漏治理',
    'target_equipment': 'COMP-01 ~ COMP-03（3台空压机）',
    'actions': [
        '加装变频改造：当前工频运行，负载率波动大，变频后可节能20%-30%',
        '空压机群控：3台空压机联动，根据用气需求自动启停，避免多台同时低负载运行',
        '压缩空气泄漏治理：全厂管网泄漏率估算12%-15%，重点检测快速接头、阀门、软管',
        '调整加卸载压力：加载0.65MPa→0.60MPa，卸载0.75MPa→0.72MPa，降低压缩比',
        '余热回收：空压机油温80-90℃，可回收用于车间供暖或烘烤炉预热',
    ],
    'estimated_energy_saving': '25.8%',
    'estimated_carbon_reduction': '85.2 kgCO2/天（3台合计）',
    'estimated_cost_saving': '¥23,400/月',
    'investment': '¥45,000（变频器3台+群控系统+泄漏检测）',
    'payback_period': '1.9个月',
    'priority': 'high',
}
```

**多目标优化逻辑：**
- 目标函数：max(碳减排量) + max(成本节约) - min(投资额) - min(产量影响)
- 约束条件：产量≥计划产量、设备温度≤安全阈值、人员配置满足
- 用简单加权评分法排序（不需要复杂求解器，适合竞赛演示）

---

### 阶段4：API服务层

#### 4-1 `api_server/__init__.py`

```python
from api_server.routes import router as api_router

__all__ = ['api_router']
```

#### 4-2 `api_server/schemas.py`

用Pydantic定义所有请求/响应模型，**这是和后端对接的核心契约**：

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any

# === 通用响应 ===
class APIResponse(BaseModel):
    code: int = Field(200, description='状态码，200=成功')
    message: str = Field('success', description='消息')
    data: Optional[Any] = Field(None, description='数据')

# === 碳排查询相关 ===
class CarbonQueryRequest(BaseModel):
    level: str = Field(..., description='层级：factory/workshop/equipment/team')
    node_id: Optional[str] = Field(None, description='节点ID，不传则查全部')
    start_time: datetime
    end_time: datetime

class CarbonEmissionData(BaseModel):
    node_id: str
    node_name: str
    carbon_emission: float = Field(..., description='碳排放量(kgCO2)')
    energy_consumption: float = Field(..., description='能耗(kWh)')
    carbon_intensity: Optional[float] = Field(None, description='碳排强度')
    percentage: Optional[float] = Field(None, description='占比(%)')

# === 异常检测相关 ===
class AnomalyDetectRequest(BaseModel):
    equipment_id: str
    sequence_data: List[List[float]] = Field(..., description='60×8的时序数据矩阵')

class AnomalyDetectResponse(BaseModel):
    is_anomaly: bool
    reconstruction_error: float
    threshold: float
    severity: str = Field(..., description='high/medium/low')
    anomaly_score: float
    equipment_id: str
    timestamp: datetime

# === 溯源相关 ===
class TraceabilityRequest(BaseModel):
    equipment_id: str
    anomaly_time: datetime
    hours: int = Field(72, description='回溯小时数')

# === 降碳方案相关 ===
class StrategyRequest(BaseModel):
    equipment_id: str
    analysis_result: Optional[Dict[str, Any]] = None

class StrategyItem(BaseModel):
    strategy_type: str
    title: str
    target: str
    actions: List[str]
    estimated_energy_saving: str
    estimated_carbon_reduction: str
    estimated_cost_saving: str
    investment: str
    payback_period: str
    priority: str

# === 设备实时数据相关 ===
class EquipmentRealtimeData(BaseModel):
    equipment_id: str
    equipment_name: str
    equipment_type: str
    timestamp: datetime
    power: float
    load_rate: float
    carbon_emission: float
    temperature: float
    status: int
    is_anomaly: bool
```

#### 4-3 `api_server/services.py`

**业务逻辑层，负责调用算法模块并组装返回数据：**

| 函数 | 说明 |
|------|------|
| `get_carbon_emission_data(request: CarbonQueryRequest)` | 碳排数据查询服务 |
| `detect_anomaly(request: AnomalyDetectRequest)` | 异常检测服务 |
| `get_traceability_report(request: TraceabilityRequest)` | 溯源报告服务 |
| `generate_strategies(request: StrategyRequest)` | 降碳方案生成服务 |
| `get_equipment_realtime(equipment_id: str)` | 设备实时数据服务 |
| `get_factory_overview()` | 厂区总览数据服务 |
| `get_heatmap_data(start_time, end_time)` | 热力图数据服务 |

**关键实现要点：**
- 每个service函数只做三件事：调用算法模块 → 组装数据 → 返回
- 异常处理：try-except包裹，出错返回code=500和错误信息
- 数据缓存：高频查询接口加内存缓存（TTL=30秒），避免重复计算
- 模型加载：在模块加载时一次性加载模型，不要每次请求都加载

#### 4-4 `api_server/routes.py`

**FastAPI路由定义，所有接口端点：**

```python
from fastapi import APIRouter
from api_server.schemas import *
from api_server import services

router = APIRouter(prefix='/api/v1', tags=['算法接口'])

# === 碳排数据接口 ===
@router.post('/carbon/query', response_model=APIResponse)
async def query_carbon_emission(request: CarbonQueryRequest):
    """碳排数据查询：支持厂区/车间/设备/班组四级"""
    result = services.get_carbon_emission_data(request)
    return APIResponse(data=result)

@router.get('/carbon/overview', response_model=APIResponse)
async def get_factory_overview():
    """厂区碳排总览：总碳排、趋势、强度、排名"""
    result = services.get_factory_overview()
    return APIResponse(data=result)

@router.get('/carbon/heatmap', response_model=APIResponse)
async def get_heatmap(start_time: datetime, end_time: datetime):
    """碳排热力图数据：返回各设备碳排强度用于渲染"""
    result = services.get_heatmap_data(start_time, end_time)
    return APIResponse(data=result)

# === 异常检测接口 ===
@router.post('/anomaly/detect', response_model=APIResponse)
async def detect_anomaly(request: AnomalyDetectRequest):
    """异常检测：输入60×8时序数据，返回是否异常及严重程度"""
    result = services.detect_anomaly(request)
    return APIResponse(data=result)

@router.get('/anomaly/equipment/{equipment_id}', response_model=APIResponse)
async def get_equipment_anomaly_status(equipment_id: str):
    """获取设备当前异常状态"""
    result = services.get_equipment_anomaly_status(equipment_id)
    return APIResponse(data=result)

# === 溯源接口 ===
@router.post('/traceability/report', response_model=APIResponse)
async def get_traceability_report(request: TraceabilityRequest):
    """设备碳排溯源：近72小时历史+根因分析"""
    result = services.get_traceability_report(request)
    return APIResponse(data=result)

# === 降碳方案接口 ===
@router.post('/strategy/generate', response_model=APIResponse)
async def generate_strategies(request: StrategyRequest):
    """AI降碳方案生成：输出设备运维/生产排班/工艺优化三类方案"""
    result = services.generate_strategies(request)
    return APIResponse(data=result)

# === 设备实时数据接口 ===
@router.get('/equipment/realtime/{equipment_id}', response_model=APIResponse)
async def get_equipment_realtime(equipment_id: str):
    """设备实时数据：功率、负载率、碳排、温度、异常状态"""
    result = services.get_equipment_realtime(equipment_id)
    return APIResponse(data=result)

@router.get('/equipment/list', response_model=APIResponse)
async def list_equipment(workshop_id: str = None):
    """设备列表：可按车间筛选"""
    result = services.list_equipment(workshop_id)
    return APIResponse(data=result)
```

---

### 阶段5：入口与文档

#### 5-1 `main.py`（重写）

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api_server.routes import router as api_router
from config.settings import API_CONFIG

app = FastAPI(
    title='数字孪生锂电工厂碳排AI监测系统 - 算法服务',
    description='提供碳排核算、LSTM异常检测、溯源分析、AI降碳方案生成等算法接口',
    version='1.0.0',
)

# 跨域配置（前端对接需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # 开发阶段全开，生产环境限制前端域名
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 挂载算法路由
app.include_router(api_router)

@app.get('/')
async def root():
    return {
        'service': '碳排AI监测算法服务',
        'version': '1.0.0',
        'status': 'running',
        'docs': '/docs',
    }

@app.get('/health')
async def health_check():
    return {'status': 'healthy'}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        'main:app',
        host=API_CONFIG['host'],
        port=API_CONFIG['port'],
        reload=API_CONFIG['reload'],
    )
```

#### 5-2 `docs/algorithm_interface.md`（给后端同学的接口文档）

内容要点：
1. 服务地址：`http://<算法服务器IP>:8000`
2. API文档：`http://<IP>:8000/docs`（Swagger UI，可在线测试）
3. 所有接口列表（从routes.py复制，含请求/响应示例）
4. 数据格式约定（时间格式ISO8601、碳排单位kgCO2、功率单位kW）
5. 错误码说明：200成功、400参数错误、404资源不存在、500服务器错误
6. 调用示例（curl/Python/JavaScript）

#### 5-3 `docs/model_intro.md`

内容要点：
1. LSTM自编码器原理说明（配架构图）
2. 模型训练流程：数据采集→清洗→特征提取→序列构建→训练→评估
3. 异常检测逻辑：重建误差→自适应阈值→严重程度分级→告警冷却
4. 碳排核算方法：IPCC因子法、四级聚合逻辑
5. 降碳方案推理：三类方案生成逻辑、多目标优化
6. 模型性能指标：F1≥0.85、推理延迟<100ms、刷新延迟≤3秒

#### 5-4 模拟测试数据

创建`data/raw_data/sample_equipment_data.csv`，基于设备清单生成模拟数据。**建议优先覆盖以下高耗能/高数量设备**（每类至少选1-2台代表）：

| 优先级 | 设备类型 | 示例设备ID | 数量 | 额定功率 | 选入模拟数据理由 |
|--------|----------|------------|------|----------|-------------------|
| 🔴最高 | 电芯烘烤炉 | I-9-01 | 1 | 45kW | 单台最高耗能，温控异常最典型 |
| 🔴最高 | 空压机 | COMP-01 | 3 | 75kW | 公用动力最大耗能，能效优化空间大 |
| 🔴高 | 电芯化成柜 | D-4-01, J-10-01 | 16 | 8kW | 数量最多，充放电能效特征明显 |
| 🔴高 | 电芯卷绕机 | C-3-01, C-3-08 | 15 | 15kW | 数量多，启停冲击特征典型 |
| 🟡中 | 数控龙门铣床 | L-12-01 | 4 | 18.5kW | 切削参数与能耗关系典型 |
| 🟡中 | 冷却风机 | FAN-01 | 4 | 15kW | 风机特性方程验证 |
| 🟡中 | 冷水机组 | CHILL-01 | 2 | 55kW | COP随温度变化特征 |
| 🟢低 | 输送流水线 | H-8-01 | 1 | 5.5kW | 负载-速度二次关系 |
| 🟢低 | 外观检测机 | A-1-01 | 15 | 3kW | 低耗能，线性特征 |
| 🟢低 | AGV | K-11-01 | 2 | 1.5kW | 充电时段间歇性能耗 |

**模拟数据生成要求：**
- 时间范围：连续7天，分钟级采样（共10080条/每台设备）
- 设备数量：至少8台（覆盖高/中/低耗能各类型），总计约8万行数据
- 字段：同data_loader中定义的统一格式（15列）
- 数据规律：
  - 正常工况：功率在额定值的60%-90%波动，温度稳定，振动正常
  - 注入异常：每台设备注入2-3次异常事件（如烘烤炉超温、空压机低负载、化成柜大电流充电），异常持续30-120分钟
  - 班次规律：早班(8-16)负载高，中班(16-0)中等，夜班(0-8)低（化成柜除外，24小时运行）
  - 周末规律：周六日负载降低约30%
- 异常注入位置：随机分布在7天中，用于验证LSTM异常检测效果

**生成脚本建议：** 写一个`data/generate_sample_data.py`脚本，用numpy随机数+正弦波模拟正常波动，手动注入异常段，输出CSV。这样后续需要调整数据时可以重新生成。

---

## 四、开发顺序与时间规划

建议按以下顺序开发（每完成一个阶段就测试通过再进入下一阶段）：

```
第1天：阶段0 基础设施 + 阶段1 数据加载/清洗
       → 能跑通：加载CSV → 清洗 → 输出干净DataFrame

第2天：阶段1 特征提取 + 序列构建
       → 能跑通：DataFrame → 特征 → (60,8)序列 → 训练/测试划分

第3天：阶段2 LSTM模型定义 + 训练脚本
       → 能跑通：训练模型 → 保存权重 → 输出训练曲线

第4天：阶段2 预测 + 异常检测 + 评估
       → 能跑通：加载模型 → 推理 → 异常判定 → 评估报告

第5天：阶段3 碳排核算 + 设备机理模型
       → 能跑通：能耗数据 → 实时碳排 → 四级聚合

第6天：阶段3 溯源 + 降碳方案引擎
       → 能跑通：异常设备 → 72h溯源 → 根因 → 三类方案

第7天：阶段4 API层 + 阶段5 入口重写
       → 能跑通：启动服务 → 所有接口可通过/docs测试

第8天：文档 + 模拟数据 + 联调测试
       → 交付：接口文档、模型说明、模拟数据、全流程跑通
```

---

## 五、如何交接给后端同学

### 5.1 交接前的准备（你必须完成的）

1. **代码全部提交到Git**，确保`main`分支可运行
2. **编写`docs/algorithm_interface.md`**，包含所有接口的请求/响应示例
3. **准备模拟数据**，后端同学不需要真实数据就能联调
4. **在你的机器上启动服务**，确认`http://localhost:8000/docs`能打开且所有接口可测试
5. **写一个`README.md`**，包含：项目简介、环境搭建步骤、启动命令、目录结构说明

### 5.2 交接会议议程（建议30分钟）

| 时间 | 内容 | 负责人 |
|------|------|--------|
| 0-5min | 项目整体架构介绍：算法层做什么、后端层做什么 | 你 |
| 5-15min | 算法接口逐一讲解：每个接口的入参、出参、调用场景 | 你 |
| 15-20min | 数据格式约定：时间格式、单位、设备编码规则（详见「一点五、设备清单对照」，共78台/套设备，12类设备类型，5个车间，3个班组） | 你 |
| 20-25min | 后端同学提问、确认联调计划 | 双方 |
| 25-30min | 约定联调时间和沟通方式 | 双方 |

### 5.3 后端同学需要做的事（你要明确告诉他）

**后端负责的部分：**
1. **数据库设计与搭建**：设备表、时序数据表、告警记录表、方案表、用户表
2. **数据采集接口**：对接MES/EMS系统、传感器数据，写入数据库
3. **用户认证与权限**：登录、角色管理（管理层/运维岗/IT管理员）
4. **告警推送**：WebSocket实时推送、移动端消息推送、邮件通知
5. **报表生成**：月度碳排报告、设备溯源台账、降碳成效对比表（导出PDF/Excel）
6. **历史数据存储与查询**：3年全量归档、高效时序查询
7. **系统部署**：服务器环境配置、Nginx反向代理、Docker容器化

**后端调用算法接口的方式：**
- 算法服务独立部署在`8000`端口，后端通过HTTP调用
- 实时数据流：后端采集到数据后，调用`/api/v1/anomaly/detect`做异常检测
- 碳排数据：后端查询数据库后，可调用`/api/v1/carbon/query`做聚合计算（或后端自己算，算法层提供核算逻辑参考）
- 溯源与方案：前端点击设备时，后端调用`/api/v1/traceability/report`和`/api/v1/strategy/generate`

**联调接口优先级（按这个顺序对接）：**
1. `/api/v1/carbon/overview` — 厂区总览（首页数据）
2. `/api/v1/carbon/heatmap` — 热力图数据
3. `/api/v1/equipment/realtime/{id}` — 设备实时数据
4. `/api/v1/anomaly/detect` — 异常检测
5. `/api/v1/traceability/report` — 溯源报告
6. `/api/v1/strategy/generate` — 降碳方案

### 5.4 交接文档清单（你交付给后端的）

- [ ] `docs/algorithm_interface.md` — 算法接口文档
- [ ] `docs/model_intro.md` — 模型说明文档
- [ ] `README.md` — 项目启动说明
- [ ] `data/raw_data/sample_equipment_data.csv` — 模拟测试数据
- [ ] 可运行的算法服务（Git仓库地址）
- [ ] 你的联系方式（联调用）

---

## 六、代码规范（团队统一）

1. **格式化**：保存自动格式化，prettier，4空格缩进，单引号
2. **命名**：
   - 文件名：snake_case（如`data_loader.py`）
   - 类名：PascalCase（如`DataLoader`）
   - 函数/变量：snake_case（如`load_csv`）
   - 常量：UPPER_SNAKE_CASE（如`CARBON_FACTORS`）
3. **注释**：每个类和公共函数必须有docstring，说明功能、参数、返回值
4. **类型注解**：函数参数和返回值都加类型注解
5. **配置集中**：所有硬编码参数放`config/settings.py`，不要散落在代码里
6. **Git提交**：每次完成一个小功能就提交，commit message写清楚做了什么

---

## 七、常见问题

**Q: 没有真实设备数据怎么办？**
A: 用模拟数据。写一个脚本生成带正常规律+少量异常的分钟级数据，字段按统一格式。竞赛演示用模拟数据完全可以。

**Q: LSTM模型训练不出来/效果不好怎么办？**
A: 先用简单的统计方法（3σ原则）做异常检测兜底，LSTM作为进阶。竞赛演示重点在系统完整性，模型精度够用就行。

**Q: 降碳方案怎么生成？是真的AI推理吗？**
A: 竞赛阶段用规则引擎+模板生成即可。根据溯源结果匹配对应的方案模板，填入具体数值。不需要真的训练强化学习模型。

**Q: 后端同学说接口不够用怎么办？**
A: 先在`api_server/routes.py`里加接口，同步更新`docs/algorithm_interface.md`。算法层尽量提供原子能力，业务组合交给后端。

**Q: 模型文件太大Git提交不了怎么办？**
A: `.gitignore`里已经忽略了`output/model_weight/`，模型权重不提交到Git。交接时告诉后端同学模型文件位置，或用U盘/网盘传输。
