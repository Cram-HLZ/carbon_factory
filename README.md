# 数字孪生锂电工厂碳排 AI 监测与溯源系统 · 算法服务

> 项目：基于 LSTM 自编码器的设备异常检测 + IPCC 因子法碳排核算 + AI 降碳方案推理
> 负责人：队长（算法）
> 最后更新：2026-08-22

---

## 一、项目简介

本仓库为「数字孪生赋能锂电工厂碳排 AI 监测与溯源系统」的**算法侧**，对外提供以下能力：

1. **碳排核算**：基于 IPCC 因子法（GB/T 32150 兼容），支持厂区/车间/设备/班组四级聚合
2. **LSTM 异常检测**：自编码器 + 自适应阈值 + 严重程度分级 + 告警冷却
3. **碳排溯源**：72h 历史回溯 + 7 类根因分析 + 设备健康评分
4. **AI 降碳方案**：设备运维/生产排班/工艺优化三类方案模板 + 多目标加权排序

所有能力通过 FastAPI 暴露在 8000 端口，后端通过 HTTP 调用即可。

---

## 二、环境搭建

### 2.1 Python 版本

- 推荐 Python **3.10+**
- 项目假设操作系统为 Windows / Linux 均可

### 2.2 安装步骤

```bash
# 1. 克隆代码
git clone <仓库地址>
cd carbon_factory

# 2. 创建虚拟环境
python -m venv env
env\Scripts\activate          # Windows
# source env/bin/activate     # Linux/Mac

# 3. 安装依赖
pip install -r requirements.txt

# 4. 生成模拟数据（生产环境跳过此步，后端接数据库）
python data/generate_sample_data.py
# → 输出 data/raw_data/sample_equipment_data.csv（约 9 MB，8 万行）

# 5. 启动算法服务
python main.py
# → 监听 0.0.0.0:8000，Swagger UI: http://localhost:8000/docs
```

### 2.3 可选：训练 LSTM 模型

> 没训练模型时 `/anomaly/detect` 会退化为统计偏离度检测，**不影响联调**。
> 联调通过后建议为高耗能设备单独训练：I-9-01 烘烤炉、COMP-01 空压机、CHILL-01 冷水机组、L-12-01 龙门铣床、C-3-01 卷绕机。

```bash
python -m Lstm_model.train --equipment_id I-9-01 --epochs 30
```

训练后会在 `output/model_weight/` 下生成：
- `lstm_autoencoder_I-9-01_best.pth`（模型权重）
- `scaler_I-9-01.pkl`（归一化器，**后端联调时也需要拷贝过去**）

---

## 三、目录结构

```
carbon_factory/
├── config/                    # 全局配置
│   ├── __init__.py
│   └── settings.py            # 所有硬编码参数（碳排因子/超参/设备清单/车间班组）
├── feature_engineer/          # 数据与特征工程
│   ├── __init__.py
│   ├── data_loader.py         # CSV/设备ID/时间范围/层级 查询
│   ├── data_cleaner.py        # 缺失值/异常值/时间对齐/班次标记
│   ├── feature_extractor.py   # 8维输入 + 滑窗统计 + 碳排
│   └── sequence_builder.py    # 切成 (N,60,8) + MinMax 归一化 + scaler 持久化
├── Lstm_model/                # LSTM 异常检测模型
│   ├── __init__.py
│   ├── model.py               # PyTorch 自编码器定义
│   ├── train.py               # 训练脚本（命令行入口）
│   ├── predict.py             # 推理器（加载 .pth + scaler）
│   ├── anomaly_detector.py    # 自适应阈值 + 严重程度 + 告警冷却
│   └── evaluate.py            # 评估工具（F1/混淆矩阵/误差分布图）
├── carbon_strategy/           # 碳排核算与降碳策略
│   ├── __init__.py
│   ├── carbon_calculator.py   # IPCC 因子法 + 四级聚合
│   ├── equipment_models.py    # 12 类设备机理模型
│   ├── traceability.py        # 72h 溯源 + 7 类根因
│   └── strategy_engine.py     # 降碳方案模板 + 加权排序
├── api_server/                # API 服务层（对接后端）
│   ├── __init__.py
│   ├── schemas.py             # Pydantic 请求/响应模型（核心契约）
│   ├── services.py            # 业务逻辑层 + 内存缓存
│   └── routes.py              # FastAPI 路由（前缀 /api/v1）
├── data/
│   ├── generate_sample_data.py # 模拟数据生成脚本
│   └── raw_data/
│       └── sample_equipment_data.csv  # 模拟测试数据（约 9 MB）
├── docs/
│   ├── ALGORITHM_TODO.md       # 算法侧任务清单（开发依据）
│   ├── algorithm_interface.md  # 算法接口文档（给后端同学）
│   └── model_intro.md          # 模型原理与使用说明
├── output/                    # 输出目录（git 忽略）
│   ├── model_weight/           # LSTM 权重 + scaler
│   ├── chart/                  # 训练曲线/误差分布图
│   └── log/                    # 评估报告
├── main.py                    # FastAPI 应用入口
├── requirements.txt           # Python 依赖清单
└── .gitignore
```

