# 模型原理与使用说明

> **文档定位**：算法侧模型/方案的原理介绍，给后端同学与答辩评委看
> **最后更新**：2026-08-22

---

## 一、整体架构

```
原始时序数据 → 数据清洗 → 特征提取 → LSTM 自编码器重建
                                              ↓
                                         重建误差
                                              ↓
                          自适应阈值判定 → 异常告警 → 溯源 → 降碳方案
                                              ↓
                                       IPCC 因子核算四级聚合
```

**核心模块**：

| 模块 | 文件 | 作用 |
|------|------|------|
| 数据加载 | `feature_engineer/data_loader.py` | CSV / 设备ID / 时间范围 / 层级查询 |
| 数据清洗 | `feature_engineer/data_cleaner.py` | 缺失值/异常值/时间对齐/班次标记 |
| 特征提取 | `feature_engineer/feature_extractor.py` | 8 维输入 + 滑窗统计 + 碳排 |
| 序列构建 | `feature_engineer/sequence_builder.py` | 切成 (N, 60, 8) + 归一化 + scaler 持久化 |
| LSTM 模型 | `Lstm_model/model.py` | PyTorch 自编码器 |
| 训练脚本 | `Lstm_model/train.py` | 早停 + lr 调度 + checkpoint |
| 推理器 | `Lstm_model/predict.py` | 加载 .pth + scaler，单条延迟 <100ms |
| 异常检测 | `Lstm_model/anomaly_detector.py` | 自适应阈值 + 严重程度 + 告警冷却 |
| 碳排核算 | `carbon_strategy/carbon_calculator.py` | IPCC 因子法 + 四级聚合 |
| 设备机理 | `carbon_strategy/equipment_models.py` | 12 类设备的能耗/能效模型 |
| 溯源分析 | `carbon_strategy/traceability.py` | 72h 历史 + 7 类根因 |
| 降碳方案 | `carbon_strategy/strategy_engine.py` | 三类方案模板 + 加权排序 |
| API 服务 | `api_server/` | FastAPI 路由 + service 层 |

---

## 二、LSTM 自编码器原理

### 2.1 为什么选自编码器

- **无监督**：不需要标注异常数据，正常数据训练即可（实际产线异常样本稀缺）
- **适合时序**：LSTM 能学到负载/温度的动态规律
- **可解释**：重建误差大的样本视为异常，符合"偏离正常模式即异常"的直觉

### 2.2 网络结构

```
输入序列 (batch, 60, 8)
        ↓ Encoder LSTM (2层, hidden=128)
        ↓ 取最后时刻隐向量 (batch, 128)
        ↓ RepeatVector(60)
        ↓ Decoder LSTM (2层, hidden=128)
        ↓ Linear(128 → 8)
        ↓ 输出序列 (batch, 60, 8)  ← 与输入同形，学习重建
```

### 2.3 训练流程

1. **数据准备**：CSV → 清洗（缺失插值 + 3σ 异常替换 + 1分钟对齐 + 班次标记）
2. **特征提取**：8维特征 = 负载率/功率/能耗增量/温度/振动/碳排/功率变化率/运行时长
3. **序列构建**：滑窗切片，shape = (N, 60, 8)，训练:测试 = 8:2 按时间顺序分
4. **归一化**：MinMaxScaler 拟合到 [0,1]，scaler 保存到 `output/model_weight/scaler_{eq_id}.pkl`
5. **训练**：Adam(lr=0.001) + MSELoss + ReduceLROnPlateau + 早停(patience=10)
6. **保存**：最佳权重存到 `output/model_weight/lstm_autoencoder_{eq_id}_best.pth`

**命令行入口**：

```bash
# 训练指定设备（建议优先训练高耗能设备）
python -m Lstm_model.train --equipment_id I-9-01
python -m Lstm_model.train --equipment_id COMP-01
python -m Lstm_model.train --equipment_id C-3-01
```

### 2.4 推理与异常判定

**重建误差** = mean((输入 - 重建输出)²)（MSE）

**阈值策略**：

