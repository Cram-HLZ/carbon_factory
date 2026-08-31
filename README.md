# 数字孪生锂电工厂碳排 AI 监测与溯源系统

> 基于 LSTM 自编码器的设备异常检测 + IPCC 因子法碳排核算 + AI 降碳方案推理，
> 配套 Web 后端（认证/采集/数据库）与前端看板，覆盖「采集 → 核算 → 检测 → 溯源 → 策略」全链路。
> 最后更新：2026-08-31

***

## 一、项目简介

本仓库为「数字孪生赋能锂电工厂碳排 AI 监测与溯源系统」的完整实现，由三个服务组成：

| 服务    | 端口   | 技术栈                         | 职责                                 |
| ----- | ---- | --------------------------- | ---------------------------------- |
| 算法服务  | 8000 | FastAPI + PyTorch           | 碳排核算、LSTM 异常检测、溯源分析、AI 降碳方案        |
| 后端服务  | 8001 | FastAPI + SQLAlchemy        | 认证授权、数据采集入口（MES/EMS/PLC）、业务组装、转发算法 |
| 前端静态站 | 8003 | HTML + Bootstrap5 + ECharts | 登录、总览、热力图、设备实时、用户管理                |

核心能力：

1. **碳排核算**：IPCC 因子法（GB/T 32150 兼容），支持厂区/车间/设备/班组四级聚合
2. **LSTM 异常检测**：自编码器 + 自适应阈值 + 严重程度分级 + 告警冷却
3. **碳排溯源**：72h 历史回溯 + 7 类根因分析 + 设备健康评分
4. **AI 降碳方案**：设备运维/生产排班/工艺优化三类方案模板 + 多目标加权排序
5. **用户认证与权限**：标准 JWT（HS256）无状态认证，三级角色（管理层/运维岗/IT管理员）
6. **数据采集**：MES/EMS/PLC 入站 HTTP 接口 + 模拟采集器

***

## 二、系统架构

```
传感器 / PLC / MES / EMS
        │  (HTTP POST /api/ingest/*)
        ▼
┌─────────────────────────┐
│   后端服务 :8001        │
│  · 认证授权(JWT)        │── 数据库(SQLite，5张表)
│  · 数据采集入站          │
│  · 业务组装/转发         │──── HTTP ────▶ 算法服务 :8000
└───────────┬─────────────┘                 (LSTM/碳排/溯源/策略)
            │  (REST /api/*)
            ▼
┌─────────────────────────┐
│   前端静态站 :8003       │  login / overview / heatmap / realtime / users
└─────────────────────────┘
```

数据流：`传感器/PLC → 后端采集入站 → 落库并核算碳排 → 前端实时展示 → 触发异常检测 → 溯源/降碳方案`。

***

## 三、环境搭建

### 3.1 Python 版本

* 推荐 Python **3.10 \~ 3.12**

* ⚠️ 兼容性提示：`torch==2.4.0`、`numpy==1.26.4` 等固定版本与 Python 3.13 存在兼容问题。密码哈希已改用标准库 PBKDF2-HMAC-SHA256（不依赖 bcrypt），可直接跑在 3.13 上，但训练 LSTM 仍建议用 3.10\~3.12。

### 3.2 安装步骤

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

# 4. 初始化数据库（建 5 张表 + 灌入 78 台设备与 3 个默认账号）
python -m database.init_db
# → 生成 database/carbon_factory.db（SQLite，可用 DATABASE_URL 切到 MySQL）
```

### 3.3 一键启动

```bash
python main.py                 # 推荐：./env/Scripts/python.exe main.py
```

启动后同时拉起三个服务：

* 前端页面：<http://localhost:8003/login.html>

* 后端接口：<http://localhost:8001/docs>

* 算法接口：<http://localhost:8000/docs>

### 3.4 默认账号（数据库初始化时灌入）

| 账号       | 密码            | 角色          |
| -------- | ------------- | ----------- |
| admin    | Admin\@123    | IT管理员（全部权限） |
| manager  | Manager\@123  | 管理层         |
| operator | Operator\@123 | 运维岗         |

生产环境首次登录后应及时修改密码。

***

## 四、单独启动各服务

```bash
# 算法服务（8000）
uvicorn main:app --host 0.0.0.0 --port 8000

# 后端服务（8001）
uvicorn backend.main:app --host 0.0.0.0 --port 8001

# 前端静态站（8003）
python -m http.server 8003 --directory frontend
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
| POST | `/anomaly/detect`          | 异常检测（传时序数据）    |
| GET  | `/anomaly/equipment/{id}`  | 设备当前异常状态       |
| POST | `/traceability/report`     | 设备碳排溯源报告       |
| POST | `/strategy/generate`       | AI 降碳方案生成      |
| GET  | `/equipment/realtime/{id}` | 设备实时数据         |
| GET  | `/equipment/list`          | 设备列表           |
| GET  | `/health`                  | 健康检查           |

### 5.2 后端服务（前缀 `/api`，转发 + 业务组装）

* 业务转发：`/carbon/overview`、`/carbon/heatmap`、`/equipment/realtime/{id}`、`/equipment/list`、`/anomaly/equipment/{id}`、`/anomaly/detect`、`/carbon/query`、`/traceability/report`、`/strategy/generate`

* 探活：`GET /api/health`（同时探测算法可达性）

### 5.3 数据采集（前缀 `/api/ingest`）

