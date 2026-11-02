"""
settings —— 全局配置中心

本文件汇总了项目所有"硬编码"参数：
  1. 项目路径
  2. IPCC 碳排放核算因子
  3. LSTM 模型超参数
  4. 异常检测阈值配置
  5. 设备清单（基于《设备清单.xlsx》共78台/12类设备）
  6. 车间 / 班组 / 层级配置
  7. API 服务配置

后端同学联调时若需要调整某个常量，**只改这里一处**即可，
其它模块都从这里 import，不要在业务代码里重复硬编码。
"""

import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

# 加载项目根目录 .env（邮件 SMTP / 移动端推送等真实凭据不进入代码仓库）
load_dotenv()

# ============================================================
# 1. 项目路径
# ============================================================
# BASE_DIR = 项目根目录（carbon_factory/）
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
RAW_DATA_DIR = DATA_DIR / 'raw_data'  # 原始 CSV / 数据库快照
PROCESS_DATA_DIR = DATA_DIR / 'process_data'  # 清洗后中间产物
OUTPUT_DIR = BASE_DIR / 'output'
MODEL_WEIGHT_DIR = OUTPUT_DIR / 'model_weight'  # LSTM 权重 + scaler
LOG_DIR = OUTPUT_DIR / 'log'
CHART_DIR = OUTPUT_DIR / 'chart'  # 训练曲线、误差分布图等

