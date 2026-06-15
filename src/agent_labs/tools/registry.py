"""
工具注册表 - 管理所有工具的生命周期
"""

from __future__ import annotations

from typing import Any

from .base import BaseTool


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具"""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销一个工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool | None:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """列出所有工具名"""
        return list(self._tools.keys())

    def get_all(self) -> list[BaseTool]:
        """获取所有工具实例"""
        return list(self._tools.values())

    def clear(self) -> None:
        """清空注册表"""
        self._tools.clear()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
