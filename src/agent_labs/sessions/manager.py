"""
会话管理器实现

内置实现，使用内存 + SQLite 存储会话状态。
实现 BaseSession 接口，可被替换为其他存储后端。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..core.base_session import BaseSession
from ..core.types import (
    Message,
    SessionConfig,
    SessionState,
    SessionStatus,
    new_id,
    utc_now,
)

logger = logging.getLogger(__name__)


class SessionManager(BaseSession):
    """
    内置会话管理器

    存储策略：
    - 活跃会话驻留在内存字典中
    - SQLite 持久化历史数据（可选，Phase 3 实现）
    """

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionState] = {}
        self._checkpoints: dict[str, dict[str, dict]] = {}  # session_id -> {name: data}

    async def create(
        self, agent_id: str, config: SessionConfig | None = None
    ) -> str:
        config = config or SessionConfig()
        session_id = new_id()
        state = SessionState(
            session_id=session_id,
            agent_id=agent_id,
            config=config,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._sessions[session_id] = state
        self._checkpoints[session_id] = {}
        logger.info(f"Session created: {session_id} (agent={agent_id})")
        return session_id

    async def get_state(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    async def update_state(self, session_id: str, state: SessionState) -> None:
        state.updated_at = utc_now()
        self._sessions[session_id] = state

    async def add_message(self, session_id: str, message: Message) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.messages.append(message)
            session.updated_at = utc_now()

    async def get_history(
        self, session_id: str, limit: int = 50, before_message_id: str | None = None
    ) -> list[Message]:
        session = self._sessions.get(session_id)
        if not session:
            return []

        messages = session.messages
        if before_message_id:
            messages = [
                m for m in messages
                if m.id < before_message_id  # 按 ID 字典序过滤
            ]

        return messages[-limit:]

    async def close(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.status = SessionStatus.COMPLETED
            session.updated_at = utc_now()
            logger.info(f"Session closed: {session_id}")

    async def save_checkpoint(self, session_id: str, name: str, data: dict) -> None:
        if session_id not in self._checkpoints:
            self._checkpoints[session_id] = {}
        self._checkpoints[session_id][name] = {
            **data,
            "saved_at": utc_now().isoformat(),
        }

    async def load_checkpoint(self, session_id: str, name: str) -> dict | None:
        return self._checkpoints.get(session_id, {}).get(name)

    async def list_sessions(
        self, user_id: str | None = None, status: str | None = None
    ) -> list[str]:
        result = []
        for sid, state in self._sessions.items():
            if status and state.status.value != status:
                continue
            result.append(sid)
        return result

    async def cleanup_expired(self) -> int:
        """清理过期会话"""
        now = utc_now()
        expired = []
        for sid, state in self._sessions.items():
            age = (now - state.updated_at).total_seconds()
            if age > self.ttl_seconds:
                expired.append(sid)

        for sid in expired:
            self._sessions.pop(sid, None)
            self._checkpoints.pop(sid, None)

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
        return len(expired)
