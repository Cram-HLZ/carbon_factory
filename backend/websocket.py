"""
websocket —— WebSocket 实时推送模块

维护所有在线前端的 WebSocket 连接，异常检测触发告警后由
alarm_service 调用 manager.broadcast() 把告警实时推送给所有已连接前端。

【连接地址】 ws://localhost:8001/ws/alerts
【鉴权】    前端可携带 ?token=<jwt>（开发期前端已做登录页守卫，服务端宽松放行；
            生产环境可在 connect 前解析 token 做严格鉴权）
"""

from __future__ import annotations

import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器（广播式：告警推送给所有在线前端）"""

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._counter = 0

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        self._counter += 1
        conn_id = f'client-{self._counter}'
        self._connections[conn_id] = websocket
        logger.info('WebSocket 连接建立: %s（当前 %d 个在线）', conn_id, len(self._connections))
        return conn_id

    def disconnect(self, conn_id: str) -> None:
        self._connections.pop(conn_id, None)
        logger.info('WebSocket 连接断开: %s（当前 %d 个在线）', conn_id, len(self._connections))

    async def broadcast(self, message: dict) -> int:
        """向所有在线连接广播 JSON 消息，返回成功发送数量"""
        sent = 0
        dead = []
        for conn_id, ws in list(self._connections.items()):
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as exc:  # 连接已失效，标记后清理
                logger.warning('向 %s 推送失败: %s', conn_id, exc)
                dead.append(conn_id)
        for conn_id in dead:
            self.disconnect(conn_id)
        return sent

    @property
    def online_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@router.websocket('/ws/alerts')
async def ws_alerts(websocket: WebSocket):
    """告警实时推送通道：前端连接后，收到服务端广播的 {type:'alarm', ...} JSON"""
    conn_id = await manager.connect(websocket)
    try:
        while True:
            # 仅用于保活：前端发 'ping'，服务端回 'pong'
            data = await websocket.receive_text()
            if data == 'ping':
                await websocket.send_text('pong')
    except WebSocketDisconnect:
        manager.disconnect(conn_id)