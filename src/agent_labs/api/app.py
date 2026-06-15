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
from .routes.sessions import router as sessions_router
from .routes.tools import router as tools_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Agent-Labs starting up...")
    # 初始化全局服务
    from ..config.settings import get_settings
    settings = get_settings()
    logger.info(f"Config loaded: {settings.app.name} v{settings.app.version}")
    logger.info(f"Debug mode: {settings.app.debug}")

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

    # 健康检查
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.app.version}

    return app