| 方法   | 路径                   | 说明                   |
| ---- | -------------------- | -------------------- |
| POST | `/sensor`            | 单条传感器读数写入（PLC 在线推送）  |
| POST | `/batch`             | 批量读数写入（EMS/MES 定时同步） |
| POST | `/simulate/backfill` | 模拟：回填最近 N 天历史数据      |
| POST | `/simulate/live`     | 模拟：实时采集最近 N 分钟       |

> 说明：该组接口为「对接入口」，真实 MES/EMS/PLC 需由网关/中间件调用推送数据。当前数据库时序数据来自模拟采集器（simulator）。

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

共 5 张表（定义见 [database/models.py](database/models.py)）：

| 表                  | 说明                                 |
| ------------------ | ---------------------------------- |
| `equipment`        | 设备主数据（78 台 / 12 类）                 |
| `time_series_data` | 时序数据（功率/温度/振动/负载率/碳排，按 (设备,时间) 唯一） |
| `alarm_record`     | 告警记录                               |
| `strategy`         | 降碳方案                               |
| `user`             | 用户（账号/角色/密码哈希/权限）                  |

***

## 八、目录结构

```
carbon_factory/
├── main.py                    # 算法服务入口 + 一键启动全站
├── config/settings.py         # 全局配置（碳排因子/超参/设备清单/角色/认证）
├── api_server/                # 算法服务 API 层（/api/v1）
├── Lstm_model/                # LSTM 异常检测模型（训练/推理/阈值/评估）
├── feature_engineer/          # 数据与特征工程
├── carbon_strategy/           # 碳排核算 + 溯源 + 降碳策略
├── backend/                   # 后端服务（8001）
│   ├── main.py                # 后端入口（挂载 routes/ingestion/auth）
│   ├── routes.py              # 业务路由（转发算法）
│   ├── auth.py                # 认证与用户管理
│   ├── security.py            # JWT 签发/校验 + 密码哈希 + 权限依赖
│   ├── ingestion.py           # 数据采集入站接口（MES/EMS/PLC）
│   └── algorithm_client.py    # 算法服务 HTTP 客户端
├── collector/                 # 采集入写服务（落库 + 碳排核算 + 模拟器）
├── database/                  # 数据库（模型/连接/建表/种子）
├── frontend/                  # 前端静态站（8003）
│   ├── app.js                 # 全局脚本（Token 注入/401 拦截/常量）
│   ├── login.html             # 登录 + 注册
│   ├── overview.html          # 碳排总览
│   ├── heatmap.html           # 碳排热力图
│   ├── realtime.html          # 设备实时
│   └── users.html             # 用户与角色管理
├── data/                      # 数据与样本生成
├── docs/                      # 接口文档 / 模型说明
├── output/                    # 模型权重 / 图表 / 日志（git 忽略）
└── requirements.txt
```

***

## 九、训练 LSTM 模型（可选）

> 未训练模型时，`/anomaly/detect` 会退化为统计偏离度检测（`threshold_type="fallback"`），不影响联调。联调通过后建议为高耗能设备单独训练。

```bash
python -m Lstm_model.train --equipment_id I-9-01 --epochs 30
```

训练后在 `output/model_weight/` 下生成：

* `lstm_autoencoder_I-9-01_best.pth`（模型权重）

* `scaler_I-9-01.pkl`（归一化器）

优先训练的高耗能设备：`I-9-01` 烘烤炉、`COMP-01` 空压机、`CHILL-01` 冷水机组、`L-12-01` 龙门铣床、`C-3-01` 卷绕机。

***

## 十、关键配置

修改这些常量即可调整行为，**不需要动业务代码**（均在 [config/settings.py](config/settings.py)）：

| 配置项                                          | 默认值       | 说明                                  |
| -------------------------------------------- | --------- | ----------------------------------- |
| `CARBON_FACTORS['electricity']`              | 0.5810    | 南方电网碳排因子，地域切换改这里                    |
| `MODEL_CONFIG['epochs']` / `device`          | 100 / cpu | 训练轮数 / 有无 GPU 改 cuda                |
| `THRESHOLD_CONFIG['method']`                 | adaptive  | 自适应/固定阈值切换                          |
| `THRESHOLD_CONFIG['alert_cooldown_seconds']` | 600       | 同设备告警冷却时间                           |
| `AUTH_CONFIG['algorithm']`                   | HS256     | JWT 签名算法                            |
| `AUTH_CONFIG['access_token_expire_seconds']` | 28800     | 令牌有效期（8h），可用 `AUTH_TOKEN_EXPIRE` 覆盖 |
| `AUTH_CONFIG['secret_key']`                  | dev 默认值   | 生产必须用环境变量 `AUTH_SECRET_KEY` 覆盖      |
| `DATABASE_URL`                               | sqlite    | 环境变量，切 MySQL 用                      |

***

## 十一、当前进度与待办

### 已完成

* [x] 算法服务（碳排核算 / LSTM 异常检测 / 溯源 / 降碳方案）

* [x] 后端服务（业务转发 + 数据采集入口 + 认证授权）

* [x] 前端（登录 + 总览 + 热力图 + 设备实时 + 用户管理）

* [x] 数据库（SQLite 5 张表 + 设备/用户种子数据）

* [x] 用户认证与角色权限（标准 JWT + 三级角色 + 用户增删改查）

* [x] 一键启动（`python main.py` 同时拉起三服务）

### 待办

* [ ] 真实 MES/EMS/PLC 对接（当前为 HTTP 入站接口 + 模拟数据）

* [ ] LSTM 模型训练（当前异常检测退化为统计偏离度 fallback）

* [ ] 告警推送（WebSocket / 邮件 / 移动端）

* [ ] 报表导出（PDF / Excel）

* [ ] Docker 容器化 + Nginx 反向代理部署

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

