"""
gateway —— 边缘网关（主动采集 / 订阅，统一入写）

把「只能靠 MES/EMS 推 HTTP」升级为「边缘网关主动接现场设备」：

    poll_modbus()   用 pymodbus 主动轮询 PLC 保持寄存器 → 归一化入写
    poll_opcua()    用 opcua 主动读取 OPC UA 数据节点 → 归一化入写
    run_mqtt()      用 paho-mqtt 订阅主题，消息到达即归一化入写（常驻）
    ingest_reading() 协议无关的 HTTP 网关入口（配合后端 /api/ingest/gateway 路由）

协议客户端库按需懒加载：未安装时抛出带安装提示的 RuntimeError，
调用方（后端路由）据此降级为 501 并返回提示，不影响既有 HTTP 采集链路。

实用方式：
    from collector.gateway import EdgeGateway
    gw = EdgeGateway()
    gw.ingest_reading('mqtt', 'I-9-01', {'power': 12.3, 'temperature': 40.1})
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config.settings import PROTOCOL_CONFIG
from . import protocols
from .service import IngestionService

logger = logging.getLogger(__name__)


class EdgeGateway:
    """边缘网关：协议采集 → 归一化 → IngestionService 入写"""

    def __init__(self, service: Optional[IngestionService] = None):
        self.service = service or IngestionService()

    # ---------------- 协议无关的统一入写入口 ----------------
    def ingest_reading(
        self,
        protocol: str,
        equipment_id: str,
        raw: Any,
        timestamp: Any = None,
    ) -> Dict[str, Any]:
        """HTTP 网关入口：原始协议 payload → 标准读数 → 入写（返回写入统计 + 读数）"""
        reading = protocols.normalize_gateway_reading(protocol, equipment_id, raw, timestamp)
        stats = self.service.write_batch([reading])
        return {'protocol': protocol, 'reading': reading, 'result': stats}

    # ---------------- Modbus TCP ----------------
    def poll_modbus(
        self,
        equipment_ids: List[str],
        host: Optional[str] = None,
        port: Optional[int] = None,
        unit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        轮询 PLC 保持寄存器并入写。
        每个设备读 MODBUS_REGISTER_MAP 覆盖的寄存器区间（address=0，count=max+1）。
        """
        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError as exc:
            raise RuntimeError('未安装 pymodbus，请先 `pip install pymodbus` 再接 Modbus 设备') from exc

        cfg = PROTOCOL_CONFIG['modbus']
        host = host or cfg['host']
        port = port or cfg['port']
        unit = unit if unit is not None else cfg['unit']

        # 计算需要读取的寄存器数量（覆盖映射中最大的 register 下标）
        count = max(s['register'] for s in protocols.MODBUS_REGISTER_MAP.values()) + 1

        client = ModbusTcpClient(host, port=port)
        client.connect()
        try:
            results = {}
            for eq_id in equipment_ids:
                rr = client.read_holding_registers(address=0, count=count, slave=unit)
                if rr.isError():
                    results[eq_id] = {'error': f'读取失败: {rr}'}
                    continue
                reading = protocols.modbus_to_reading(eq_id, list(rr.registers))
                stats = self.service.write_batch([reading])
                results[eq_id] = {'reading': reading, 'result': stats}
            return {'protocol': 'modbus', 'host': host, 'port': port, 'unit': unit, 'devices': results}
        finally:
            client.close()

    # ---------------- OPC UA ----------------
    def poll_opcua(
        self,
        equipment_ids: List[str],
        endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """读取 OPC UA 数据节点并入写。节点名需与 OPCUA_NODE_MAP 的 key 对应。"""
        try:
            from opcua import Client
        except ImportError as exc:
            raise RuntimeError('未安装 opcua，请先 `pip install opcua` 再接 OPC UA 服务器') from exc

        endpoint = endpoint or PROTOCOL_CONFIG['opcua']['endpoint']
        client = Client(endpoint)
        try:
            client.connect()
            results = {}
            for eq_id in equipment_ids:
                node_values = {
                    name: client.get_node(f'ns=2;i={i}').get_value()
                    for i, name in enumerate(protocols.OPCUA_NODE_MAP)
                }
                reading = protocols.opcua_to_reading(eq_id, node_values)
                stats = self.service.write_batch([reading])
                results[eq_id] = {'reading': reading, 'result': stats}
            return {'protocol': 'opcua', 'endpoint': endpoint, 'devices': results}
        finally:
            client.disconnect()

    # ---------------- MQTT 订阅（常驻） ----------------
    def run_mqtt(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        topic: Optional[str] = None,
    ) -> None:
        """
        订阅 MQTT 主题并常驻消费，消息到达即归一化入写（阻塞调用）。

        主题约定：carbon_factory/{equipment_id}/reading，收到后从主题里解出设备ID。
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError('未安装 paho-mqtt，请先 `pip install paho-mqtt` 再订阅 MQTT 代理') from exc

        cfg = PROTOCOL_CONFIG['mqtt']
        host = host or cfg['host']
        port = port or cfg['port']
        topic = topic or cfg['topic']

        def on_connect(client, userdata, flags, rc):
            client.subscribe(topic)
            logger.info('MQTT 网关已订阅 %s（rc=%s）', topic, rc)

        def on_message(client, userdata, msg):
            try:
                # 从 carbon_factory/{equipment_id}/reading 解出设备ID
                parts = msg.topic.split('/')
                if len(parts) >= 2:
                    eq_id = parts[1]
                else:
                    logger.warning('无法从主题解析设备ID: %s', msg.topic)
                    return
                res = self.ingest_reading('mqtt', eq_id, msg.payload)
                logger.info('MQTT 入写 %s: %s', eq_id, res['result'])
            except Exception:
                logger.exception('MQTT 消息处理失败: %s', msg.topic)

        client = mqtt.Client(client_id=cfg['client_id'])
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(host, port, cfg['keepalive'])
        client.loop_forever()