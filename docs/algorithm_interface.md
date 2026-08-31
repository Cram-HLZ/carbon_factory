# 算法服务接口文档（联调版）

> **对接对象**：负责后端联调的同学
> **算法负责人**：队长（算法）
> **最后更新**：2026-08-22

---

## 一、服务信息

| 项目       | 值                                         |
| ---------- | ------------------------------------------ |
| 服务名称   | 数字孪生锂电工厂碳排AI监测算法服务         |
| 版本       | 1.0.0                                      |
| 服务地址   | `http://<算法服务器IP>:8000`               |
| Swagger UI | `http://<IP>:8000/docs` （可在线测试）     |
| 健康检查   | `GET http://<IP>:8000/health`              |
| API 前缀   | `/api/v1`                                  |
| 跨域策略   | 开发期 `*`，生产部署建议改为前端域名白名单 |

---

## 二、数据格式约定

| 项目     | 格式 / 单位                        |
| -------- | ---------------------------------- |
| 时间格式 | ISO 8601，如 `2026-08-21T14:30:00` |
| 碳排单位 | kgCO2（千克二氧化碳）              |
| 功率单位 | kW（千瓦）                         |
| 能耗单位 | kWh（千瓦时）                      |
| 温度单位 | ℃（摄氏度）                        |
| 振动单位 | mm/s                               |
| 负载率   | 0-1 小数                           |
| 设备ID   | 见下方设备编码规则                 |

### 设备编码规则

- **生产设备**：`{清单编号}-{两位序号}`，如 `C-3-01`、`I-9-01`
- **公用设备**：`{类型缩写}-{两位序号}`，如 `COMP-01`、`FAN-01`
- 共 78 台/套设备，12 类设备类型，5 个车间，3 个班组（详见 `config/settings.py` 中 `EQUIPMENT_LIST` / `EQUIPMENT_TYPES` / `WORKSHOPS` / `TEAMS`）

---

## 三、接口列表

### 3.1 碳排查询

#### `POST /api/v1/carbon/query` 碳排数据查询（四级聚合）

按厂区/车间/设备/班组聚合查询碳排。

**请求体**

```json
{
    "level": "workshop",
    "node_id": "WS-01",
    "start_time": "2026-08-15T00:00:00",
    "end_time": "2026-08-22T00:00:00"
}
```

| 字段       | 类型     | 必填 | 说明                                                    |
| ---------- | -------- | ---- | ------------------------------------------------------- |
| level      | string   | 是   | 聚合层级：`factory` / `workshop` / `equipment` / `team` |
| node_id    | string   | 否   | 节点ID；`level=factory` 时忽略                          |
| start_time | datetime | 是   | 起始时间（ISO 8601）                                    |
| end_time   | datetime | 是   | 结束时间（ISO 8601）                                    |

