# 数字孪生锂电工厂碳排 AI 监测与溯源系统

> 基于 LSTM 自编码器的设备异常检测 + IPCC 因子法碳排核算 + AI 降碳方案推理，
> 配套 Web 后端（认证/采集/数据库/告警/报表/MRV）与 Vue3 前端看板，覆盖「采集 → 核算 → 检测 → 告警 → 溯源 → 策略 → 报表 → 核查」全链路；
> 并接入 DeepSeek 大模型 AI 助手与 Modbus/OPC UA/MQTT 边缘网关。
> 最后更新：2026-11-02

***

## 一、项目简介

本仓库为「数字孪生赋能锂电工厂碳排 AI 监测与溯源系统」的完整实现，由三个服务组成：

| 服务    | 端口   | 技术栈                         | 职责                                 |
| ----- | ---- | --------------------------- | ---------------------------------- |
| 算法服务  | 8000 | FastAPI + PyTorch           | 碳排核算、LSTM 异常检测、溯源分析、AI 降碳方案        |
| 后端服务  | 8001 | FastAPI + SQLAlchemy        | 认证授权、数据采集入口（MES/EMS/PLC/边缘网关）、业务组装、转发算法、DeepSeek AI 助手、MRV 台账 |
| 前端站点   | 8002 | Vue3 + Vite + Pinia + ECharts | 登录、总览、热力图、设备实时、告警中心、报表中心、用户管理    |

核心能力：

1. **碳排核算**：IPCC 因子法（GB/T 32150 兼容），支持厂区/车间/设备/班组四级聚合，覆盖电力/天然气/煤/柴油/压缩空气五类因子
2. **LSTM 异常检测**：自编码器 + 自适应阈值 + 严重程度分级 + 告警冷却 + 特征贡献可解释性；支持 accuracy/precision/recall/F1/混淆矩阵评估
3. **碳排溯源**：72h 历史回溯 + 根因分析 + 设备健康评分
4. **AI 降碳方案**：设备运维/生产排班/工艺优化三类方案模板 + 多目标加权排序 + 设备能效曲线（线性/多项式/二次）建模
5. **MRV 核查闭环**：监测-报告-核查台账，按报告期记录 Scope1/2/3 排放、数据质量评分、方法学与核查留痕（draft → self_audited → verified）
6. **DeepSeek AI 助手**：function calling 自动查询碳排总览/设备/告警/溯源/降碳方案，SSE 流式打字机输出，前端悬浮对话窗
7. **用户认证与权限**：标准 JWT（HS256）无状态认证，三级角色（管理层/运维岗/IT管理员）+ 集团-工厂-车间三级组织树与数据范围隔离（all/factory/workshop）
8. **数据采集**：MES/EMS/PLC 入站 HTTP 接口 + 边缘网关（Modbus TCP / OPC UA / MQTT 主动轮询/订阅）+ 分项计量（照明/空调/动力/产线）+ 模拟采集器
9. **告警中心**：实时异常告警（WebSocket / 邮件 / PushPlus·Server酱 多渠道）+ 告警增删改查 + 10 分钟冷却
10. **报表与归档**：月度碳排报告 / 设备溯源台账 / 降碳成效导出 PDF·Excel + 时序分层归档（分钟级留 30 天，归档桶保留 3 年）

***

## 二、系统架构

```
传感器 / PLC / MES / EMS / Modbus / OPC UA / MQTT
        │  (HTTP POST /api/ingest/*，或 EdgeGateway 主动采集归一化)
        ▼
┌─────────────────────────┐
│   后端服务 :8001        │
│  · 认证授权(JWT)        │── 数据库(SQLite，7 张表)
│  · 数据采集入站          │
│  · 业务组装/转发         │──── HTTP ────▶ 算法服务 :8000
│  · AI 助手(DeepSeek)    │     (LSTM/碳排/溯源/策略)
└───────────┬─────────────┘
            │  (REST /api/* + WebSocket /ws/alerts)
            ▼
┌─────────────────────────┐
│   前端站点 :8002         │  login / overview / heatmap / realtime / alarms / reports / users + AI 助手悬浮窗
└─────────────────────────┘
```

数据流：`传感器/PLC → (网关归一化) → 后端采集入站 → 落库并核算碳排 → 前端实时展示 → 触发异常检测 → 溯源/降碳方案 → MRV 核查归档`。

