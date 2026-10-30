"""
protocols —— 工业协议适配层（把黑盒协议数据归一化为标准读数）

补齐「采集链路只有单一 HTTP 接口」的短板，支持三类现场主流协议：

    Modbus TCP/RTU   → 保持寄存器数组 → 标准读数（register/scale 映射）
    OPC UA           → 节点值 dict     → 标准读数（node 映射）
    MQTT             → JSON 消息       → 标准读数（topic 通配 + 字段映射）

归一化产物为标准读数 dict，结构对齐 collector.schemas.SensorReading，
可直接喂给 collector.service.IngestionService.write_batch / write_reading。

协议客户端库（pymodbus / opcua / paho-mqtt）在此不做硬导入，
由 collector.gateway.EdgeGateway 在实际连接时懒加载，避免无硬件环境装不上依赖。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


# ============================================================
# Modbus 保持寄存器地址映射（16 位整数寄存器 → 真实量纲）
# ============================================================
# value = 寄存器整数值 / scale，得到真实物理量。
# 现场 PLC 寄存器规划有差异时，只需改这里的 register / scale。
MODBUS_REGISTER_MAP: Dict[str, Dict[str, Any]] = {
    'power': {'register': 0, 'scale': 10.0, 'unit': 'kW'},          # 有功功率
    'temperature': {'register': 1, 'scale': 10.0, 'unit': '℃'},     # 设备温度
    'vibration': {'register': 2, 'scale': 100.0, 'unit': 'mm/s'},   # 振动
    'load_rate': {'register': 3, 'scale': 1000.0, 'unit': '(0-1)'},  # 负载率
}

# ============================================================
# OPC UA 节点映射（节点 ID / 名称 → 标准字段）
# ============================================================
OPCUA_NODE_MAP: Dict[str, str] = {
    'Power': 'power',
    'Temperature': 'temperature',
    'Vibration': 'vibration',
    'LoadRate': 'load_rate',
}

# ============================================================
# MQTT 主题约定
# ============================================================
# 主题模板：carbon_factory/{equipment_id}/reading
MQTT_TOPIC_TEMPLATE = 'carbon_factory/{equipment_id}/reading'


def _as_float(value: Any) -> Optional[float]:
    """把协议侧原始值安全转 float；None / 空串 / 非法值 → None"""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN → None


def _norm_ts(ts: Any) -> Optional[datetime]:
    """统一时间戳（协议侧可能传 ISO 字符串 / datetime / 缺省用当前时间）"""
    if ts is None:
        return datetime.now()
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return datetime.now()
    return datetime.now()


# ============================================================
# 各协议 → 标准读数
# ============================================================
def modbus_to_reading(
    equipment_id: str,
    registers: List[int],
    timestamp: Any = None,
    register_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> dict:
    """
    把 Modbus 保持寄存器数组 → 标准读数 dict。

    Parameters
    ----------
    registers : 顺序保持寄存器值列表（索引对应 register_map[field]['register']）
    register_map : 字段映射表，缺省用 MODBUS_REGISTER_MAP
    """
    mapping = register_map or MODBUS_REGISTER_MAP
    reg = list(registers)

    def _read(field: str) -> Optional[float]:
        spec = mapping.get(field)
        if not spec:
            return None
        idx = spec['register']
        if idx >= len(reg):
            return None
        raw = reg[idx]
        return round(raw / spec['scale'], 4)

    return {
        'equipment_id': str(equipment_id),
        'timestamp': _norm_ts(timestamp),
        'power': _read('power') or 0.0,
        'temperature': _read('temperature'),
        'vibration': _read('vibration'),
        'load_rate': _read('load_rate'),
        'carbon_emission': None,
    }


def opcua_to_reading(
    equipment_id: str,
    node_values: Dict[str, Any],
    timestamp: Any = None,
    node_map: Optional[Dict[str, str]] = None,
) -> dict:
    """
    把 OPC UA 节点值 dict → 标准读数 dict。

    Parameters
    ----------
    node_values : 节点名/节点ID → 值；字段名经 node_map 映射到标准字段
    node_map : 节点名 → 标准字段 映射，缺省用 OPCUA_NODE_MAP
    """
    mapping = node_map or OPCUA_NODE_MAP

    def _get(field: str) -> Optional[float]:
        # 找到映射到该标准字段的节点名（支持多个别名）
        for node_name, std_field in mapping.items():
            if std_field == field and node_name in node_values:
                return _as_float(node_values[node_name])
        return None

    return {
        'equipment_id': str(equipment_id),
        'timestamp': _norm_ts(timestamp),
        'power': _get('power') or 0.0,
        'temperature': _get('temperature'),
        'vibration': _get('vibration'),
        'load_rate': _get('load_rate'),
        'carbon_emission': None,
    }


def mqtt_to_reading(
    equipment_id: str,
    payload: Any,
    timestamp: Any = None,
) -> dict:
    """
    把 MQTT JSON 消息 → 标准读数 dict。

    payload 支持两种形态：
        1. 平铺 dict：{'power': 12.3, 'temperature': 40.1, ...}
        2. 带 'data' 键的嵌套 dict：{'data': {...}}
    """
    if isinstance(payload, (bytes, bytearray)):
        import json
        try:
            payload = json.loads(payload.decode('utf-8'))
        except Exception:
            payload = {}
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    if not isinstance(payload, dict):
        payload = {}

    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload

    ts = payload.get('timestamp') if isinstance(payload.get('timestamp'), (str, datetime)) else timestamp

    return {
        'equipment_id': str(equipment_id),
        'timestamp': _norm_ts(ts),
        'power': _as_float(data.get('power')) or 0.0,
        'temperature': _as_float(data.get('temperature')),
        'vibration': _as_float(data.get('vibration')),
        'load_rate': _as_float(data.get('load_rate')),
        'carbon_emission': _as_float(data.get('carbon_emission')),
    }


def normalize_gateway_reading(
    protocol: str,
    equipment_id: str,
    raw: Any,
    timestamp: Any = None,
) -> dict:
    """协议无关的统一入口：按协议分发到对应适配器，产出标准读数 dict。"""
    protocol = (protocol or '').strip().lower()
    if protocol in ('modbus', 'modbus_tcp', 'modbus_rtu'):
        registers = raw.get('registers') if isinstance(raw, dict) else None
        if registers is None and isinstance(raw, (list, tuple)):
            registers = raw
        if not isinstance(registers, (list, tuple)):
            raise ValueError('modbus 需要 registers（保持寄存器数组）或 {"registers": [...]}')
        return modbus_to_reading(equipment_id, list(registers), timestamp)
    if protocol in ('opcua', 'opc_ua', 'opc-ua'):
        if not isinstance(raw, dict):
            raise ValueError('opcua 需要节点值 dict（node名 → 值）')
        return opcua_to_reading(equipment_id, raw, timestamp)
    if protocol in ('mqtt',):
        return mqtt_to_reading(equipment_id, raw, timestamp)
    raise ValueError(f'不支持的协议: {protocol}（支持 modbus / opcua / mqtt）')