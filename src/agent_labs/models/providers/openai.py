"""
OpenAI 模型提供商适配器
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from .base import BaseModelProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseModelProvider):
    """OpenAI API 适配"""

    def __init__(self, api_key: str, base_url: str | None = None):
        super().__init__(api_key, base_url)
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted = []
        for tool in tools:
            converted.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
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
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                params["tools"] = self._convert_tools(tools)

            response = await self._client.chat.completions.create(**params)
            choice = response.choices[0]
            msg = choice.message

            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": tc.function.arguments if isinstance(tc.function.arguments, dict)
                                else __import__("json").loads(tc.function.arguments),
                    })

            return {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": tool_calls,
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            }
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
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
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }
            if tools:
                params["tools"] = self._convert_tools(tools)

            stream = await self._client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield {"type": "text_delta", "content": delta.content}
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            yield {
                                "type": "tool_call_delta",
                                "id": tc.id,
                                "name": tc.function.name if tc.function else "",
                                "arguments": tc.function.arguments if tc.function else "",
                            }
                if chunk.usage:
                    yield {
                        "type": "usage",
                        "input_tokens": chunk.usage.prompt_tokens or 0,
                        "output_tokens": chunk.usage.completion_tokens or 0,
                    }
        except Exception as e:
            logger.error(f"OpenAI stream error: {e}")
            yield {"type": "error", "message": str(e)}

    async def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in messages:
            total += len(enc.encode(str(msg.get("content", ""))))
        return total
