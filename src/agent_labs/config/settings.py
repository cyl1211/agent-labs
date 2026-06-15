"""
配置数据类

所有配置通过 pydantic-settings 加载，支持：
- YAML 文件
- 环境变量覆盖 (前缀: AGENT_LABS_)
- .env 文件
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    name: str = "agent-labs"
    version: str = "0.1.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000


class AgentSettings(BaseModel):
    max_iterations: int = 25
    default_loop: str = "react"
    termination: dict[str, Any] = Field(default_factory=lambda: {
        "max_timeout_seconds": 300,
        "max_tool_calls": 15,
        "stop_phrases": ["TASK_COMPLETE", "FINAL_ANSWER"],
    })


class SessionSettings(BaseModel):
    ttl_seconds: int = 3600
    backend: str = "sqlite"
    max_concurrent: int = 100


class MemorySettings(BaseModel):
    working_max_messages: int = 50
    episodic_max_entries: int = 1000
    semantic_dimension: int = 1536
    gc_interval_seconds: int = 3600
    ttl_seconds: dict[str, int] = Field(default_factory=lambda: {
        "working": 3600,
        "episodic": 86400,
        "semantic": 604800,
    })


class ContextSettings(BaseModel):
    max_tokens: int = 100000
    compression_enabled: bool = True
    compression_threshold: int = 30


class SandboxSettings(BaseModel):
    mode: str = "process"
    docker_image: str = "python:3.11-slim"


class SecuritySettings(BaseModel):
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    tool_timeout_seconds: int = 60
    task_timeout_seconds: int = 36000


class EmailNotificationSettings(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password_env: str = "SMTP_PASSWORD"


class NotificationSettings(BaseModel):
    email: EmailNotificationSettings = Field(default_factory=EmailNotificationSettings)


class ObservabilitySettings(BaseModel):
    token_tracking: bool = True
    node_tracing: bool = True
    log_level: str = "INFO"


class Settings(BaseModel):
    """聚合所有配置"""
    app: AppSettings = Field(default_factory=AppSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    models_config: dict[str, Any] = Field(default_factory=dict)
    tools_config: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, config_dir: str | Path) -> "Settings":
        """从 YAML 配置目录加载所有配置"""
        config_dir = Path(config_dir)
        merged: dict[str, Any] = {}

        for file_name in ("default.yaml", "models.yaml", "tools.yaml"):
            file_path = config_dir / file_name
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                merged.update(data)

        # 分离 models 和 tools 配置
        models_config = merged.pop("models", {})
        # 如果 models.yaml 中的 providers/selection 在顶层（不在 models 键下），合并进来
        if "providers" in merged:
            models_config["providers"] = merged.pop("providers")
        if "selection" in merged:
            models_config["selection"] = merged.pop("selection")
        tools_config = merged.pop("tools", [])

        settings = cls(
            app=AppSettings(**merged.get("app", {})),
            agent=AgentSettings(**merged.get("agent", {})),
            session=SessionSettings(**merged.get("session", {})),
            memory=MemorySettings(**merged.get("memory", {})),
            context=ContextSettings(**merged.get("context", {})),
            security=SecuritySettings(**merged.get("security", {})),
            notifications=NotificationSettings(**merged.get("notifications", {})),
            observability=ObservabilitySettings(**merged.get("observability", {})),
            models_config=models_config,
            tools_config={"tools": tools_config, **merged.get("permission_levels", {})},
        )
        return settings


# 全局单例
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例"""
    global _settings
    if _settings is None:
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
        _settings = Settings.from_yaml(config_dir)
    return _settings


def set_settings(settings: Settings) -> None:
    """设置全局配置（用于测试）"""
    global _settings
    _settings = settings
