"""
超时管理器

统一管理各类操作的超时：
- 工具执行超时
- Agent 任务超时
- 请求级别超时
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TimeoutConfig:
    """超时配置"""

    tool_timeout_seconds: int = 60
    task_timeout_seconds: int = 36000  # 10 小时
    node_timeout_seconds: int = 120
    llm_timeout_seconds: int = 90
    request_timeout_seconds: int = 300


class TimeoutManager:
    """超时管理器

    使用方式：
        manager = TimeoutManager()
        async with manager.with_timeout("tool", 30):
            result = await some_tool.execute()
    """

    def __init__(self, config: TimeoutConfig | None = None):
        self.config = config or TimeoutConfig()
        self._active_timeouts: dict[str, float] = {}
        self._timeout_events: list[dict[str, Any]] = []
        self._max_events = 100

    @asynccontextmanager
    async def with_timeout(
        self,
        name: str,
        timeout_seconds: float | None = None,
        fallback: Any = None,
    ) -> AsyncIterator[None]:
        """异步上下文管理器：为操作添加超时

        Args:
            name: 操作名称（用于日志）
            timeout_seconds: 超时时间
            fallback: 超时后的回退值

        Yields:
            None (正常执行) 或 fallback (超时后)

        Raises:
            asyncio.TimeoutError: 如果没有 fallback 且超时
        """
        timeout = timeout_seconds or self.config.tool_timeout_seconds
        start = time.monotonic()

        try:
            yield
        except TimeoutError:
            duration = time.monotonic() - start
            self._record_timeout(name, timeout, duration)
            logger.warning(f"[Timeout] '{name}' 超时 ({timeout}s)")

            if fallback is not None:
                # 不能在这里 yield fallback，因为这个上下文管理器已经 yielding
                pass
            raise

        duration = time.monotonic() - start
        if duration > timeout * 0.8:
            logger.debug(f"[Timeout] '{name}' 接近超时: {duration:.1f}s / {timeout}s")

    def wrap_coroutine(
        self,
        coro,
        name: str = "unknown",
        timeout_seconds: float | None = None,
    ):
        """包装一个协程，添加超时

        Args:
            coro: 协程对象
            name: 操作名称
            timeout_seconds: 超时时间

        Returns:
            包装后的协程
        """
        timeout = timeout_seconds or self.config.tool_timeout_seconds
        return asyncio.wait_for(coro, timeout=timeout)

    async def run_with_timeout(
        self,
        coro,
        name: str = "unknown",
        timeout_seconds: float | None = None,
        on_timeout=None,
    ) -> Any:
        """运行协程并处理超时

        Args:
            coro: 协程
            name: 操作名
            timeout_seconds: 超时时间
            on_timeout: 超时回调

        Returns:
            协程结果，或超时后的回退值
        """
        timeout = timeout_seconds or self.config.tool_timeout_seconds
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except TimeoutError:
            duration = time.monotonic() - start
            self._record_timeout(name, timeout, duration)
            logger.error(f"[Timeout] '{name}' 超时 ({timeout}s)")

            if on_timeout:
                return on_timeout()
            raise

    def get_tool_timeout(self, tool_name: str) -> float:
        """获取工具超时时间

        不同工具有不同的默认超时：
        - execute_command: 120s
        - web_search: 30s
        - read_file: 30s
        - write_file: 30s
        """
        tool_timeouts = {
            "execute_command": 120.0,
            "web_search": 30.0,
            "web_fetch": 30.0,
            "read_file": 30.0,
            "write_file": 30.0,
            "list_directory": 15.0,
        }
        return tool_timeouts.get(tool_name, self.config.tool_timeout_seconds)

    def _record_timeout(self, name: str, timeout: float, duration: float) -> None:
        self._timeout_events.append(
            {
                "name": name,
                "timeout_setting": timeout,
                "actual_duration": duration,
                "timestamp": time.monotonic(),
            }
        )
        if len(self._timeout_events) > self._max_events:
            self._timeout_events = self._timeout_events[-self._max_events :]

    def get_timeout_stats(self) -> dict[str, Any]:
        """获取超时统计"""
        if not self._timeout_events:
            return {"total_timeouts": 0}

        return {
            "total_timeouts": len(self._timeout_events),
            "recent": [
                {"name": e["name"], "timeout": e["timeout_setting"]}
                for e in self._timeout_events[-5:]
            ],
        }
