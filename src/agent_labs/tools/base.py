"""
工具基类与注册表
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.types import ToolResult


class BaseTool(ABC):
    """工具抽象基类"""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}  # JSON Schema

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        ...

    def to_openai_schema(self) -> dict[str, Any]:
        """转为 OpenAI 工具格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> dict[str, Any]:
        """转为 Anthropic 工具格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_dict(self) -> dict[str, Any]:
        """通用序列化"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
