"""
模型管理器

负责：
- 多平台模型统一管理
- 模型选择策略 (strong/weak tier)
- 模型权限检查
- Token 计数
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

from ..config.settings import Settings, get_settings
from ..core.types import Message, new_id
from .providers.anthropic import AnthropicProvider
from .providers.base import BaseModelProvider
from .providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

# 提供商工厂
PROVIDER_FACTORY: dict[str, type[BaseModelProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


class ModelManager:
    """
    多平台模型管理器

    使用方式：
        manager = ModelManager(settings)
        response = await manager.chat(messages=[...], model="claude-sonnet-4-6")
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._providers: dict[str, BaseModelProvider] = {}

    def _get_provider(self, provider_name: str) -> BaseModelProvider:
        """获取或初始化提供商实例"""
        if provider_name not in self._providers:
            provider_config = self.settings.models_config.get("providers", {}).get(provider_name, {})
            api_key_env = provider_config.get("api_key_env", "")
            api_key = os.getenv(api_key_env, "")

            if not api_key:
                logger.warning(f"API key not found for {provider_name} (env: {api_key_env})")

            base_url = provider_config.get("base_url")

            provider_cls = PROVIDER_FACTORY.get(provider_name)
            if not provider_cls:
                raise ValueError(f"Unknown provider: {provider_name}. Available: {list(PROVIDER_FACTORY)}")

            self._providers[provider_name] = provider_cls(
                api_key=api_key,
                base_url=base_url,
            )
        return self._providers[provider_name]

    def _resolve_model(self, model_id: str | None = None, tier: str | None = None) -> tuple[str, str]:
        """
        解析模型 ID

        Args:
            model_id: 显式指定模型 ID，如 "claude-sonnet-4-6"
            tier: 模型层级 "strong" | "weak"

        Returns:
            (provider_name, model_id)
        """
        providers = self.settings.models_config.get("providers", {})

        if model_id:
            # 从所有提供商中查找匹配的模型
            for pname, pconfig in providers.items():
                for model in pconfig.get("models", []):
                    if model["id"] == model_id:
                        return pname, model_id
            raise ValueError(f"Model not found: {model_id}")

        if tier:
            # 按层级选择默认模型（第一个匹配的）
            for pname, pconfig in providers.items():
                for model in pconfig.get("models", []):
                    if model.get("tier") == tier:
                        return pname, model["id"]

        # 回退到默认提供商和模型
        default_provider = self.settings.models_config.get("default_provider", "anthropic")
        default_model = providers.get(default_provider, {}).get("default_model", "claude-sonnet-4-6")
        return default_provider, default_model

    def get_model_for_agent(self, agent_type: str) -> tuple[str, str]:
        """
        根据 Agent 类型选择模型

        - orchestrator / supervisor → strong model
        - worker / executor → weak model

        Args:
            agent_type: Agent 类型标识

        Returns:
            (provider_name, model_id)
        """
        orchestrator_types = {"orchestrator", "supervisor", "planner"}
        if agent_type.lower() in orchestrator_types:
            tier = self.settings.models_config.get("selection", {}).get("orchestrator_tier", "strong")
        else:
            tier = self.settings.models_config.get("selection", {}).get("worker_tier", "weak")
        return self._resolve_model(tier=tier)

    async def chat(
        self,
        messages: list[Message] | list[dict[str, Any]],
        model: str | None = None,
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        通用聊天补全

        Args:
            messages: 消息列表 (Message 对象或 dict)
            model: 模型 ID，不指定则使用默认
            provider: 提供商，不指定则自动查找
            temperature: 温度参数
            max_tokens: 最大输出 token
            tools: 工具定义列表

        Returns:
            {"role": "assistant", "content": "...", "tool_calls": [...], "usage": {...}}
        """
        # 标准化消息格式
        normalized_messages = []
        for m in messages:
            if isinstance(m, Message):
                normalized_messages.append({
                    "role": m.role.value,
                    "content": m.content,
                })
            else:
                normalized_messages.append(m)

        # 解析提供商和模型
        if not provider:
            provider, model = self._resolve_model(model_id=model)
        elif not model:
            _, model = self._resolve_model(model_id=None)

        provider_instance = self._get_provider(provider)
        return await provider_instance.chat(
            messages=normalized_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

    async def chat_stream(
        self,
        messages: list[Message] | list[dict[str, Any]],
        model: str | None = None,
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式聊天补全"""
        normalized_messages = []
        for m in messages:
            if isinstance(m, Message):
                normalized_messages.append({"role": m.role.value, "content": m.content})
            else:
                normalized_messages.append(m)

        if not provider:
            provider, model = self._resolve_model(model_id=model)
        elif not model:
            _, model = self._resolve_model(model_id=None)

        provider_instance = self._get_provider(provider)
        async for chunk in provider_instance.chat_stream(
            messages=normalized_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        ):
            yield chunk

    async def count_tokens(self, messages: list[Message] | list[dict[str, Any]],
                           model: str | None = None) -> int:
        """计算消息的 token 数"""
        normalized = []
        for m in messages:
            if isinstance(m, Message):
                normalized.append({"role": m.role.value, "content": m.content})
            else:
                normalized.append(m)

        provider, model = self._resolve_model(model_id=model)
        provider_instance = self._get_provider(provider)
        return await provider_instance.count_tokens(normalized, model)

    def list_available_models(self) -> list[dict[str, Any]]:
        """列出所有可用模型"""
        models = []
        for pname, pconfig in self.settings.models_config.get("providers", {}).items():
            for model in pconfig.get("models", []):
                models.append({
                    "provider": pname,
                    "id": model["id"],
                    "display_name": model.get("display_name", model["id"]),
                    "tier": model.get("tier", "unknown"),
                    "max_tokens": model.get("max_tokens", 0),
                })
        return models

    def check_model_permission(self, model_id: str, user_roles: list[str]) -> bool:
        """
        检查用户是否有权限使用指定模型

        Args:
            model_id: 模型 ID
            user_roles: 用户角色列表

        Returns:
            是否有权限
        """
        # 简化实现：admin 可用所有，普通用户只能用 weak 模型
        if "admin" in user_roles:
            return True

        for pconfig in self.settings.models_config.get("providers", {}).values():
            for model in pconfig.get("models", []):
                if model["id"] == model_id and model.get("tier") == "strong":
                    return False
        return True
