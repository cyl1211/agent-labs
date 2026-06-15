"""
工具执行器 - 负责工具调用的执行、重试、错误处理
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..core.types import ToolResult
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    工具执行器

    功能：
    - 执行工具调用
    - 失败重试（可配置次数和退避策略）
    - 执行超时控制
    - 权限检查

    使用方式：
        registry = ToolRegistry()
        registry.register(MyTool())
        executor = ToolExecutor(registry)
        result = await executor.execute("my_tool", arg1="value1")
    """

    def __init__(
        self,
        registry: ToolRegistry,
        default_timeout: float = 60.0,
        default_retries: int = 2,
    ):
        self.registry = registry
        self.default_timeout = default_timeout
        self.default_retries = default_retries

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """
        执行工具调用（带重试）

        Args:
            name: 工具名
            **kwargs: 工具参数

        Returns:
            ToolResult
        """
        tool = self.registry.get(name)
        if not tool:
            return ToolResult(
                success=False,
                content="",
                error=f"Tool not found: {name}. Available: {self.registry.list_tools()}",
            )

        retries = self.default_retries
        last_error: str | None = None

        for attempt in range(retries + 1):
            start = time.monotonic()
            try:
                # 执行 + 超时保护
                result = await asyncio.wait_for(
                    tool.execute(**kwargs),
                    timeout=self.default_timeout,
                )
                result.duration_ms = (time.monotonic() - start) * 1000
                return result

            except asyncio.TimeoutError:
                last_error = f"Tool '{name}' timed out after {self.default_timeout}s"
                logger.warning(f"[ToolExecutor] {last_error} (attempt {attempt + 1}/{retries + 1})")

            except Exception as e:
                last_error = f"Tool '{name}' failed: {e}"
                logger.error(f"[ToolExecutor] {last_error} (attempt {attempt + 1}/{retries + 1})")

            if attempt < retries:
                delay = 2 ** attempt  # 指数退避: 1s, 2s
                await asyncio.sleep(delay)

        return ToolResult(
            success=False,
            content="",
            error=last_error or "Unknown error",
            duration_ms=0,
        )

    async def execute_batch(
        self, calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        批量并行执行工具调用

        Args:
            calls: [{name: "tool_name", args: {...}}, ...]

        Returns:
            [{name, result: ToolResult, call_index}, ...]  保持顺序
        """
        tasks = []
        for call in calls:
            name = call.get("name", "")
            args = call.get("args", {})
            tasks.append(self.execute(name, **args))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: list[dict[str, Any]] = []
        for i, (call, result) in enumerate(zip(calls, results)):
            name = call.get("name", "unknown")
            if isinstance(result, Exception):
                output.append({
                    "index": i,
                    "name": name,
                    "result": ToolResult(success=False, content="", error=str(result)),
                })
            else:
                output.append({
                    "index": i,
                    "name": name,
                    "result": result,
                })

        return output

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取所有工具的 API 定义（供 LLM 使用）"""
        return [tool.to_dict() for tool in self.registry.get_all()]

    def list_tools(self) -> list[str]:
        """列出所有工具名"""
        return self.registry.list_tools()

    def check_permission(self, tool_name: str, user_roles: list[str]) -> bool:
        """
        检查用户是否有权限使用工具

        Args:
            tool_name: 工具名
            user_roles: 用户角色

        Returns:
            是否有权限
        """
        tool = self.registry.get(tool_name)
        if not tool:
            return False

        # 检查工具上的 permission_level 属性
        required = getattr(tool, "permission_level", "read")

        if required == "execute" and "admin" not in user_roles:
            return False
        if required == "write" and "admin" not in user_roles and "editor" not in user_roles:
            return False

        return True