---

## 四、启动与测试

### 4.1 启动算法服务

```bash
python main.py
```

启动成功后访问：
- 服务根信息：http://localhost:8000/
- Swagger UI（在线测试）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 4.2 验证接口可用

打开 Swagger UI 后，依次测试：

1. `GET /api/v1/carbon/overview` — 应返回厂区碳排总览数据
2. `GET /api/v1/equipment/list?workshop_id=WS-01` — 应返回 WS-01 的 17 台设备
3. `POST /api/v1/traceability/report` — 传 `{equipment_id: "I-9-01", anomaly_time: "2026-08-21T14:30:00"}` 应返回溯源报告
4. `POST /api/v1/strategy/generate` — 传 `{equipment_id: "I-9-01"}` 应返回三类降碳方案

### 4.3 训练模型（可选）

```bash
# 高耗能设备优先（用模拟数据训练，约 5 分钟/设备在 CPU 上）
python -m Lstm_model.train --equipment_id I-9-01 --epochs 30
python -m Lstm_model.train --equipment_id COMP-01 --epochs 30
python -m Lstm_model.train --equipment_id C-3-01 --epochs 30
```

---

## 五、与后端联调

### 5.1 算法侧交付内容

- [x] 可运行的算法服务（本仓库）
- [x] `docs/algorithm_interface.md` 算法接口文档
- [x] `docs/model_intro.md` 模型说明文档
- [x] `data/raw_data/sample_equipment_data.csv` 模拟测试数据
- [x] 本 README

### 5.2 后端负责的部分

1. 数据库设计与搭建（设备表/时序数据表/告警记录/方案表/用户表）
2. 数据采集接口（对接 MES/EMS/PLC/传感器）
3. 用户认证与权限（管理层/运维岗/IT管理员）
4. 告警推送（WebSocket/移动端/邮件）
5. 报表生成（月度碳排报告/溯源台账/降碳成效对比，导出 PDF/Excel）
6. 历史数据存储与查询（3年归档）
7. 部署：Nginx 反向代理 + Docker 容器化

### 5.3 实时数据流

```
传感器/PLC → 后端采集 → 数据库 → 后端调 /anomaly/detect
   → 算法返回异常 → 后端推 WebSocket → 前端弹窗
```

### 5.4 联调优先级

1. `GET /api/v1/carbon/overview` — 厂区总览
2. `GET /api/v1/carbon/heatmap` — 热力图
3. `GET /api/v1/equipment/realtime/{id}` — 设备实时数据
4. `POST /api/v1/anomaly/detect` — 异常检测
5. `POST /api/v1/traceability/report` — 溯源报告
6. `POST /api/v1/strategy/generate` — 降碳方案

---

## 六、代码规范

- **格式化**：保存自动格式化，Prettier，4 空格缩进，单引号（团队 `.vscode/settings.json` 已统一）
- **命名**：文件 snake_case / 类 PascalCase / 函数变量 snake_case / 常量 UPPER_SNAKE_CASE
- **注释**：每个类和公共函数都有 docstring，说明功能/参数/返回值
- **类型注解**：函数参数和返回值都加类型注解
- **配置集中**：所有硬编码参数放 `config/settings.py`，不要散落在业务代码里
- **Git 提交**：每完成一个小功能就提交，commit message 写清楚做了什么

---

## 七、关键配置

修改这些常量即可调整系统行为，**不需要动业务代码**：

| 配置项 | 文件 | 默认值 | 说明 |
|--------|------|--------|------|
| `CARBON_FACTORS['electricity']` | `config/settings.py` | 0.5810 | 南方电网碳排因子，地域切换改这里 |
| `MODEL_CONFIG['epochs']` | `config/settings.py` | 100 | 训练轮数，开发期可改 30 |
| `MODEL_CONFIG['device']` | `config/settings.py` | 'cpu' | 部署有 GPU 改 'cuda' |
| `THRESHOLD_CONFIG['method']` | `config/settings.py` | 'adaptive' | 自适应/固定阈值切换 |
| `THRESHOLD_CONFIG['alert_cooldown_seconds']` | `config/settings.py` | 600 | 同设备告警冷却时间 |
| `API_CONFIG['reload']` | `config/settings.py` | True | 开发热重载，生产建议关闭 |
| `services._CACHE_TTL` | `api_server/services.py` | 30.0 | 高频接口缓存 TTL（秒） |

---

## 八、联系方式

- 算法负责人：队长（算法）
- 联调问题随时找我（微信/钉钉/当面）
- 接口文档：`docs/algorithm_interface.md`
- 模型说明：`docs/model_intro.md`
