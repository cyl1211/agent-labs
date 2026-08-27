"""
FastAPI 应用工厂

创建和配置 FastAPI 应用实例。
路由、中间件、生命周期事件在此组装。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config.settings import get_settings
from .middleware.logging import LoggingMiddleware
from .routes.agents import router as agents_router
from .routes.approval import router as approval_router
from .routes.observability import router as observability_router
from .routes.sessions import router as sessions_router
from .routes.skills import router as skills_router
from .routes.tools import router as tools_router

logger = logging.getLogger(__name__)


def _init_builtin_tools() -> None:
    """注册所有内置工具并加载权限配置"""
    from ..tools.builtin import register_all_builtin_tools
    from .deps import get_tool_executor, get_tool_permission_manager, get_tool_registry

    registry = get_tool_registry()
    # 避免重复注册（全局单例跨测试共享）
    if len(registry) == 0:
        register_all_builtin_tools(registry)

    # 将权限管理器注入 ToolExecutor
    perm_mgr = get_tool_permission_manager()
    executor = get_tool_executor()
    executor.set_permission_manager(perm_mgr)

    logger.info(f"[Startup] 注册 {len(registry)} 个内置工具, 权限配置已加载")


def _init_builtin_skills() -> None:
    """注册所有内置技能并加载权限配置"""
    from ..skills.builtin import register_all_builtin_skills
    from .deps import (
        get_skill_permission_manager,
        get_skill_registry,
    )

    registry = get_skill_registry()
    # 避免重复注册（全局单例跨测试共享）
    if len(registry) == 0:
        register_all_builtin_skills(registry)

    # 注册技能权限
    skill_perm = get_skill_permission_manager()
    for skill in registry.get_all():
        skill_perm.register_skill(
            skill_name=skill.name,
            required_tools=skill.required_tools,
        )

    logger.info(f"[Startup] 注册 {len(registry)} 个内置技能, 技能权限已加载")


def _init_services() -> None:
    """预热所有全局服务单例"""
    from .deps import (
        get_approval_manager,
        get_context_builder,
        get_context_compressor,
        get_email_notifier,
        get_knowledge_injector,
        get_memory_manager,
        get_model_manager,
        get_session_manager,
        get_timeout_manager,
        get_token_monitor,
        get_tracer,
    )

    # 触发所有单例初始化
    get_model_manager()
    get_session_manager()
    get_memory_manager()
    get_context_builder()
    get_context_compressor()
    get_knowledge_injector()
    get_tracer()
    get_token_monitor()
    get_approval_manager()
    get_email_notifier()
    get_timeout_manager()

    logger.info("[Startup] 所有全局服务已预热")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    logger.info(f"Agent-Labs starting up ({settings.app.name} v{settings.app.version})...")

    try:
        _init_services()
        _init_builtin_tools()
        _init_builtin_skills()
        logger.info("[Startup] Agent-Labs 启动完成, 所有模块已就绪")
    except Exception as e:
        logger.error(f"[Startup] 初始化失败: {e}")
        raise

    yield

    logger.info("Agent-Labs shutting down...")


def create_app() -> FastAPI:
    """
    创建 FastAPI 应用实例

    返回：
        FastAPI: 配置好的应用实例
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description="A production-grade agent learning platform based on LangGraph",
        docs_url="/docs" if settings.app.debug else None,
        redoc_url="/redoc" if settings.app.debug else None,
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 日志中间件
    app.add_middleware(LoggingMiddleware)

    # 注册路由
    app.include_router(agents_router, prefix="/api/v1/agents", tags=["Agents"])
    app.include_router(sessions_router, prefix="/api/v1/sessions", tags=["Sessions"])
    app.include_router(tools_router, prefix="/api/v1/tools", tags=["Tools"])
    app.include_router(skills_router, prefix="/api/v1/skills", tags=["Skills"])
    app.include_router(observability_router, prefix="/api/v1/observability", tags=["Observability"])
    app.include_router(approval_router, prefix="/api/v1/approval", tags=["Approval"])

    # 健康检查
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.app.version}

    return app