| 策略 | 公式 | 说明 |
|------|------|------|
| adaptive（默认） | threshold = mean(过去24h误差) + 3 × std | 自适应波动，避免误报 |
| fixed | threshold = 0.5 | 固定阈值，调试用 |

**严重程度**：

```
score = 重建误差 / 阈值
score > 2.0  → high（红色告警）
score > 1.5  → medium（橙色告警）
score > 1.0  → low（黄色提示）
score ≤ 1.0  → normal
```

**告警冷却**：同一设备 600 秒内只告警一次（`alert_cooldown_seconds=600`）

### 2.5 性能指标

| 指标 | 目标 | 实测 |
|------|------|------|
| 异常检测 F1 | ≥ 0.85 | 取决于训练数据 |
| 单条推理延迟 | < 100ms | CPU 上 < 20ms（`predict.benchmark_latency` 验证） |
| 数据刷新延迟 | ≤ 3 秒 | API 服务内存缓存 TTL=30s |
| AI 方案生成准确率 | ≥ 85% | 异常检测 F1 满足即满足 |

---

## 三、碳排核算方法

### 3.1 IPCC 因子法（基于 GB/T 32150）

| 能源类型 | 因子 | 单位 |
|----------|------|------|
| 电力（南方电网） | 0.5810 | kgCO2/kWh |
| 天然气 | 2.1622 | kgCO2/m³ |
| 煤 | 2.6600 | kgCO2/kg |
| 柴油 | 3.0959 | kgCO2/L |
| 压缩空气 | 0.12 | kgCO2/m³ |

后端做地域切换时，只改 `config.CARBON_FACTORS['electricity']`。

### 3.2 四级聚合逻辑

```
设备级（每分钟） = power(kW) × (1/60 h) × 0.5810(kgCO2/kWh)
     ↓ groupby(workshop_id)
车间级 = sum(设备碳排)，含设备数、平均负载、碳排强度
     ↓ groupby(team_id)
班组级 = sum(车间内该班组设备碳排)，含对比
     ↓ sum(全部)
厂区级 = 总碳排、Top10 设备、按小时趋势
```

### 3.3 碳排强度

`碳排强度 = 总碳排(kgCO2) / 同期产量(件)`

由后端调用 `CarbonCalculator.calculate_carbon_intensity(df, production_output)` 计算。

---

## 四、降碳方案推理

### 4.1 三类方案

| 方案类型 | 适用场景 | 关键字段 |
|---------|---------|----------|
| equipment_maintenance | 设备运维：烘烤炉温控/化成柜充电/空压机群控/风机变频 | `actions`, `investment`, `payback_period` |
| production_scheduling | 生产排班：峰谷错峰、夜班高耗能工序 | `recommended_schedule`, `constraints` |
| process_optimization | 工艺优化：卷绕机启停时序/风机变频参数 | `actions`, `priority` |

### 4.2 多目标优化

目标函数：

```
max(碳减排量) + max(成本节约) - min(投资额) - min(产量影响)
```

实现：**简单加权评分法**（竞赛演示够用，不需要复杂求解器）

排序优先级：
1. 与根因匹配的方案类型优先
2. priority 字段（high > medium > low）
3. 投资回收期短的优先

### 4.3 模板库

`carbon_strategy/strategy_engine.py` 内置 12 类设备 × 2 种方案（运维 + 工艺）的模板，按 `equipment_type` 路由。每个模板含具体的 actions、节能量估算、投资额、回收期。

实际部署时建议根据真实节能量数据修正模板中的系数（用 `estimate_energy_savings` 函数辅助估算）。

---

## 五、设备机理模型

12 类设备的能耗/能效模型（覆盖清单中所有设备类型）：

