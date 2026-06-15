"""
模型提供商抽象基类
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class BaseModelProvider(ABC):
    """模型提供商接口"""

    def __init__(self, api_key: str, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """同步聊天补全"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式聊天补全"""
        ...

    @abstractmethod
    async def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        """计算 token 数"""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供商名称"""
        ...