***

## 三、环境搭建

### 3.1 Python 版本

* 推荐 Python **3.13**（依赖已按 3.13 锁定，见 `requirements-*.txt`；容器镜像同为 `python:3.13-slim`）

* 密码哈希使用标准库 PBKDF2-HMAC-SHA256（不依赖 bcrypt），LSTM 训练（CPU 版 PyTorch 2.13）与碳排核算（numpy/pandas）均兼容 3.13。

### 3.2 安装步骤

```bash
# 1. 克隆代码
git clone <仓库地址>
cd carbon_factory

# 2. 创建虚拟环境
python -m venv env
env\Scripts\activate          # Windows
# source env/bin/activate     # Linux/Mac

# 3. 安装依赖（requirements.txt 为全量入口，内部按 base/algo/backend 拆分为三个文件）
pip install -r requirements.txt

# 4. 初始化数据库（建 7 张表 + 灌入 78 台设备与 3 个默认账号）
python -m database.init_db
# → 生成 database/carbon_factory.db（SQLite，可用 DATABASE_URL 切到 MySQL）
```

> 容器化部署见 3.5 节；敏感凭据（SMTP / 推送 / JWT 密钥）放入 `.env`（模板见 `.env.example`）。样本数据会在服务启动时自动刷新，无需手动生成。

### 3.3 一键启动

```bash
python main.py                 # 推荐：./env/Scripts/python.exe main.py
```

启动后同时拉起三个服务：

* 前端页面：<http://localhost:8002/>

* 后端接口：<http://localhost:8001/docs>

* 算法接口：<http://localhost:8000/docs>

### 3.4 默认账号（数据库初始化时灌入）

| 账号       | 密码            | 角色          |
| -------- | ------------- | ----------- |
| admin    | Admin\@123    | IT管理员（全部权限） |
| manager  | Manager\@123  | 管理层         |
| operator | Operator\@123 | 运维岗         |

生产环境首次登录后应及时修改密码。

### 3.5 Docker 容器化 + Nginx 反向代理

```bash
# 项目根目录执行（需先复制 .env.example 为 .env 并填入凭据）
docker compose up -d --build
```

编排见 `docker-compose.yml`，三个服务：

| 组件          | 构建来源                                    | 说明                                        |
| ----------- | --------------------------------------- | ----------------------------------------- |
| 算法服务      | deploy/Dockerfile.algo                   | Python 3.13 + CPU 版 PyTorch              |
| 后端服务      | deploy/Dockerfile.backend                | Python 3.13 + FastAPI（不装 torch，镜像更小） |
| 前端 + Nginx | deploy/Dockerfile.web + deploy/nginx.conf | 托管 web/dist + 反代 `/api` 和 `/ws`（含升级头） |

* 前端经 Nginx 同源反代 `/api` → 后端 8001、`/ws` → 后端 WebSocket，容器内无需跨域。
* 生产部署请设置 `APP_ENV=production` 并配置 `AUTH_SECRET_KEY`，否则默认密钥会被拒绝启动。

***

## 四、单独启动各服务

```bash
# 算法服务（8000）
uvicorn main:app --host 0.0.0.0 --port 8000

# 后端服务（8001）
uvicorn backend.main:app --host 0.0.0.0 --port 8001

# 前端站点（8002，Vue3 + Vite SPA）
cd web && npm install && npm run build
python -m http.server 8002 --directory web/dist
```

> 三个命令均需在**项目根目录**执行。

***

## 五、接口总览

### 5.1 算法服务（前缀 `/api/v1`）

| 方法   | 路径                         | 说明             |
| ---- | -------------------------- | -------------- |
| GET  | `/carbon/overview`         | 厂区碳排总览         |
| GET  | `/carbon/heatmap`          | 碳排热力图          |
| POST | `/carbon/query`            | 碳排数据查询（按层级/时间） |
| POST | `/anomaly/detect`          | 异常检测（传 60×8 时序数据） |
| GET  | `/anomaly/equipment/{id}`  | 设备当前异常状态       |
| GET  | `/anomaly/evaluate`        | 模型评估指标（accuracy/precision/recall/F1/混淆矩阵） |
| POST | `/traceability/report`     | 设备碳排溯源报告       |
| POST | `/strategy/generate`       | AI 降碳方案生成      |
| GET  | `/equipment/realtime/{id}` | 设备实时数据         |
| GET  | `/equipment/list`          | 设备列表（可按车间筛选）   |
| GET  | `/health`                  | 健康检查           |

