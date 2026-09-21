"""
notifier —— 多渠道告警推送

异常检测触发告警后，除 WebSocket 实时推送到前端外，还支持：
    1. 移动端推送（PushPlus / Server酱，消息直达个人微信）
    2. 邮件通知（SMTP）

所有渠道的**真实凭据不进入代码**，统一通过项目根目录 .env 提供
（见 .env.example）；未配置时对应渠道自动降级为日志记录。

设计要点：
    - 三个渠道相互独立，任一渠道失败不影响其它渠道与主流程
    - 推送均为 async，阻塞的网络 IO 通过 asyncio.to_thread 丢到线程池执行
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import urllib.parse
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from typing import Any, Dict

from backend.websocket import manager
from config.settings import MOBILE_PUSH_CONFIG, SMTP_CONFIG

logger = logging.getLogger(__name__)

_PUSHPLUS_URL = 'http://www.pushplus.plus/send'
_SERVERCHAN_URL = 'https://sctapi.ftqq.com/{key}.send'
_HTTP_TIMEOUT = 15.0


async def notify_web_socket(payload: Dict[str, Any]) -> int:
    """WebSocket 实时推送前端（广播给所有在线连接），返回送达连接数"""
    return await manager.broadcast(payload)


# ============================================================
# 移动端推送（PushPlus / Server酱 → 个人微信）
# ============================================================
def _build_mobile_text(payload: Dict[str, Any]) -> str:
    sev = payload.get('severity_label') or payload.get('severity') or '未知'
    return (
        f"设备：{payload.get('equipment_name')}（{payload.get('equipment_id')}）\n"
        f"告警级别：{sev}\n"
        f"异常得分：{payload.get('anomaly_score')}\n"
        f"根因：{payload.get('root_cause')}\n"
        f"时间：{payload.get('alarm_time')}\n"
    )


async def notify_mobile(payload: Dict[str, Any]) -> None:
    """
    移动端推送：PushPlus 或 Server酱（按 PUSH_TYPE 选择），消息直达个人微信。
    未配置对应 token/key 时降级为日志记录。
    """
    ptype = (MOBILE_PUSH_CONFIG.get('type') or '').lower()
    sev = payload.get('severity_label') or payload.get('severity') or ''
    title = f'【碳排告警】{payload.get("equipment_name")} {sev}级'.strip()
    text = _build_mobile_text(payload)

    try:
        if ptype == 'serverchan':
            key = MOBILE_PUSH_CONFIG.get('serverchan_key')
            if not key:
                logger.info('[移动端推送]（未配置 SERVERCHAN_KEY，仅记录）%s', title)
                return
            await asyncio.to_thread(_post_serverchan, key, title, text)
        else:
            token = MOBILE_PUSH_CONFIG.get('pushplus_token')
            if not token:
                logger.info('[移动端推送]（未配置 PUSHPLUS_TOKEN，仅记录）%s', title)
                return
            await asyncio.to_thread(_post_pushplus, token, title, text)
        logger.info('[移动端推送] 已发送 %s', title)
    except Exception as exc:
        logger.warning('[移动端推送] 发送失败: %s', exc)


def _post_pushplus(token: str, title: str, content: str) -> None:
    """调用 PushPlus HTTP 接口推送消息到个人微信"""
    body = json.dumps({
        'token': token,
        'title': title,
        'content': content,
        'template': 'txt',
    }).encode('utf-8')
    req = urllib.request.Request(
        _PUSHPLUS_URL, data=body,
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    if result.get('code') != 200:
        raise RuntimeError(f'PushPlus 返回非成功码: {result}')


def _post_serverchan(key: str, title: str, content: str) -> None:
    """调用 Server酱 HTTP 接口推送消息到个人微信"""
    url = _SERVERCHAN_URL.format(key=urllib.parse.quote(key))
    data = urllib.parse.urlencode({'title': title, 'desp': content}).encode('utf-8')
    req = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST',
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    if result.get('code') != 0:
        raise RuntimeError(f'Server酱返回非成功码: {result}')


# ============================================================
# 邮件推送（SMTP）
# ============================================================
async def notify_email(payload: Dict[str, Any]) -> None:
    """邮件通知：读取 SMTP_CONFIG 发送告警邮件；未配置时降级为日志记录"""
    host = SMTP_CONFIG.get('host')
    if not host or not SMTP_CONFIG.get('to_addrs'):
        logger.info(
            '[邮件推送]（未配置 SMTP，仅记录）设备 %s %s 级告警，ID=%s',
            payload.get('equipment_id'),
            payload.get('severity_label', payload.get('severity')),
            payload.get('id'),
        )
        return

    subject = (
        f'[碳排监测告警] {payload.get("equipment_name")}'
        f'（{payload.get("equipment_id")}）{payload.get("severity_label", payload.get("severity"))}级告警'
    )
    body = (
        f'设备：{payload.get("equipment_name")}（{payload.get("equipment_id")}）\n'
        f'告警级别：{payload.get("severity_label", payload.get("severity"))}\n'
        f'异常得分：{payload.get("anomaly_score")}\n'
        f'阈值：{payload.get("threshold")}\n'
        f'根因：{payload.get("root_cause")}\n'
        f'时间：{payload.get("alarm_time")}\n'
    )
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = SMTP_CONFIG.get('from_addr') or SMTP_CONFIG.get('user') or ''
    msg['To'] = SMTP_CONFIG.get('to_addrs', '')

    try:
        await asyncio.to_thread(_send_smtp, msg)
    except Exception as exc:
        logger.warning('[邮件推送] 发送失败: %s', exc)


def _send_smtp(msg: MIMEText) -> None:
    """阻塞式 SMTP 发送（由 asyncio.to_thread 在线程池中执行）"""
    host = SMTP_CONFIG.get('host')
    port = SMTP_CONFIG.get('port', 465)
    user = SMTP_CONFIG.get('user')
    password = SMTP_CONFIG.get('password')
    to_addrs = [a.strip() for a in SMTP_CONFIG.get('to_addrs', '').split(',') if a.strip()]
    if not to_addrs:
        return

    if SMTP_CONFIG.get('use_ssl', True):
        with smtplib.SMTP_SSL(host, port, timeout=_HTTP_TIMEOUT) as smtp:
            if user:
                smtp.login(user, password or '')
            smtp.sendmail(msg['From'], to_addrs, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=_HTTP_TIMEOUT) as smtp:
            smtp.starttls()
            if user:
                smtp.login(user, password or '')
            smtp.sendmail(msg['From'], to_addrs, msg.as_string())