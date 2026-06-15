"""
Agent-Labs 核心类型定义

所有核心数据类型集中定义，确保 Agent、Session、Memory 之间的解耦。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# ID 类型
# ============================================================================

def new_id() -> str:
    """生成唯一 ID"""
    return uuid.uuid4().hex[:16]


def utc_now() -> datetime:
    """获取 UTC 时间"""
    return datetime.now(timezone.utc)


# ============================================================================
# 角色定义
# ============================================================================

class Role(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ============================================================================
# 消息类型
# ============================================================================

class Message(BaseModel):
    """对话消息"""
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=new_id)
    role: Role
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Agent 输入/输出
# ============================================================================

class AgentInput(BaseModel):
    """Agent 输入"""
    query: str
    session_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class AgentOutput(BaseModel):
    """Agent 输出"""
    session_id: str
    answer: str
    tool_calls_made: list[dict[str, Any]] = Field(default_factory=list)
    iterations: int = 0
    tokens_used: int = 0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    """Agent 流式事件"""
    event_type: Literal["thinking", "tool_call", "tool_result", "answer", "error", "human_approval"]
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=utc_now)


# ============================================================================
# Agent 上下文 (注入 Agent 的只读视图)
# ============================================================================

class AgentContext(BaseModel):
    """Agent 执行上下文 - 注入 session + memory 的只读视图"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    user_id: str | None = None
    messages: list[Message] = Field(default_factory=list)
    memories: list[MemoryEntry] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)


# ============================================================================
# Session 类型
# ============================================================================

class SessionStatus(str, Enum):
    """会话状态"""
    ACTIVE = "active"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    ERROR = "error"
    EXPIRED = "expired"


class SessionConfig(BaseModel):
    """会话配置"""
    agent_type: str = "react"
    model_id: str | None = None
    max_iterations: int = 25
    timeout_seconds: int = 300
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionState(BaseModel):
    """会话运行时状态"""
    session_id: str
    agent_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    messages: list[Message] = Field(default_factory=list)
    iterations: int = 0
    tool_calls_count: int = 0
    tokens_used: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    config: SessionConfig = Field(default_factory=SessionConfig)
    checkpoints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Memory 类型
# ============================================================================

class MemoryLayer(str, Enum):
    """记忆层级"""
    WORKING = "working"       # 当前会话上下文
    EPISODIC = "episodic"     # 历史对话摘要
    SEMANTIC = "semantic"     # 长期知识/事实
    PROCEDURAL = "procedural" # 成功模式/经验


class MemoryEntry(BaseModel):
    """记忆条目"""
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=new_id)
    layer: MemoryLayer
    content: str
    embedding: list[float] | None = None
    importance: float = 0.5  # 0-1, GC 时低重要性优先清理
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    last_accessed_at: datetime = Field(default_factory=utc_now)
    access_count: int = 0
    ttl_seconds: int = 86400  # 过期时间
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryQuery(BaseModel):
    """记忆查询"""
    layer: MemoryLayer | None = None
    tags: list[str] | None = None
    limit: int = 10
    min_importance: float = 0.0


# ============================================================================
# Tool 类型
# ============================================================================

class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    content: str
    error: str | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Skill 类型
# ============================================================================

class SkillContext(BaseModel):
    """技能执行上下文"""
    session_id: str
    agent_context: AgentContext | None = None
    tool_results: dict[str, ToolResult] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    """技能执行结果"""
    success: bool
    content: str
    error: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# 权限类型
# ============================================================================

class Permission(str, Enum):
    """操作权限"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


# ============================================================================
# 通知类型
# ============================================================================

class NotificationLevel(str, Enum):
    """通知级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    COMPLETION = "completion"


class NotificationEvent(BaseModel):
    """通知事件"""
    level: NotificationLevel
    title: str
    message: str
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