**响应体**

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "level": "workshop",
        "node_id": "WS-01",
        "records": [
            {
                "workshop_id": "WS-01",
                "carbon_emission": 1234.56,
                "energy_consumption": 2125.83,
                "equipment_count": 17,
                "workshop_name": "电芯制备车间"
            }
        ],
        "total_emission": 1234.56
    }
}
```

---

#### `GET /api/v1/carbon/overview` 厂区碳排总览（首页数据）

无入参。返回厂区总碳排、车间/班组排名、设备 Top10、按小时趋势。

**响应体**

```json
{
    "code": 200,
    "data": {
        "total_emission": 12345.67,
        "total_energy": 21267.34,
        "by_workshop": [
            { "workshop_id": "WS-01", "carbon_emission": 1234.56, "...": "..." }
        ],
        "by_team": [
            { "team_id": "TEAM-A", "carbon_emission": 8000.0, "...": "..." }
        ],
        "by_equipment_top": [
            {
                "equipment_id": "I-9-01",
                "carbon_emission": 2000.0,
                "...": "..."
            }
        ],
        "hourly_trend": [
            {
                "timestamp": "2026-08-15T00:00:00",
                "carbon_emission": 12.5,
                "energy_consumption": 21.5
            }
        ]
    }
}
```

---

#### `GET /api/v1/carbon/heatmap` 碳排热力图数据

**Query 参数**

| 字段       | 类型     | 说明     |
| ---------- | -------- | -------- |
| start_time | datetime | 起始时间 |
| end_time   | datetime | 结束时间 |

**响应体**

```json
{
    "code": 200,
    "data": {
        "records": [
            {
                "equipment_id": "I-9-01",
                "equipment_name": "电芯烘烤炉",
                "workshop_id": "WS-01",
                "carbon_emission": 2345.67,
                "power_mean": 42.3,
                "runtime": 10080,
                "equipment_type": "baking_oven"
            }
        ],
        "count": 78
    }
}
```

---

### 3.2 异常检测

#### `POST /api/v1/anomaly/detect` 异常检测

输入 60×8 时序数据矩阵，返回是否异常及严重程度。

**请求体**

```json
{
    "equipment_id": "I-9-01",
    "sequence_data": [
        [0.78, 35.4, 0.59, 122.5, 0.45, 0.34, 0.02, 6800.5],
        [0.8, 36.1, 0.6, 123.0, 0.46, 0.35, 0.01, 6800.52],
        "...(共60行，每行8维)"
    ]
}
```

> **重要**：`sequence_data` 必须是已经归一化（[0,1]）后的数据，使用训练时保存的 scaler（位置 `output/model_weight/scaler_{equipment_id}.pkl`）。  
> 若后端没有 scaler，请改用 `GET /api/v1/anomaly/equipment/{equipment_id}` 走自动检测流程，本接口由前端做精确实时检测时调用。  
> 当前 8 维特征顺序为：`load_rate, power, energy_diff, temperature, vibration, carbon_emission, power_change_rate, runtime_hours`

**响应体**

```json
{
    "code": 200,
    "data": {
        "is_anomaly": true,
        "reconstruction_error": 0.345,
        "threshold": 0.28,
        "threshold_type": "lstm",
        "anomaly_score": 1.232,
        "equipment_id": "I-9-01",
        "equipment_name": "电芯烘烤炉",
        "timestamp": "2026-08-21T14:30:00",
        "severity": "medium",
        "should_alert": true
    }
}
```

**严重程度分级**：`score = error / threshold`

| 分级   | 阈值范围    |
| ------ | ----------- |
| high   | score > 2.0 |
| medium | score > 1.5 |
| low    | score > 1.0 |
| normal | score ≤ 1.0 |

> **告警冷却**：同一设备 10 分钟内（`alert_cooldown_seconds=600`）只告警一次，避免频繁弹窗。

---

#### `GET /api/v1/anomaly/equipment/{equipment_id}` 设备当前异常状态

无需传 sequence_data，算法侧自动从 raw_data 加载最近 1 小时数据，构建序列并检测。

**路径参数**：`equipment_id`，如 `I-9-01`

**响应体**：同 `POST /api/v1/anomaly/detect`，但 `threshold_type` 可能是 `lstm` 或 `fallback`（无训练模型时退化为统计偏离度）。

---

### 3.3 溯源

#### `POST /api/v1/traceability/report` 设备碳排溯源报告

**请求体**

```json
{
    "equipment_id": "I-9-01",
    "anomaly_time": "2026-08-21T14:30:00",
    "hours": 72
}
```

**响应体**

```json
{
    "code": 200,
    "data": {
        "equipment_id": "I-9-01",
        "equipment_name": "电芯烘烤炉",
        "equipment_type": "baking_oven",
        "workshop_id": "WS-01",
        "team_id": "TEAM-A",
        "anomaly_time": "2026-08-21 14:30:00",
        "carbon_emission": 26.2,
        "baseline_emission": 18.5,
        "excess_emission": 7.7,
        "root_causes": [
            {
                "cause": "温控异常-保温温度偏高",
                "confidence": 0.88,
                "detail": "..."
            },
            { "cause": "升温时间过长", "confidence": 0.72, "detail": "..." }
        ],
        "history_72h_summary": {
            "avg_load": 0.78,
            "avg_emission": 21.3,
            "runtime": 71.5,
            "avg_temp": 125.6,
            "temp_deviation": 5.6
        },
        "recommendation": "建议校准温度传感器，检查保温层密封情况，优化升温曲线...",
        "health_score": 85.5
    }
}
```

---

### 3.4 降碳方案

#### `POST /api/v1/strategy/generate` AI 降碳方案生成

**请求体**

```json
{
    "equipment_id": "I-9-01",
    "analysis_result": null
}
```

`analysis_result` 不传时，方案引擎使用默认模板；若已先调用 `/traceability/report` 拿到结果，可整段传入做精准匹配。

**响应体**

```json
{
    "code": 200,
    "data": {
        "equipment_id": "I-9-01",
        "strategies": [
            {
                "strategy_type": "equipment_maintenance",
                "title": "电芯烘烤炉温控校准与保温层维护",
                "target_equipment": "I-9-01",
                "actions": ["校准温度传感器...", "检查炉门密封与保温层..."],
                "estimated_energy_saving": "15.2%",
                "estimated_carbon_reduction": "23.8 kgCO2/天",
                "estimated_cost_saving": "¥6,800/月",
                "investment": "¥2,000（传感器校准+密封条更换）",
                "payback_period": "0.3个月",
                "priority": "high"
            },
            { "strategy_type": "production_scheduling", "...": "..." },
            { "strategy_type": "process_optimization", "...": "..." }
        ],
        "count": 3
    }
}
```

三类方案自动按投入产出比排序。

---

### 3.5 设备实时数据

#### `GET /api/v1/equipment/realtime/{equipment_id}` 设备实时数据

**路径参数**：`equipment_id`

**响应体**

```json
{
    "code": 200,
    "data": {
        "equipment_id": "I-9-01",
        "equipment_name": "电芯烘烤炉",
        "equipment_type": "baking_oven",
        "workshop_id": "WS-01",
        "timestamp": "2026-08-21T14:30:00",
        "power": 42.3,
        "load_rate": 0.94,
        "carbon_emission": 0.41,
        "temperature": 122.5,
        "status": 1,
        "is_anomaly": false
    }
}
```

> 数据缓存 30s（`services._CACHE_TTL=30.0`），高频调用不会重复计算。

---

#### `GET /api/v1/equipment/list` 设备列表（可按车间筛选）

**Query 参数**：`workshop_id`（可选，如 `WS-01`）

**响应体**

```json
{
    "code": 200,
    "data": {
        "count": 78,
        "items": [
            {
                "equipment_id": "A-1-01",
                "equipment_name": "外观检测机1号",
                "equipment_type": "appearance_inspector",
                "workshop_id": "WS-03",
                "team_id": "TEAM-A",
                "rated_power": 3.0,
                "category": "检测设备"
            }
        ],
        "workshop_filter": null
    }
}
```

---

## 四、错误码说明

| code | 含义                                   | 处理建议                                  |
| ---- | -------------------------------------- | ----------------------------------------- |
| 200  | 成功                                   | 正常处理                                  |
| 400  | 参数错误                               | 检查请求体 schema 是否匹配                |
| 404  | 资源不存在（如 equipment_id 不在清单） | 确认设备ID是否在 78 台清单内              |
| 500  | 服务内部错误                           | 查看 response.data.error 字段获取错误信息 |

> 所有 500 错误都做了 try-except 兜底，不会让 FastAPI 抛栈，但建议后端联调时关注 `data.error` 字段做日志记录。

---

## 五、调用示例

### cURL

```bash
# 厂区总览
curl http://localhost:8000/api/v1/carbon/overview