### 5.2 后端服务（前缀 `/api`，转发 + 业务组装）

* 业务转发：`/carbon/overview`、`/carbon/heatmap`、`/equipment/realtime/{id}`、`/equipment/list`、`/anomaly/equipment/{id}`、`/anomaly/detect`、`/carbon/query`、`/traceability/report`、`/strategy/generate`

* 探活：`GET /api/health`（同时探测算法可达性）

* 告警管理（`/api/alarms`）：`GET/POST` 列表/手动录入、`GET/PUT/DELETE /{id}` 详情/编辑/删除、`PUT /{id}/status` 改处理状态、`DELETE` 批量删除、`POST /scan` 手动扫描

* 报表中心（`/api/report`，`format=json/excel/pdf`）：`GET /monthly` 月度碳排报告、`GET /traceability` 设备溯源台账、`GET /savings` 降碳成效对比

* 历史时序（`/api/history`）：`GET /timeseries` 单设备时序查询、`POST /archive` 手动归档

* AI 助手（`/api/agent`，DeepSeek 大模型 + function calling，需登录）：`POST /chat` 普通对话、`POST /chat/stream` SSE 流式（打字机 + 工具调用进度）

* 实时告警推送：WebSocket `/ws/alerts`

### 5.3 数据采集（前缀 `/api/ingest`）

| 方法   | 路径                   | 说明                   |
| ---- | -------------------- | -------------------- |
| POST | `/sensor`            | 单条传感器读数写入（PLC 在线推送）  |
| POST | `/batch`             | 批量读数写入（EMS/MES 定时同步） |
| POST | `/gateway`           | 边缘网关协议注入（Modbus/OPC UA/MQTT 原始帧归一化入写） |
| GET  | `/submeter/summary`  | 分项计量汇总（照明/空调/动力/产线） |
| GET  | `/submeter/resolve`  | 单台设备 → 所属分项           |
| POST | `/simulate/backfill` | 模拟：回填最近 N 天历史数据      |
| POST | `/simulate/live`     | 模拟：实时采集最近 N 分钟       |

> 说明：该组接口为「对接入口」。真实 MES/EMS 可直接 HTTP 推送；现场 PLC/传感器也可由 `collector/gateway.py` 的 `EdgeGateway` 主动轮询 Modbus 保持寄存器 / 读 OPC UA 节点 / 订阅 MQTT 主题后归一化入写（协议库 pymodbus/opcua/paho-mqtt 按需懒加载，未安装时返回 501 提示，不阻断既有 HTTP 链路）。当前数据库时序数据默认来自模拟采集器（simulator）。

### 5.4 认证与权限（前缀 `/api/auth`）

| 方法                  | 路径              | 权限    | 说明               |
| ------------------- | --------------- | ----- | ---------------- |
| POST                | `/login`        | 公开    | 登录，返回 JWT + 用户信息 |
| POST                | `/register`     | 公开    | 注册（固定为运维岗）       |
| GET                 | `/me`           | 登录    | 当前登录用户           |
| POST                | `/logout`       | 登录    | 登出               |
| GET                 | `/roles`        | 登录    | 角色定义             |
| GET/POST/PUT/DELETE | `/users[/{id}]` | IT管理员 | 用户增删改查           |

认证方式：`Authorization: Bearer <access_token>`，令牌为标准 JWT（`header.payload.signature`，HS256），默认有效期 8 小时（可用环境变量 `AUTH_TOKEN_EXPIRE` 调整）。

***

## 六、角色与权限

三种角色由 [config/settings.py](config/settings.py) 的 `ROLES` 统一定义：

| 角色    | 标识         | 默认权限                     |
| ----- | ---------- | ------------------------ |
| 管理层   | management | 查看总览/热力图/设备/告警/报告、生成降碳方案 |
| 运维岗   | operator   | 查看设备/告警、处理告警             |
| IT管理员 | it\_admin  | `*` 全部权限（含用户与角色管理）       |

***

## 七、数据库

默认使用 SQLite（`database/carbon_factory.db`），可切换 MySQL（设置环境变量 `DATABASE_URL`）：

