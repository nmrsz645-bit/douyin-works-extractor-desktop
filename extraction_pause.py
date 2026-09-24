"""跨线程控制作品提取，在安全检查点等待继续。"""

import asyncio
import threading


async def wait_if_paused(gate: threading.Event | None) -> None:
    """保留爬虫事件循环，等待用户继续当前提取任务。"""
    while gate is not None and not gate.is_set():
        await asyncio.sleep(0.05)
