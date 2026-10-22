"""Windows 上 psycopg 异步驱动必须使用 SelectorEventLoop。

Python 3.14 起 asyncio policy（set_event_loop_policy）已弃用，应通过
uvicorn --loop / asyncio.run(loop_factory=...) / TestClient backend_options
显式传入工厂，而不是改全局 policy。
"""

from __future__ import annotations

import asyncio
import sys


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """给 uvicorn `loop=` 使用：无参可调用，返回事件循环实例。"""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
