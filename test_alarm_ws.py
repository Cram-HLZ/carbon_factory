"""
test_alarm_ws —— 告警中心「实时弹窗」链路测试（WebSocket 推送验证）

【用途】
    模拟前端 WebSocket 客户端订阅 ws://localhost:8001/ws/alerts，
    注入一段「前 59 分钟正常 + 最后 1 分钟异常」的工况数据，
    触发后端检测扫描，验证后端是否实时广播 {type:'alarm'} 告警消息。

    前端 alarmRealtime.js 收到 type=='alarm' 即弹窗，因此本脚本收到该消息，
    即等价于「告警中心弹窗」链路打通。

【零依赖】只使用 Python 标准库（socket 手写 WebSocket 客户端），无需安装额外包。

【前置条件】
    1. 启动算法服务:  python main.py                        # 8000
    2. 启动后端服务:  uvicorn backend.main:app --port 8001  # 8001
    3. 数据库已初始化，且默认账号可用（admin / Admin@123）

【用法】
    python test_alarm_ws.py                              # 完整链路：注入→扫描→收推送
    python test_alarm_ws.py --eq I-9-01                  # 指定设备
    python test_alarm_ws.py --no-scan                    # 只连 WS 收广播，不注入/不扫描

【告警冷却说明】
    同一设备 10 分钟内只能触发一次告警（算法侧 alert_cooldown_seconds=600）。
    若刚测过一轮再跑，会因冷却 should_alert=False 而不推送。
    对策：重启算法服务(8000) 重置冷却，或更换 --eq 到其它未冷却设备，或等 10 分钟。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

BASE = 'http://127.0.0.1:8001'
WS_PATH = '/ws/alerts'

TARGET_EQ = 'I-9-01'  # 电芯烘烤炉（额定 45kW，scan_equipment 代表设备之一）

received = []


class SimpleWS:
    """极简 WebSocket 客户端（仅标准库），用于订阅后端告警广播并接收文本帧。"""

    def __init__(self, url: str, timeout: float = 10.0):
        rest = url.split('://', 1)[1] if '://' in url else url
        hostport, _, path = rest.partition('/')
        path = '/' + path
        if ':' in hostport:
            self.host, port = hostport.rsplit(':', 1)
            self.port = int(port)
        else:
            self.host, self.port = hostport, 80
        self.path = path
        self.timeout = timeout
        self.sock = None
        self._buf = b''

    def connect(self) -> bool:
        """TCP 连接 + WebSocket 握手，成功返回 True。"""
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f'GET {self.path} HTTP/1.1\r\n'
            f'Host: {self.host}:{self.port}\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            'Sec-WebSocket-Version: 13\r\n'
            '\r\n'
        )
        self.sock.sendall(req.encode('ascii'))
        self.sock.settimeout(self.timeout)
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError('握手失败：连接被关闭')
            data += chunk
        head, _, self._buf = data.partition(b'\r\n\r\n')
        status = head.split(b'\r\n', 1)[0]
        if b'101' not in status:
            raise IOError(f'WebSocket 握手失败: {head.decode(errors="replace")}')
        return True

    def _require_sock(self) -> socket.socket:
        """返回已建立的 socket；未连接时抛错（同时消除 Pylance 的 Optional 告警）。"""
        if self.sock is None:
            raise IOError('WebSocket 未连接，请先调用 connect()')
        return self.sock

    def recv_frame(self):
        """接收一帧，返回 (opcode, payload)。0x1=text 0x8=close 0x9=ping 0xA=pong"""
        sock = self._require_sock()
        while len(self._buf) < 2:
            chunk = sock.recv(4096)
            if not chunk:
                raise IOError('连接已关闭')
            self._buf += chunk
        b0, b1 = self._buf[0], self._buf[1]
        opcode = b0 & 0x0F
        masked = (b1 & 0x80) != 0
        length = b1 & 0x7F
        offset = 2
        if length == 126:
            while len(self._buf) < offset + 2:
                self._buf += sock.recv(4096)
            length = struct.unpack('>H', self._buf[offset:offset + 2])[0]
            offset += 2
        elif length == 127:
            while len(self._buf) < offset + 8:
                self._buf += sock.recv(4096)
            length = struct.unpack('>Q', self._buf[offset:offset + 8])[0]
            offset += 8
        if masked:
            while len(self._buf) < offset + 4:
                self._buf += sock.recv(4096)
            mask = self._buf[offset:offset + 4]
            offset += 4
        else:
            mask = None
        while len(self._buf) < offset + length:
            chunk = sock.recv(4096)
            if not chunk:
                raise IOError('连接已关闭')
            self._buf += chunk
        payload = self._buf[offset:offset + length]
        self._buf = self._buf[offset + length:]
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def send_frame(self, opcode: int, payload: bytes = b'') -> None:
        sock = self._require_sock()
        mask = os.urandom(4)
        n = len(payload)
        header = bytearray([0x80 | opcode])  # FIN=1
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack('>H', n)
        else:
            header.append(0x80 | 127)
            header += struct.pack('>Q', n)
        header += mask
        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        sock.sendall(bytes(header) + masked_payload)

    def close(self) -> None:
        try:
            self.send_frame(0x8, struct.pack('>H', 1000))
        except Exception:
            pass
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass


def ws_listen(ws: SimpleWS) -> None:
    """后台线程：循环收帧，text 帧记入 received；ping 回 pong。"""
    while True:
        try:
            opcode, payload = ws.recv_frame()
        except socket.timeout:
            continue
        except Exception as e:
            print(f'  [WS CLOSE] {e}')
            break
        if opcode == 0x1:  # text
            msg = payload.decode('utf-8', errors='replace')
            received.append(msg)
            print(f'  [WS 收到] {msg}')
        elif opcode == 0x9:  # ping → pong
            try:
                ws.send_frame(0xA, payload)
            except Exception:
                break
        elif opcode == 0x8:  # close
            print('  [WS CLOSE]')
            break


def http(method: str, path: str, payload=None, token=None):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception as e:  # 连接失败
        return 0, {'error': str(e)}


def build_abnormal_readings(eq: str, minutes: int = 60):
    """构造 minutes 分钟序列：前 minutes-1 分钟正常 + 最后 1 分钟异常"""
    now = datetime.now().replace(second=0, microsecond=0)
    readings = []
    for i in range(minutes):
        ts = (now - timedelta(minutes=minutes - 1 - i)).isoformat()
        if i < minutes - 1:
            # 正常工况：功率 ~27kW（45kW 的 60%），温度 125℃，振动 0.5，负载 0.6
            readings.append({
                'equipment_id': eq, 'timestamp': ts,
                'power': 27.0, 'temperature': 125.0, 'vibration': 0.5, 'load_rate': 0.6,
            })
        else:
            # 最后一条异常：超温 + 超载
            readings.append({
                'equipment_id': eq, 'timestamp': ts,
                'power': 80.0, 'temperature': 155.0, 'vibration': 2.5, 'load_rate': 1.3,
            })
    return readings


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description='告警中心弹窗推送链路测试')
    parser.add_argument('--base', default=BASE, help=f'后端地址，默认 {BASE}')
    parser.add_argument('--eq', default=TARGET_EQ, help='目标设备')
    parser.add_argument('--account', default='admin', help='登录账号')
    parser.add_argument('--password', default='Admin@123', help='登录密码')
    parser.add_argument('--wait', type=float, default=3.0, help='等待 WS 推送的秒数')
    parser.add_argument('--no-scan', action='store_true', help='只连 WS 收广播，不注入/不扫描')
    args = parser.parse_args()

    BASE = args.base.rstrip('/')
    ws_url = BASE.replace('http', 'ws', 1) + WS_PATH

    print('=' * 70)
    print('告警中心弹窗推送链路测试（模拟前端 WebSocket 订阅）')
    print(f'后端: {BASE}    WebSocket: {ws_url}')
    print('=' * 70)

    # 1. 建立 WebSocket 连接（模拟前端在线监听弹窗）
    ws = SimpleWS(ws_url)
    try:
        ws.connect()
        print('[1] WebSocket 已连接 /ws/alerts（前端在线）')
    except Exception as e:
        print(f'[1] [!] WebSocket 连接失败：{e}，请确认后端 8001 已启动')
        return 1
    threading.Thread(target=ws_listen, args=(ws,), daemon=True).start()

    if args.no_scan:
        print('    （--no-scan 模式：保持连接接收广播，按 Ctrl+C 退出）')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        ws.close()
        return 0

    # 2. 登录拿 token（/api/alarms/scan 需要鉴权）
    st, body = http('POST', '/api/auth/login',
                    {'account': args.account, 'password': args.password})
    token = (body or {}).get('access_token')
    if not token:
        print(f'[2] [FAIL] 登录失败: {body}')
        ws.close()
        return 1
    print(f'[2] 登录成功（{args.account}），拿到 access_token')

    # 3. 注入 60 分钟「前正常后异常」序列
    readings = build_abnormal_readings(args.eq)
    st, body = http('POST', '/api/ingest/batch', {'readings': readings, 'source': 'plc'})
    print(f'[3] 注入 {len(readings)} 条数据 → /api/ingest/batch  HTTP {st}  {body}')

    # 4. 触发一轮检测扫描（后端读 DB → 调算法 /anomaly/detect → 告警编排+推送）
    st, body = http('POST', '/api/alarms/scan', None, token=token)
    print(f'[4] 触发扫描 /api/alarms/scan  HTTP {st}  {body}')
    scanned = (body or {}).get('scanned')
    triggered = (body or {}).get('triggered')

    # 5. 等待 WS 推送到达
    time.sleep(args.wait)

    # 6. 汇总结果
    alarm_msgs = []
    for m in received:
        try:
            obj = json.loads(m)
        except Exception:
            obj = m  # 非 JSON 沿用原文
        if isinstance(obj, dict) and obj.get('type') == 'alarm':
            alarm_msgs.append(obj)

    print('=' * 70)
    print(f'本轮扫描：{scanned} 台设备，触发 {triggered} 条告警')
    print(f'WebSocket 实际收到告警弹窗消息：{len(alarm_msgs)} 条')
    for i, a in enumerate(alarm_msgs, 1):
        print(f'  [{i}] 设备={a.get("equipment_name")}({a.get("equipment_id")}) '
              f'严重度={a.get("severity_label")} 得分={a.get("anomaly_score")} '
              f'根因={a.get("root_cause")}')
    print('=' * 70)

    ok = len(alarm_msgs) > 0
    if ok:
        print('结论：✅ 弹窗链路打通（后端已实时推送告警，前端 alarmRealtime 会弹窗）')
    else:
        print('结论：❌ 未收到告警推送')
        if not triggered:
            print('  未触发告警，可能原因：')
            print('    1) 告警冷却中：该设备 10 分钟内已告警过 → 重启算法服务(8000)重置，或换 --eq')
            print('    2) 数据窗口不足：目标设备近期 <60 条数据（确认注入成功、时间戳正确）')
            print('    3) 算法服务未启动或 /anomaly/detect 不可用')
        else:
            print('  已触发告警但未收到 WS 推送：检查 WebSocket 连接是否在触发前建立、等待窗口是否过短')

    ws.close()
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())