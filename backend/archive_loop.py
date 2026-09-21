"""
archive_loop —— 历史数据归档后台调度

按 config.ARCHIVE_CONFIG['archive_interval_hours'] 周期执行一轮归档。
归档为低频重活（降采样 + 删除），放线程池执行，避免阻塞事件循环。
生产环境亦可关闭本循环改用外部 cron / 定时任务，仅保留 POST /api/history/archive 手动触发。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from config.settings import ARCHIVE_CONFIG
from backend.archive_service import run_archive

logger = logging.getLogger(__name__)

_stop_event: Optional[asyncio.Event] = None
_task: Optional[asyncio.Task] = None


async def _loop(stop_event: asyncio.Event) -> None:
    interval_hours = ARCHIVE_CONFIG['archive_interval_hours']
    interval = interval_hours * 3600
    logger.info('归档调度循环启动：每 %d 小时执行一轮', interval_hours)
    while not stop_event.is_set():
        try:
            result = await asyncio.to_thread(run_archive)
            logger.info('归档完成：%s', result)
        except Exception as exc:  # noqa: BLE001 —— 归档失败不应中断调度
            logger.exception('归档循环异常: %s', exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def start() -> None:
    """启动后台归档调度（幂等）"""
    global _stop_event, _task
    if _task is not None:
        return
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_loop(_stop_event))


async def stop() -> None:
    """停止后台归档调度（优雅停机）"""
    global _stop_event, _task
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        _stop_event = None