# 异常检测
curl -X POST http://localhost:8000/api/v1/anomaly/detect \
  -H "Content-Type: application/json" \
  -d '{"equipment_id":"I-9-01","sequence_data":[[0.78,35.4,0.59,122.5,0.45,0.34,0.02,6800.5],...]}'

# 降碳方案生成
curl -X POST http://localhost:8000/api/v1/strategy/generate \
  -H "Content-Type: application/json" \
  -d '{"equipment_id":"I-9-01"}'
```

### Python（requests）

```python
import requests
BASE = 'http://localhost:8000/api/v1'

# 厂区总览
r = requests.get(f'{BASE}/carbon/overview')
print(r.json())

# 溯源报告
r = requests.post(f'{BASE}/traceability/report', json={
    'equipment_id': 'I-9-01',
    'anomaly_time': '2026-08-21T14:30:00',
    'hours': 72,
})
print(r.json())
```

### JavaScript（axios）

```javascript
import axios from 'axios';
const API = axios.create({ baseURL: 'http://localhost:8000/api/v1' });

// 厂区总览
const overview = await API.get('/carbon/overview').then((r) => r.data.data);

// 设备列表
const list = await API.get('/equipment/list', {
    params: { workshop_id: 'WS-01' },
}).then((r) => r.data.data);
```

---

## 六、联调优先级

按以下顺序对接（与交接会议一致）：

1. `GET /api/v1/carbon/overview` — 厂区总览（首页数据）
2. `GET /api/v1/carbon/heatmap` — 热力图数据
3. `GET /api/v1/equipment/realtime/{id}` — 设备实时数据
4. `POST /api/v1/anomaly/detect` — 异常检测
5. `POST /api/v1/traceability/report` — 溯源报告
6. `POST /api/v1/strategy/generate` — 降碳方案

---

## 七、后端负责的对接事项

1. **数据库设计**：设备表、时序数据表、告警记录表、方案表、用户表
2. **数据采集**：对接 MES/EMS 系统、传感器数据写入数据库
3. **认证与权限**：登录、角色（管理层/运维岗/IT管理员）
4. **告警推送**：WebSocket 实时推送 + 移动端 + 邮件
5. **报表生成**：月度碳排报告、设备溯源台账（导出 PDF/Excel）
6. **历史存储**：3 年归档、高效时序查询
7. **部署**：Nginx 反向代理 + Docker 容器化（算法服务单独部署 8000 端口）

**实时数据流（关键链路）**：

```
传感器/PLC → 后端采集服务 → 数据库 → 后端调用 /anomaly/detect →
  算法返回异常 → 后端推 WebSocket → 前端弹窗
