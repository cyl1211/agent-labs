"""
Session 抽象基类

Session 管理 Agent 的运行时状态：消息历史、迭代计数、检查点等。
与 Agent 解耦 — Session 不知道 Agent 如何工作，Agent 不知道 Session 如何持久化。

Session 可以被任何 Agent 系统使用，只需实现此接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import Message, SessionConfig, SessionState


class BaseSession(ABC):
    """
    会话管理器抽象

    职责：
    - 创建/关闭会话
    - 读写会话运行时状态 (SessionState)
    - 管理消息历史（增删查）
    - 检查点管理（用于长时间任务的中断恢复）

    不做的事：
    - 不涉及 Agent 执行逻辑
    - 不涉及 Memory 持久化
    - 不涉及用户认证
    """

    @abstractmethod
    async def create(self, agent_id: str, config: SessionConfig | None = None) -> str:
        """
        创建新会话

        Args:
            agent_id: 要使用的 Agent 标识
            config: 会话配置

        Returns:
            session_id: 新会话 ID
        """
        ...

    @abstractmethod
    async def get_state(self, session_id: str) -> SessionState | None:
        """
        获取会话状态

        Args:
            session_id: 会话 ID

        Returns:
            SessionState 或 None（不存在时）
        """
        ...

    @abstractmethod
    async def update_state(self, session_id: str, state: SessionState) -> None:
        """
        更新会话状态（全量写入）

        Args:
            session_id: 会话 ID
            state: 新状态
        """
        ...

    @abstractmethod
    async def add_message(self, session_id: str, message: Message) -> None:
        """
        向会话追加一条消息

        Args:
            session_id: 会话 ID
            message: 消息对象
        """
        ...

    @abstractmethod
    async def get_history(
        self, session_id: str, limit: int = 50, before_message_id: str | None = None
    ) -> list[Message]:
        """
        获取会话消息历史

        Args:
            session_id: 会话 ID
            limit: 最大返回条数
            before_message_id: 获取此消息之前的消息（用于分页）

        Returns:
            消息列表（按时间正序）
        """
        ...

    @abstractmethod
    async def close(self, session_id: str) -> None:
        """
        关闭会话（标记为已完成或过期）

        Args:
            session_id: 会话 ID
        """
        ...

    @abstractmethod
    async def save_checkpoint(self, session_id: str, name: str, data: dict) -> None:
        """
        保存检查点（用于长任务恢复）

        Args:
            session_id: 会话 ID
            name: 检查点名称
            data: 检查点数据
        """
        ...

    @abstractmethod
    async def load_checkpoint(self, session_id: str, name: str) -> dict | None:
        """
        加载检查点

        Args:
            session_id: 会话 ID
            name: 检查点名称

        Returns:
            检查点数据或 None
        """
        ...

    @abstractmethod
    async def list_sessions(
        self, user_id: str | None = None, status: str | None = None
    ) -> list[str]:
        """
        列出会话 ID

        Args:
            user_id: 按用户过滤
            status: 按状态过滤

        Returns:
            会话 ID 列表
        """
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """
        清理过期会话

        Returns:
            清理的会话数量
        """
        ...
