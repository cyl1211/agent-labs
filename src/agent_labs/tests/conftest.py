"""
Pytest 配置和共享 fixtures
"""

from __future__ import annotations

import pytest

from agent_labs.config.settings import Settings, set_settings
from agent_labs.memory.manager import MemoryManager
from agent_labs.models.manager import ModelManager
from agent_labs.sessions.manager import SessionManager
from agent_labs.tools.executor import ToolExecutor
from agent_labs.tools.registry import ToolRegistry


@pytest.fixture
def settings() -> Settings:
    """测试用配置"""
    s = Settings()
    set_settings(s)
    return s


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """空工具注册表"""
    return ToolRegistry()


@pytest.fixture
def tool_executor(tool_registry: ToolRegistry) -> ToolExecutor:
    """工具执行器"""
    return ToolExecutor(tool_registry)


@pytest.fixture
def session_manager() -> SessionManager:
    """会话管理器"""
    return SessionManager(ttl_seconds=60)


@pytest.fixture
def memory_manager() -> MemoryManager:
    """记忆管理器"""
    return MemoryManager()


@pytest.fixture
def model_manager(settings: Settings) -> ModelManager:
    """模型管理器"""
    return ModelManager(settings)