| 设备类型 | 模型 | 关键参数 |
|---------|------|----------|
| baking_oven | 升温/保温/降温三阶段 | 设定温度、环境温度、阶段时长 |
| formation_cabinet | C-rate + SOC 能效曲线 | 充电倍率、SOC |
| winding_machine | 张力+速度线性 | 张力、速度 |
| cnc_milling_machine | 空载+主轴+切削 | 主轴转速、进给率、切削深度 |
| conveyor_line | 负载+速度二次 | 负载重量、速度 |
| appearance/dimension_inspector | 检测速率线性 | 检测速率 |
| sorting_machine | 分选速度线性 | 分选速度 |
| agv | SOC 充电模型 | 电池 SOC |
| compressor | 三次多项式比功率 | 负载率 |
| cooling_fan | 相似定律（功率∝风量³） | 风量、静压 |
| chiller | COP 温度模型 | 出水温度、环境温度 |

**入口函数**：`estimate_energy_savings(equipment_id, current_state, target_state)` 按 `equipment_type` 路由到对应模型。

---

## 六、模型训练与评估

### 6.1 训练命令

```bash
# 高耗能设备优先
python -m Lstm_model.train --equipment_id I-9-01
python -m Lstm_model.train --equipment_id COMP-01
python -m Lstm_model.train --equipment_id CHILL-01
python -m Lstm_model.train --equipment_id L-12-01
python -m Lstm_model.train --equipment_id C-3-01

# 覆盖 epochs（开发期缩短训练时间）
python -m Lstm_model.train --equipment_id I-9-01 --epochs 30
```

### 6.2 输出文件

| 文件 | 路径 | 用途 |
|------|------|------|
| 模型权重 | `output/model_weight/lstm_autoencoder_{eq_id}_best.pth` | 推理加载 |
| Scaler | `output/model_weight/scaler_{eq_id}.pkl` | 推理时归一化 |
| 训练曲线 | `output/chart/training_curve_{eq_id}.png` | 可视化训练过程 |
| 评估报告 | `output/log/evaluation_report_{eq_id}.json` | F1/混淆矩阵 |

### 6.3 评估工具

```python
from Lstm_model.evaluate import (
    evaluate_model, classification_report,
    plot_error_distribution, save_evaluation_report
)
```

---

## 七、部署建议

### 7.1 算法服务部署

```bash
# 1. 创建虚拟环境
python -m venv env
env\Scripts\activate  # Windows
# source env/bin/activate  # Linux

# 2. 安装依赖
pip install -r requirements.txt

# 3. 生成模拟数据（生产环境跳过，后端直接接数据库）
python data/generate_sample_data.py

# 4. 训练模型（可选，生产环境由后端从数据库取真实数据训练）
python -m Lstm_model.train --equipment_id I-9-01 --epochs 30

# 5. 启动 API 服务
python main.py  # 或 uvicorn main:app --reload --port 8000
```

### 7.2 生产环境配置

- 修改 `config.settings.API_CONFIG['reload']=False`
- 修改 `config.settings.MODEL_CONFIG['device']='cuda'`（有 GPU 时）
- 调小 `api_server/services._CACHE_TTL` 至 5s（更实时）
- 把告警冷却的基线数据从内存 dict 改为 Redis（`AnomalyDetector._baselines`）

---

## 八、常见问题

**Q: 没有真实设备数据怎么办？**
A: 用 `data/generate_sample_data.py` 生成 7 天 × 8 台的模拟数据（已包含异常注入）。竞赛演示完全够用。

**Q: LSTM 模型训练不出来/效果不好怎么办？**
A: `/anomaly/detect` 会自动退化为 `fallback` 统计偏离度检测，不影响联调。模型精度够用就行，竞赛演示重点在系统完整性。

**Q: 降碳方案怎么生成？是真的 AI 推理吗？**
A: 竞赛阶段用规则引擎 + 方案模板（根据 `equipment_type` 路由）。模板中填入溯源结果的具体数值。不需要训练强化学习模型。

**Q: 后端同学说接口不够用怎么办？**
A: 在 `api_server/routes.py` 加端点，同步更新 `docs/algorithm_interface.md`。算法层尽量提供原子能力，业务组合交给后端。

**Q: 模型文件太大 Git 提交不了怎么办？**
A: `.gitignore` 已忽略 `output/model_weight/`，权重不提交。交接时通过 U盘/网盘传输，或重新训练（约 30 分钟/设备）。