```bash
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/carbon_factory
```

共 7 张表（定义见 [database/models.py](database/models.py)）：

| 表                     | 说明                                          |
| -------------------- | ------------------------------------------- |
| `equipment`          | 设备主数据（78 台 / 12 类，额定功率/车间/班组）               |
| `time_series_data`   | 分钟级时序数据（功率/温度/振动/负载率/碳排，近 30 天热数据）        |
| `time_series_archive`| 归档数据（小时/天统计桶，保留 3 年）                       |
| `alarm_record`       | 告警记录（严重度/根因/处理状态 + `feature_contributions` 特征贡献可解释性） |
| `strategy`           | 降碳方案（类型/节能估算/优先级）                           |
| `user`               | 用户（账号/角色/密码哈希/权限 + `scope_type`·`scope_value` 数据范围 all/factory/workshop） |
| `mrv_report`         | MRV 核查台账（报告期 Scope1/2/3 排放、数据质量评分、方法学、核查状态 draft/self_audited/verified） |

> 时序数据分层存储：分钟级原始数据保留近 30 天，过期后降采样为小时/天统计桶归档，归档保留 3 年；报表聚合走归档感知查询层，跨原始表与归档表透明读取。
> 组织级数据隔离：`config/settings.py` 的 `ORGANIZATION_TREE` 定义「锂能智造集团 → F-01 华南一厂 / F-02 华南二厂 → 5 个车间」三级树，用户按 `scope_type` 只能看授权工厂/车间的数据。

***

## 八、目录结构

```
carbon_factory/
├── main.py                    # 算法服务入口 + 一键启动全站
├── test_api.py                # 算法接口自动化验证脚本（8000 全端点）
├── test_alarm_ws.py           # 告警弹窗 WebSocket 链路测试脚本（8001 推送验证）
├── test_scaler_io.py          # scaler 保存/加载单元测试
├── config/settings.py         # 全局配置（碳排因子/超参/设备清单/角色/认证/协议网关/组织树/DeepSeek）
├── api_server/                # 算法服务 API 层（/api/v1：routes/schemas/services）
├── Lstm_model/                # LSTM 异常检测模型（model/train/predict/anomaly_detector/evaluate）
├── feature_engineer/          # 数据与特征工程（清洗/加载/特征提取/序列构建）
├── carbon_strategy/           # 碳排核算 + 溯源 + 降碳策略
│   ├── carbon_calculator.py    # IPCC 因子法核算 + 四级聚合
│   ├── equipment_models.py    # 设备能效曲线（linear/polynomial/quadratic）
│   ├── traceability.py        # 72h 根因溯源
│   └── strategy_engine.py      # 三类降碳方案生成与排序
├── collector/                 # 采集入写服务
│   ├── service.py             # 归一化读数落库 + 碳排核算
│   ├── gateway.py              # 边缘网关：Modbus/OPC UA 主动轮询、MQTT 订阅
│   ├── protocols.py            # 各协议原始帧 → 标准读数归一化
│   ├── submeter.py            # 分项计量（照明/空调/动力/产线）
│   ├── simulator.py           # 模拟采集器（历史回填/实时推送）
│   └── schemas.py             # 采集请求/响应 Pydantic 模型
├── backend/                   # 后端服务（8001）
│   ├── main.py                # 后端入口（挂载 routes/ingestion/auth/alarm/report/history/ai_agent/websocket）
│   ├── routes.py              # 业务路由（转发算法）
│   ├── auth.py / security.py  # 认证、用户管理、JWT 签发校验、权限与数据范围依赖
│   ├── ingestion.py           # 数据采集入站接口（MES/EMS/PLC/网关/分项计量）
│   ├── algorithm_client.py    # 算法服务 HTTP 客户端
│   ├── ai_agent.py            # DeepSeek function calling 工具集与 SSE 流式编排
│   ├── ai_agent_routes.py     # /api/agent/chat 与 /chat/stream
│   ├── alarm_service.py / alarm_routes.py   # 告警增删改查 + 冷却 + 多渠道编排
│   ├── report_service.py / report_export.py / report_routes.py  # 报表聚合 + Excel/PDF 导出
│   ├── archive_service.py / archive_loop.py # 时序降采样归档与后台循环
│   ├── timeseries_service.py / history_routes.py  # 分层时序/归档查询
│   ├── detection_loop.py       # 后台异常检测循环（30s 扫描代表设备）
│   ├── notifier.py / websocket.py        # 多渠道通知（WS/邮件/PushPlus·Server酱）与连接管理
│   └── test_backend.py        # 后端→算法链路验证脚本（8001 转发验收）
├── database/                  # 数据库（models/database/init_db/seed，7 张表）
├── web/                       # 前端源码（Vue3 + Vite SPA，8002 serve 构建产物 dist/）
│   ├── src/api/               # HTTP 封装与后端接口定义
│   ├── src/stores/            # Pinia（auth 登录态/角色守卫）
│   ├── src/router/            # 路由 + 登录/管理员守卫
│   ├── src/composables/       # alarmRealtime（WS 订阅）/useEcharts/toast/connection
│   ├── src/layout/            # AppLayout 侧边栏布局
│   ├── src/components/        # AiAssistant 悬浮对话窗等公共组件
│   ├── src/views/             # Login / Overview / Heatmap / Realtime / Alarms / Reports / Users
│   └── dist/                  # 生产构建产物（index.html + assets）
├── data/                      # 数据与样本生成（generate_sample_data.py + raw_data/）
├── docs/                      # 接口文档（algorithm_interface.md）/ 模型说明（model_intro.md）/ 集成清单与待办
├── deploy/                    # Docker + Nginx 部署（Dockerfile.* / nginx.conf）
├── output/                    # 模型权重 / 图表 / 日志（git 忽略）
├── vendor/                    # 本地便携依赖（uvicorn/websockets/click/h11，离线运行用）
├── docker-compose.yml         # 三服务容器编排（算法/后端/前端+Nginx）
├── .env.example               # 环境变量模板（SMTP / 推送 / JWT 密钥 / CORS 白名单）
├── .dockerignore              # Docker 构建忽略清单
├── requirements.txt           # 全量安装入口（引用下面三个拆分包）
├── requirements-base.txt      # 公共依赖（FastAPI / numpy / pandas）
├── requirements-algo.txt      # 算法依赖（torch / scikit-learn / joblib）
└── requirements-backend.txt   # 后端依赖（SQLAlchemy / pymysql / openpyxl）
```

