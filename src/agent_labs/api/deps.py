"""
FastAPI 依赖注入

提供请求级别的服务实例。
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Request

from ..agents.react_agent import ReactAgent
from ..config.settings import Settings, get_settings
from ..memory.manager import MemoryManager
from ..models.manager import ModelManager
from ..sessions.manager import SessionManager
from ..tools.executor import ToolExecutor
from ..tools.registry import ToolRegistry


@lru_cache()
def get_model_manager() -> ModelManager:
    """获取全局 ModelManager 单例"""
    return ModelManager()


@lru_cache()
def get_session_manager() -> SessionManager:
    """获取全局 SessionManager 单例"""
    settings = get_settings()
    return SessionManager(ttl_seconds=settings.session.ttl_seconds)


@lru_cache()
def get_memory_manager() -> MemoryManager:
    """获取全局 MemoryManager 单例"""
    return MemoryManager()


@lru_cache()
def get_tool_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 单例"""
    return ToolRegistry()


@lru_cache()
def get_tool_executor() -> ToolExecutor:
    """获取全局 ToolExecutor 单例"""
    registry = get_tool_registry()
    return ToolExecutor(registry)


def get_react_agent() -> ReactAgent:
    """创建 ReactAgent 实例"""
    model_manager = get_model_manager()
    tool_executor = get_tool_executor()
    settings = get_settings()
    return ReactAgent(
        name="react-agent",
        model_manager=model_manager,
        tool_executor=tool_executor,
        max_iterations=settings.agent.max_iterations,
    )
