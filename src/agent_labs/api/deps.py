"""
FastAPI 依赖注入

提供请求级别的服务实例。使用 lru_cache 确保全局单例。
"""

from __future__ import annotations

from functools import lru_cache

from ..agents.react_agent import ReactAgent
from ..config.settings import get_settings
from ..context.builder import ContextBuilder
from ..context.compressor import ContextCompressor
from ..context.knowledge import KnowledgeInjector
from ..human_loop.approval import ApprovalManager
from ..memory.manager import MemoryManager
from ..models.manager import ModelManager
from ..notifications.email import EmailConfig, EmailNotifier
from ..observability.monitor import TokenMonitor
from ..observability.tracer import Tracer
from ..security.timeout import TimeoutConfig, TimeoutManager
from ..sessions.manager import SessionManager
from ..skills.executor import SkillExecutor
from ..skills.permissions import SkillPermissionManager
from ..skills.registry import SkillRegistry
from ..tools.executor import ToolExecutor
from ..tools.permissions import ToolPermissionManager
from ..tools.registry import ToolRegistry

# ============================================================================
# 核心服务 (P0)
# ============================================================================


@lru_cache
def get_model_manager() -> ModelManager:
    """获取全局 ModelManager 单例"""
    return ModelManager()


@lru_cache
def get_session_manager() -> SessionManager:
    """获取全局 SessionManager 单例"""
    settings = get_settings()
    return SessionManager(ttl_seconds=settings.session.ttl_seconds)


@lru_cache
def get_memory_manager() -> MemoryManager:
    """获取全局 MemoryManager 单例"""
    return MemoryManager()


@lru_cache
def get_tool_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 单例"""
    return ToolRegistry()


@lru_cache
def get_tool_executor() -> ToolExecutor:
    """获取全局 ToolExecutor 单例"""
    registry = get_tool_registry()
    settings = get_settings()
    return ToolExecutor(
        registry,
        default_timeout=settings.security.tool_timeout_seconds,
    )


@lru_cache
def get_tool_permission_manager() -> ToolPermissionManager:
    """获取全局 ToolPermissionManager 单例"""
    settings = get_settings()
    mgr = ToolPermissionManager()
    mgr.load_from_config(settings.tools_config)
    return mgr


# ============================================================================
# 技能系统 (P0)
# ============================================================================


@lru_cache
def get_skill_registry() -> SkillRegistry:
    """获取全局 SkillRegistry 单例"""
    return SkillRegistry()


@lru_cache
def get_skill_executor() -> SkillExecutor:
    """获取全局 SkillExecutor 单例"""
    registry = get_skill_registry()
    tool_executor = get_tool_executor()
    return SkillExecutor(registry, tool_executor)


@lru_cache
def get_skill_permission_manager() -> SkillPermissionManager:
    """获取全局 SkillPermissionManager 单例"""
    tool_perm = get_tool_permission_manager()
    return SkillPermissionManager(tool_perm)


# ============================================================================
# 上下文工程 (P1)
# ============================================================================


@lru_cache
def get_context_builder() -> ContextBuilder:
    """获取全局 ContextBuilder 单例"""
    settings = get_settings()
    return ContextBuilder(max_tokens=settings.context.max_tokens)


@lru_cache
def get_context_compressor() -> ContextCompressor:
    """获取全局 ContextCompressor 单例"""
    settings = get_settings()
    return ContextCompressor(
        max_tokens=settings.context.max_tokens,
        threshold_messages=settings.context.compression_threshold,
    )


@lru_cache
def get_knowledge_injector() -> KnowledgeInjector:
    """获取全局 KnowledgeInjector 单例"""
    memory_mgr = get_memory_manager()
    return KnowledgeInjector(memory_manager=memory_mgr)


# ============================================================================
# 可观测性 (P2)
# ============================================================================


@lru_cache
def get_tracer() -> Tracer:
    """获取全局 Tracer 单例"""
    settings = get_settings()
    return Tracer(enabled=settings.observability.node_tracing)


@lru_cache
def get_token_monitor() -> TokenMonitor:
    """获取全局 TokenMonitor 单例"""
    settings = get_settings()
    return TokenMonitor(enabled=settings.observability.token_tracking)


# ============================================================================
# 人工确认 + 通知 (P2)
# ============================================================================


@lru_cache
def get_approval_manager() -> ApprovalManager:
    """获取全局 ApprovalManager 单例"""
    return ApprovalManager()


@lru_cache
def get_email_notifier() -> EmailNotifier:
    """获取全局 EmailNotifier 单例"""
    settings = get_settings()
    email_cfg = settings.notifications.email
    config = EmailConfig(
        enabled=email_cfg.enabled,
        smtp_host=email_cfg.smtp_host,
        smtp_port=email_cfg.smtp_port,
        smtp_user=email_cfg.smtp_user,
        smtp_password="",  # 从环境变量读取
        from_addr=email_cfg.smtp_user,
    )
    return EmailNotifier(config)


# ============================================================================
# 安全 (P2)
# ============================================================================


@lru_cache
def get_timeout_manager() -> TimeoutManager:
    """获取全局 TimeoutManager 单例"""
    settings = get_settings()
    config = TimeoutConfig(
        tool_timeout_seconds=settings.security.tool_timeout_seconds,
        task_timeout_seconds=settings.security.task_timeout_seconds,
    )
    return TimeoutManager(config)


# ============================================================================
# Agent 工厂
# ============================================================================


def get_react_agent() -> ReactAgent:
    """创建 ReactAgent 实例（注入所有全局服务）"""
    model_manager = get_model_manager()
    tool_executor = get_tool_executor()
    settings = get_settings()

    agent = ReactAgent(
        name="react-agent",
        model_manager=model_manager,
        tool_executor=tool_executor,
        max_iterations=settings.agent.max_iterations,
    )

    # 注入可观测性
    agent.tracer = get_tracer()
    agent.token_monitor = get_token_monitor()

    # 注入上下文工程
    agent.context_builder = get_context_builder()
    agent.context_compressor = get_context_compressor()
    agent.knowledge_injector = get_knowledge_injector()

    # 注入审批 + 通知
    agent.approval_manager = get_approval_manager()
    agent.email_notifier = get_email_notifier()

    # 注入超时管理
    agent.timeout_manager = get_timeout_manager()

    # 注入技能系统
    agent.skill_executor = get_skill_executor()

    return agent