***

## 九、测试与验证

项目提供 4 个「运行即验证」的独立测试脚本（均为 `python xxx.py` 手动运行，不进入生产链路）：

| 脚本 | 位置 | 作用 | 前置条件 |
| ---- | ---- | ---- | ---- |
| `test_api.py` | 根目录 | 算法服务(8000) 9 个端点自动化验证，核对 HTTP 状态 + 业务 code + 返回字段 | 启动算法服务 |
| `backend/test_backend.py` | backend/ | 后端(8001)→算法(8000) 整条转发链路验证，模拟前端视角打后端 | 启动算法 + 后端 |
| `test_alarm_ws.py` | 根目录 | 告警中心「实时弹窗」链路：模拟前端 WebSocket 订阅 /ws/alerts，注入异常工况触发扫描，验证实时广播告警（纯标准库手写 WS 客户端） | 启动算法 + 后端 |
| `test_scaler_io.py` | 根目录 | LSTM scaler 保存/加载最小单元测试（临时目录，不污染模型权重） | 无 |

常用命令：

```bash
python test_api.py                        # 先起算法服务 8000
python backend/test_backend.py            # 算法 8000 + 后端 8001
python test_alarm_ws.py --eq I-9-01       # 告警弹窗链路
python test_scaler_io.py                  # scaler 单元测试
```

> 告警测试提示：同设备 10 分钟冷却（`alert_cooldown_seconds=600`），连续跑需重启算法服务(8000)重置冷却，或更换 `--eq`。

***

## 十、训练 LSTM 模型（可选）

> 未训练模型时，`/anomaly/detect` 会退化为统计偏离度检测（`threshold_type="fallback"`），不影响联调。
> 当前仓库已在 `output/model_weight/` 内置三台高耗能设备的训练权重：`I-9-01`（烘烤炉）、`COMP-01`（空压机）、`C-3-01`（卷绕机），其余设备仍走 fallback。联调通过后建议为剩余高耗能设备单独训练。

```bash
python -m Lstm_model.train --equipment_id I-9-01 --epochs 30
```