# 启动时自动建好输出目录，避免训练/评估时写文件失败
for _d in [PROCESS_DATA_DIR, MODEL_WEIGHT_DIR, LOG_DIR, CHART_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. IPCC 碳排放核算因子（单位：kgCO2 / 单位能源）
# ============================================================
# 数据来源：IPCC 2006 Guidelines + 中国南方电网区域平均排放因子
# electricity 0.5810 为中国南方区域电网平均因子，后端做地域切换时可改这里
CARBON_FACTORS = {
    'electricity': 0.5810,  # kgCO2/kWh（南方电网区域因子）
    'natural_gas': 2.1622,  # kgCO2/m³
    'coal': 2.6600,  # kgCO2/kg
    'diesel': 3.0959,  # kgCO2/L
    'compressed_air': 0.12,  # kgCO2/m³（按空压机耗电折算的估算值）
}


# ============================================================
# 3. LSTM 模型超参数
# ============================================================
# input_size=8 对应 feature_extractor 输出的8维特征
#   (load_rate, power, energy_diff, temperature, vibration,
#    carbon_emission, power_change_rate, runtime_hours)
# sequence_length=60 表示用过去60分钟数据预测/重建
MODEL_CONFIG = {
    'input_size': 8,
    'hidden_size': 128,
    'num_layers': 2,
    'output_size': 8,
    'dropout': 0.2,
    'sequence_length': 60,
    'prediction_steps': 1,
    'batch_size': 32,
    'learning_rate': 0.001,
    'epochs': 100,
    'early_stopping_patience': 10,
    'device': 'cpu',  # 开发用 CPU，部署生产可改 'cuda'
}


# ============================================================
# 4. 异常检测阈值配置
# ============================================================
# adaptive 自适应阈值：用过去 adaptive_window 小时的重建误差
#   均值 + sigma_multiplier × 标准差 作为告警线
# alert_cooldown_seconds：同一设备告警冷却，避免短时间内重复弹窗
THRESHOLD_CONFIG = {
    'method': 'adaptive',
    'fixed_threshold': 0.5,
    'adaptive_window': 24,  # 小时
    'sigma_multiplier': 3.0,
    'alert_cooldown_seconds': 600,
}


# ============================================================
# 4b. 告警推送配置（WebSocket 实时推送 + 多渠道通知）
# ============================================================
# 严重程度分级（与 Lstm_model.anomaly_detector._classify_severity 对齐，
# 基于 anomaly_score = reconstruction_error / threshold）
SEVERITY_LEVELS = ['normal', 'low', 'medium', 'high']
SEVERITY_LABELS = {
    'normal': '正常',
    'low': '低',
    'medium': '中',
    'high': '高',
}

ALERT_CONFIG = {
    # 前端 WebSocket 连接路径（相对后端服务根，落地为 ws://host:8001/ws/alerts）
    'ws_path': '/ws/alerts',
    # 后台检测循环扫描间隔（秒）；同一设备告警冷却仍由算法侧 600s 控制
    'detect_interval_seconds': 30,
    # 参与实时扫描的代表设备（与 data.generate_sample_data.REPRESENTATIVE_EQUIPMENT 对齐）
    'scan_equipment': [
        'I-9-01', 'COMP-01', 'D-4-01', 'C-3-01',
        'L-12-01', 'FAN-01', 'CHILL-01', 'A-1-01',
    ],
}


# ============================================================
# 4c. 多渠道告警推送配置（邮件 SMTP + 移动端 PushPlus/Server酱）
# ============================================================
# 真实凭据不写入代码，统一通过项目根目录 .env 提供（见 .env.example）。
# 未配置时，notifier 中各渠道自动降级为日志记录，不影响主流程。

SMTP_CONFIG = {
    'host': os.environ.get('SMTP_HOST', ''),
    'port': int(os.environ.get('SMTP_PORT', '465')),
    'user': os.environ.get('SMTP_USER', ''),
    'password': os.environ.get('SMTP_PASSWORD', ''),
    'from_addr': os.environ.get('SMTP_FROM', ''),
    'to_addrs': os.environ.get('SMTP_TO', ''),  # 逗号分隔多个收件人
    'use_ssl': os.environ.get('SMTP_USE_SSL', '1').lower() in ('1', 'true', 'yes'),
}

MOBILE_PUSH_CONFIG = {
    'type': os.environ.get('PUSH_TYPE', 'pushplus'),  # pushplus | serverchan
    'pushplus_token': os.environ.get('PUSHPLUS_TOKEN', ''),
    'serverchan_key': os.environ.get('SERVERCHAN_KEY', ''),
}


# ============================================================
# 4d. 工业协议与边缘网关接入配置（Modbus / OPC UA / MQTT）
# ============================================================
# 真实地址通过项目根目录 .env 提供；未配置时用本机默认值。
# 协议客户端库（pymodbus / opcua / paho-mqtt）按需懒加载，未安装时网关自动降级并提示。
PROTOCOL_CONFIG = {
    'modbus': {
        'host': os.environ.get('MODBUS_HOST', '127.0.0.1'),
        'port': int(os.environ.get('MODBUS_PORT', '502')),
        'unit': int(os.environ.get('MODBUS_UNIT', '1')),
    },
    'opcua': {
        'endpoint': os.environ.get('OPCUA_ENDPOINT', 'opc.tcp://127.0.0.1:4840'),
    },
    'mqtt': {
        'host': os.environ.get('MQTT_HOST', '127.0.0.1'),
        'port': int(os.environ.get('MQTT_PORT', '1883')),
        'topic': os.environ.get('MQTT_TOPIC', 'carbon_factory/+/reading'),
        'client_id': os.environ.get('MQTT_CLIENT_ID', 'carbon_gateway'),
        'keepalive': int(os.environ.get('MQTT_KEEPALIVE', '60')),
    },
}


# ============================================================
# 4e. 分项计量映射（照明 / 空调 / 动力 / 产线）
# ============================================================
# key = equipment_type（见下方 EQUIPMENT_TYPES），value = 分项。
# 未命中时默认归入「产线」；若后续新增照明计量点，在此把 type 映射到「照明」即可。
SUBMETER_CATEGORIES = ['照明', '空调', '动力', '产线']
SUBMETER_MAP = {
    'chiller': '空调',
    'cooling_fan': '空调',
    'compressor': '动力',
    # 'lighting': '照明',  # 预留：新增照明计量点时开启
}


# ============================================================
# 5. 设备类型配置（基于《设备清单.xlsx》9类生产设备 + 3类公用动力）
# ============================================================
# key = equipment_type 标识
# rated_power = 估算额定功率(kW)，实际部署以设备铭牌为准
# efficiency_curve = 能效曲线类型，供 carbon_strategy.equipment_models 使用
EQUIPMENT_TYPES = {
    # === 生产设备 ===
    'appearance_inspector': {
        'name': '电芯外观检测机',
        'rated_power': 3.0,
        'efficiency_curve': 'linear',
        'category': '检测设备',
    },
    'dimension_inspector': {
        'name': '电芯尺寸检测机',
        'rated_power': 2.5,
        'efficiency_curve': 'linear',
        'category': '检测设备',
    },
    'winding_machine': {
        'name': '电芯卷绕机',
        'rated_power': 15.0,
        'efficiency_curve': 'linear',
        'category': '生产设备',
    },
    'formation_cabinet': {
        'name': '电芯化成柜',
        'rated_power': 8.0,
        'efficiency_curve': 'polynomial',
        'category': '生产设备',
    },
    'sorting_machine': {
        'name': '电芯分选机',
        'rated_power': 4.0,
        'efficiency_curve': 'linear',
        'category': '检测设备',
    },
    'conveyor_line': {
        'name': '电芯输送流水线',
        'rated_power': 5.5,
        'efficiency_curve': 'quadratic',
        'category': '物流设备',
    },
    'baking_oven': {
        'name': '电芯烘烤炉',
        'rated_power': 45.0,
        'efficiency_curve': 'polynomial',
        'category': '生产设备',
    },
    'agv': {
        'name': '自动导引运输车AGV',
        'rated_power': 1.5,
        'efficiency_curve': 'linear',
        'category': '物流设备',
    },
    'cnc_milling_machine': {
        'name': '数控龙门铣床',
        'rated_power': 18.5,
        'efficiency_curve': 'polynomial',
        'category': '加工设备',
    },
    # === 公用动力设备（设备清单未列但项目方案要求监测）===
    'compressor': {
        'name': '空压机',
        'rated_power': 75.0,
        'efficiency_curve': 'polynomial',
        'category': '公用动力',
    },
    'cooling_fan': {
        'name': '冷却风机',
        'rated_power': 15.0,
        'efficiency_curve': 'quadratic',
        'category': '公用动力',
    },
    'chiller': {
        'name': '冷水机组',
        'rated_power': 55.0,
        'efficiency_curve': 'polynomial',
        'category': '公用动力',
    },
}


# ============================================================
# 6. 设备清单明细（每台设备的唯一ID映射）
# ============================================================
# 命名规则：
#   生产设备：{清单编号}-{两位序号}  例：C-3-01 ~ C-3-15
#   公用设备：{类型缩写}-{两位序号}  例：COMP-01 ~ COMP-03
# 字段说明：
#   equipment_type → 见上方 EQUIPMENT_TYPES
#   workshop_id    → 所属车间（见下方 WORKSHOPS）
#   team_id        → 所属班组（见下方 TEAMS）
# 后端联调时：所有设备ID都从这里取，保证算法侧与后端数据库一致
def _build_equipment_list() -> dict:
    """按设备清单批量生成 equipment_id → 元信息的映射"""
    eq_list = {}

    # A-1 电芯外观检测机 ×10（WS-03 检测分选车间）
    eq_list.update(
        {
            f'A-1-{i:02d}': {
                'equipment_type': 'appearance_inspector',
                'name': f'外观检测机{i}号',
                'workshop_id': 'WS-03',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 11)
        }
    )
    # B-2 电芯尺寸检测机 ×5
    eq_list.update(
        {
            f'B-2-{i:02d}': {
                'equipment_type': 'dimension_inspector',
                'name': f'尺寸检测机{i}号',
                'workshop_id': 'WS-03',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 6)
        }
    )
    # C-3 电芯卷绕机 ×15（WS-01 制备车间）
    eq_list.update(
        {
            f'C-3-{i:02d}': {
                'equipment_type': 'winding_machine',
                'name': f'卷绕机{i}号',
                'workshop_id': 'WS-01',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 16)
        }
    )
    # D-4 电芯化成柜 ×10（WS-02 化成车间，24小时运行）
    eq_list.update(
        {
            f'D-4-{i:02d}': {
                'equipment_type': 'formation_cabinet',
                'name': f'化成柜{i}号',
                'workshop_id': 'WS-02',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 11)
        }
    )
    # E-5 电芯分选机 ×5
    eq_list.update(
        {
            f'E-5-{i:02d}': {
                'equipment_type': 'sorting_machine',
                'name': f'分选机{i}号',
                'workshop_id': 'WS-03',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 6)
        }
    )
    # F-6 电芯外观检测机 ×5（第二条检测线，归属乙班）
    eq_list.update(
        {
            f'F-6-{i:02d}': {
                'equipment_type': 'appearance_inspector',
                'name': f'外观检测机{10 + i}号',
                'workshop_id': 'WS-03',
                'team_id': 'TEAM-B',
            }
            for i in range(1, 6)
        }
    )
    # G-7 电芯分选机 ×5（第二条分选线）
    eq_list.update(
        {
            f'G-7-{i:02d}': {
                'equipment_type': 'sorting_machine',
                'name': f'分选机{5 + i}号',
                'workshop_id': 'WS-03',
                'team_id': 'TEAM-B',
            }
            for i in range(1, 6)
        }
    )
    # H-8 电芯输送流水线 ×1
    eq_list['H-8-01'] = {
        'equipment_type': 'conveyor_line',
        'name': '主输送流水线',
        'workshop_id': 'WS-01',
        'team_id': 'TEAM-A',
    }
    # I-9 电芯烘烤炉 ×1（高耗能重点监测）
    eq_list['I-9-01'] = {
        'equipment_type': 'baking_oven',
        'name': '电芯烘烤炉',
        'workshop_id': 'WS-01',
        'team_id': 'TEAM-A',
    }
    # J-10 电芯化成柜 ×6（第二条化成线）
    eq_list.update(
        {
            f'J-10-{i:02d}': {
                'equipment_type': 'formation_cabinet',
                'name': f'化成柜{10 + i}号',
                'workshop_id': 'WS-02',
                'team_id': 'TEAM-B',
            }
            for i in range(1, 7)
        }
    )
    # K-11 AGV ×2（充电时段计入能耗）
    eq_list.update(
        {
            f'K-11-{i:02d}': {
                'equipment_type': 'agv',
                'name': f'AGV{i}号',
                'workshop_id': 'WS-05',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 3)
        }
    )
    # L-12 数控龙门铣床 ×4
    eq_list.update(
        {
            f'L-12-{i:02d}': {
                'equipment_type': 'cnc_milling_machine',
                'name': f'龙门铣床{i}号',
                'workshop_id': 'WS-04',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 5)
        }
    )
    # 公用动力设备
    eq_list.update(
        {
            f'COMP-{i:02d}': {
                'equipment_type': 'compressor',
                'name': f'空压机{i}号',
                'workshop_id': 'WS-05',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 4)
        }
    )
    eq_list.update(
        {
            f'FAN-{i:02d}': {
                'equipment_type': 'cooling_fan',
                'name': f'冷却风机{i}号',
                'workshop_id': 'WS-05',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 5)
        }
    )
    eq_list.update(
        {
            f'CHILL-{i:02d}': {
                'equipment_type': 'chiller',
                'name': f'冷水机组{i}号',
                'workshop_id': 'WS-05',
                'team_id': 'TEAM-A',
            }
            for i in range(1, 3)
        }
    )
    return eq_list


EQUIPMENT_LIST = _build_equipment_list()


# ============================================================
# 7. 车间配置
# ============================================================
# equipment_count 用于校验：开发期=78台，部署后以实际接入数量为准
WORKSHOPS = {
    'WS-01': {'name': '电芯制备车间', 'equipment_count': 17},
    'WS-02': {'name': '电芯化成车间', 'equipment_count': 16},
    'WS-03': {'name': '电芯检测分选车间', 'equipment_count': 30},
    'WS-04': {'name': '模具加工车间', 'equipment_count': 4},
    'WS-05': {'name': '物流动力区', 'equipment_count': 11},
}


# ============================================================
# 7b. 组织层级（集团 → 工厂 → 车间）与数据范围
# ============================================================
# 三级组织树：解决「单组织、无集团-工厂-车间多层级」的问题，
# 支撑多租户下的组织级数据隔离与权限（见 backend.security.visible_workshops）。
ORGANIZATION_TREE = {
    'name': '锂能智造集团',
    'code': 'ORG-LINENG',
    'factories': [
        {'code': 'F-01', 'name': '华南一厂（电芯基地）', 'workshops': ['WS-01', 'WS-02', 'WS-03']},
        {'code': 'F-02', 'name': '华南二厂（模组基地）', 'workshops': ['WS-04', 'WS-05']},
    ],
}

# 数据范围粒度：all=全集团（跨工厂）/ factory=单工厂 / workshop=单车间（组织级权限）
DATA_SCOPES = ['all', 'factory', 'workshop']


# ============================================================
# 8. 班组配置
# ============================================================
TEAMS = {
    'TEAM-A': {'name': '甲班（早班）', 'shift': '8:00-16:00'},
    'TEAM-B': {'name': '乙班（中班）', 'shift': '16:00-0:00'},
    'TEAM-C': {'name': '丙班（夜班）', 'shift': '0:00-8:00'},
}


# ============================================================
# 9. 四级聚合层级
# ============================================================
# 算法侧 carbon_calculator.aggregate_by_level 据此分支
HIERARCHY_LEVELS = ['factory', 'workshop', 'equipment', 'team']


# ============================================================
# 10. API 配置
# ============================================================
API_CONFIG = {
    'host': '0.0.0.0',
    'port': 8000,
    'reload': True,  # 开发热重载，生产部署建议关闭
}

# 跨域（CORS）白名单：允许访问的源，逗号分隔，可用环境变量 CORS_ORIGINS 覆盖。
# 默认放行 Vue 开发服务器(5173) 与前端静态站(8002)。生产部署时可改为实际前端域名。
# 注意：allow_credentials=True 时禁用 '*'，必须显式列出源，因此集中在此维护。
CORS_ORIGINS = [
    _o.strip()
    for _o in os.environ.get(
        'CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,'
        'http://localhost:8002,http://127.0.0.1:8002',
    ).split(',')
    if _o.strip()
]


# ============================================================
# 11. 认证与角色权限配置（阶段2 · 登录/角色管理）
# ============================================================
# 三种角色：管理层 / 运维岗 / IT管理员
#   permissions 为权限标识列表，'*' 表示拥有全部权限（仅 IT管理员）
# 权限标识约定（可按需在业务路由中校验）：
#   view:dashboard    查看碳排总览
#   view:heatmap      查看碳排热力图
#   view:equipment    查看设备实时/列表
#   view:alarm        查看告警
#   handle:alarm      处理告警
#   view:report       查看溯源报告
#   generate:strategy 生成降碳方案
#   manage:user       用户与角色管理
ROLES = {
    'management': {
        'name': '管理层',
        'description': '厂区/车间管理层：查看总览、热力图、溯源报告，生成降碳方案',
        'permissions': [
            'view:dashboard',
            'view:heatmap',
            'view:equipment',
            'view:alarm',
            'view:report',
            'generate:strategy',
        ],
    },
    'operator': {
        'name': '运维岗',
        'description': '设备运维人员：查看设备实时工况与告警，处理告警',
        'permissions': [
            'view:equipment',
            'view:alarm',
            'handle:alarm',
        ],
    },
    'it_admin': {
        'name': 'IT管理员',
        'description': '系统管理员：拥有全部权限（含用户与角色管理、系统配置）',
        'permissions': ['*'],
    },
}

_DEFAULT_SECRET = 'carbon-factory-dev-secret-change-me'

AUTH_CONFIG = {
    # 令牌签名密钥（生产务必通过环境变量 AUTH_SECRET_KEY 覆盖，勿硬编码到仓库）
    'secret_key': os.environ.get('AUTH_SECRET_KEY', _DEFAULT_SECRET),
    # 签名算法标识（令牌负载中记录，便于将来扩展非对称算法）
    'algorithm': 'HS256',
    # 访问令牌有效期（秒），默认 8 小时；可用 AUTH_TOKEN_EXPIRE 覆盖
    'access_token_expire_seconds': int(os.environ.get('AUTH_TOKEN_EXPIRE', 8 * 3600)),
    # 密码 PBKDF2-HMAC-SHA256 迭代次数
    'pbkdf2_iterations': 100_000,
}

# 生产安全护栏：生产环境若使用默认/空密钥，直接拒绝启动，防止 JWT 令牌被伪造
if os.environ.get('APP_ENV', '').lower() == 'production':
    if not AUTH_CONFIG['secret_key'] or AUTH_CONFIG['secret_key'] == _DEFAULT_SECRET:
        raise RuntimeError(
            '生产环境(APP_ENV=production)必须通过 AUTH_SECRET_KEY 设置独立随机密钥，'
            '禁止使用默认密钥或留空'
        )
# 开发环境使用默认密钥时给出醒目警告
elif AUTH_CONFIG['secret_key'] == _DEFAULT_SECRET:
    warnings.warn(
        'AUTH_SECRET_KEY 未配置，正在使用开发默认密钥，JWT 令牌可被伪造；'
        '生产部署务必通过环境变量设置 AUTH_SECRET_KEY',
        RuntimeWarning,
        stacklevel=2,
    )


# ============================================================
# 11b. 历史存储归档配置（3 年留存 + 高效时序查询）
# ============================================================
# 分层存储策略：分钟级原始数据仅保留近 retention_raw_days 天，
# 过期后降采样为「小时 / 天」统计桶写入 time_series_archive，
# 归档数据保留 retention_archive_years 年，超出后清理。
ARCHIVE_CONFIG = {
    # 分钟级原始数据保留天数（超过则滚动归档并删除原始行）
    'retention_raw_days': int(os.environ.get('ARCHIVE_RAW_DAYS', 30)),
    # 归档数据保留年限（3 年），超过后从归档表清除
    'retention_archive_years': int(os.environ.get('ARCHIVE_YEARS', 3)),
    # 后台归档调度间隔（小时）；亦可通过 POST /api/history/archive 手动触发
    'archive_interval_hours': int(os.environ.get('ARCHIVE_INTERVAL_HOURS', 24)),
}


# ============================================================
# 11c. AI Agent（DeepSeek 大模型）
# ============================================================
# 由 .env 注入：DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL
# deepseek-chat 支持 function calling，deepseek-reasoner 用于深度推理
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
DEEPSEEK_TIMEOUT = float(os.environ.get('DEEPSEEK_TIMEOUT', 60))
DEEPSEEK_MAX_TOOL_ROUNDS = int(os.environ.get('DEEPSEEK_MAX_TOOL_ROUNDS', 5))


# ============================================================
# 12. 统一导出（settings 字典，便于整体传入或一次性查看）
# ============================================================
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
    'CARBON_FACTORS': CARBON_FACTORS,
    'MODEL_CONFIG': MODEL_CONFIG,
    'THRESHOLD_CONFIG': THRESHOLD_CONFIG,
    'SEVERITY_LEVELS': SEVERITY_LEVELS,
    'SEVERITY_LABELS': SEVERITY_LABELS,
    'ALERT_CONFIG': ALERT_CONFIG,
    'ROLES': ROLES,
    'AUTH_CONFIG': AUTH_CONFIG,
    'ARCHIVE_CONFIG': ARCHIVE_CONFIG,
}
