"""
Anthropic (Claude) 模型提供商适配器
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from .base import BaseModelProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseModelProvider):
    """Anthropic Claude API 适配"""

    def __init__(self, api_key: str, base_url: str | None = None):
        super().__init__(api_key, base_url)
        self._client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将通用消息格式转换为 Anthropic 格式"""
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                converted.append({"role": "user", "content": f"<system>{content}</system>"})
            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": f"<tool_result name=\"{msg.get('tool_name', '')}\">{content}</tool_result>",
                })
            elif role == "assistant" and msg.get("tool_calls"):
                tool_blocks = []
                for tc in msg["tool_calls"]:
                    tool_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "input": tc.get("args", {}),
                    })
                converted.append({"role": "assistant", "content": tool_blocks})
            else:
                converted.append({"role": role, "content": content})
        return converted

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将通用工具格式转换为 Anthropic 格式"""
        converted = []
        for tool in tools:
            converted.append({
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {}),
            })
        return converted

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        try:
            params: dict[str, Any] = {
                "model": model,
                "messages": self._convert_messages(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                params["tools"] = self._convert_tools(tools)

            response = await self._client.messages.create(**params)

            content_blocks = response.content
            text_parts = []
            tool_calls = []

            for block in content_blocks:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "args": block.input,
                    })

            return {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else "",
                "tool_calls": tool_calls,
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                },
            }
        except Exception as e:
            logger.error(f"Anthropic chat error: {e}")
            raise

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            params: dict[str, Any] = {
                "model": model,
                "messages": self._convert_messages(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                params["tools"] = self._convert_tools(tools)

            async with self._client.messages.stream(**params) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        yield {
                            "type": "text_delta",
                            "content": event.delta.text if event.delta else "",
                        }
                    elif event.type == "content_block_start":
                        if event.content_block and event.content_block.type == "tool_use":
                            yield {
                                "type": "tool_call_start",
                                "name": event.content_block.name,
                                "id": event.content_block.id,
                            }
                    elif event.type == "message_delta":
                        if event.usage:
                            yield {
                                "type": "usage",
                                "input_tokens": event.usage.input_tokens or 0,
                                "output_tokens": event.usage.output_tokens or 0,
                            }
        except Exception as e:
            logger.error(f"Anthropic stream error: {e}")
            yield {"type": "error", "message": str(e)}

    async def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        try:
            response = await self._client.messages.count_tokens(
                model=model,
                messages=self._convert_messages(messages),
            )
            return response.input_tokens
        except Exception:
            # 粗略估算：1 token ≈ 3-4 个字符
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            return total_chars // 3