训练后在 `output/model_weight/` 下生成：

* `lstm_autoencoder_I-9-01_best.pth`（模型权重）

* `scaler_I-9-01.pkl`（归一化器）

优先训练的高耗能设备：`I-9-01` 烘烤炉、`COMP-01` 空压机、`CHILL-01` 冷水机组、`L-12-01` 龙门铣床、`C-3-01` 卷绕机。

***

## 十一、关键配置

修改这些常量即可调整行为，**不需要动业务代码**（均在 [config/settings.py](config/settings.py)）：

| 配置项                                          | 默认值       | 说明                                  |
| -------------------------------------------- | --------- | ----------------------------------- |
| `CARBON_FACTORS['electricity']`              | 0.5810    | 南方电网碳排因子，地域切换改这里（另有 natural_gas/coal/diesel/compressed_air） |
| `MODEL_CONFIG['epochs']` / `device`          | 100 / cpu | 训练轮数 / 有无 GPU 改 cuda                |
| `THRESHOLD_CONFIG['method']`                 | adaptive  | 自适应/固定阈值切换；`alert_cooldown_seconds=600` 同设备告警冷却 |
| `ALERT_CONFIG['scan_equipment']`             | 8 台代表设备  | 后台 30s 循环扫描的设备清单；`ws_path=/ws/alerts` |
| `SMTP_CONFIG` / `MOBILE_PUSH_CONFIG`         | 空        | 邮件 SMTP 与 PushPlus/Server酱 移动端推送，凭据走 `.env`，未配置自动降级为日志 |
| `PROTOCOL_CONFIG`                            | 本机回环地址    | 边缘网关 Modbus(502)/OPC UA(4840)/MQTT(1883) 连接参数，真实地址走 `.env` |
| `SUBMETER_MAP`                               | chiller/cooling_fan→空调，compressor→动力 | 设备类型 → 分项计量（照明/空调/动力/产线）映射 |
| `ORGANIZATION_TREE` / `DATA_SCOPES`          | 锂能智造集团/F-01·F-02 | 集团-工厂-车间三级组织树；用户数据范围 all/factory/workshop |
| `ARCHIVE_CONFIG`                             | 原始留 30 天 / 归档留 3 年 / 每天归档一次 | 可被 `ARCHIVE_RAW_DAYS`/`ARCHIVE_YEARS`/`ARCHIVE_INTERVAL_HOURS` 覆盖 |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`        | 空 / deepseek-chat | AI 助手大模型凭据与模型，走 `.env`；`DEEPSEEK_MAX_TOOL_ROUNDS=5` 限工具轮次防死循环 |
| `AUTH_CONFIG['algorithm']`                   | HS256     | JWT 签名算法                            |
| `AUTH_CONFIG['access_token_expire_seconds']` | 28800     | 令牌有效期（8h），可用 `AUTH_TOKEN_EXPIRE` 覆盖 |
| `AUTH_CONFIG['secret_key']`                  | dev 默认值   | 生产必须用 `AUTH_SECRET_KEY` 覆盖；`APP_ENV=production` 时缺省拒绝启动 |
| `APP_ENV`                                    | 未设置      | 设为 `production` 启用生产安全护栏（校验密钥）      |
| `CORS_ORIGINS`                               | localhost:5173/8002 开发源 | 跨域白名单，逗号分隔（`.env` 可覆盖为实际前端域名） |
| `DATABASE_URL`                               | sqlite    | 环境变量，切 MySQL 用                      |

***

## 十二、代码规范

* **格式化**：保存自动格式化，4 空格缩进，单引号（团队 `.vscode/settings.json` 已统一）

* **命名**：文件 snake\_case / 类 PascalCase / 函数变量 snake\_case / 常量 UPPER\_SNAKE\_CASE

* **注释**：每个类和公共函数都有 docstring，说明功能/参数/返回值

* **类型注解**：函数参数和返回值都加类型注解

* **配置集中**：所有硬编码参数放 `config/settings.py`，不要散落在业务代码里

* **Git 提交**：每完成一个小功能就提交，commit message 写清楚做了什么

***

## 十三、联系方式

* 算法负责人：队长（算法）

* 接口文档：`docs/algorithm_interface.md`

* 模型说明：`docs/model_intro.md`