```

---

## 八、已知限制与下一步

- 当前算法侧仅生成模拟数据，**真实数据接入由后端完成**
- LSTM 模型未训练时，`/anomaly/detect` 会退化为 `fallback` 统计偏离度（不影响联调）
- `sequence_data` 必须是归一化后的数据，scaler 文件（`output/model_weight/scaler_{equipment_id}.pkl`）**仅在该设备训练后才存在**；当前未训练 → 接口自动 fallback，联调不受影响
- 高频接口（overview / heatmap / realtime）有 30 秒内存缓存，需要实时数据时让算法侧清缓存或缩短 TTL

如有问题随时找我（队长·算法）。

---

## 九、阶段1联调核对记录（实际响应 vs 文档差异）· 2026-08-30

> 按执行计划（Step 1A）要求，用 `test_api.py` 核对了全部接口的**实际返回字段**，差异如下。
> **后端按实际字段开发**，本文档其余章节已同步修正；`api_server/schemas.py` 契约也已对齐。

| #   | 接口                           | 差异点                                                                                                                  | 后端处理方式                                                                                    |
| --- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 1   | `POST /anomaly/detect`         | 实际多返回 `equipment_name` / `should_alert` / `threshold_type`（文档原 schema 漏了）                                   | 直接可用；`threshold_type` 取值：`lstm`(已训练) / `fallback`(未训练兜底) / `adaptive` / `fixed` |
| 2   | `POST /traceability/report`    | 实际多返回 `team_id` / `health_score`（0-100 设备健康分）                                                               | 直接可用，前端可展示健康分徽标                                                                  |
| 3   | `POST /strategy/generate`      | 方案对象无 `target` 字段，实为 `target_equipment`（设备类方案）/ `target_workshop`（车间类方案），另含 `constraints` 等 | 按方案类型取对应字段；schema 已同步                                                             |
| 4   | `GET /equipment/realtime/{id}` | 无数据时**不报错**，返回占位结构（power=0 等）+ `message` 字段                                                          | 前端判 `message` 存在时展示"暂无数据"                                                           |
| 5   | `POST /carbon/query`           | 无数据时返回 `records: []` + `message`                                                                                  | 同上                                                                                            |
| 6   | scaler 文件名                  | `scaler_{equipment_id}.pkl` **训练后才存在**；此前误提交的 `scaler.pkl` 残留已清理                                      | 联调前 `ls output/model_weight/` 核对；未训练时无需 scaler，接口自动 fallback                   |
| 7   | 缓存行为                       | overview / heatmap / realtime 有 30s 内存缓存                                                                           | 改数据不生效等 30s；生产可调 `services._CACHE_TTL`                                              |

**核对工具**：项目根目录 `python test_api.py`（算法 8000 起后运行）——末尾自动打印各接口实际顶层字段与本文档的比对结果。

**阶段1联调架构**（新增 `backend/` 脚手架）：

```
前端 → 后端 8001 (/api/xxx)  →  算法 8000 (/api/v1/xxx)
       backend/routes.py 透传转发
       backend/algorithm_client.py 统一超时/错误处理(503兜底)
```

后端脚手架启动与链路验收：

```bash
# 终端1：算法服务
python main.py

# 终端2：后端服务（项目根目录执行）
uvicorn backend.main:app --port 8001

# 终端3：链路验收（覆盖全部 8 个转发端点）
python backend/test_backend.py
```
