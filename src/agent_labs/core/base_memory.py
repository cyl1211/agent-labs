"""
Memory 抽象基类

Memory 管理 Agent 的长期知识：跨会话的事实、经验、模式。
与 Agent 和 Session 解耦 — Memory 只关心"存什么、怎么查"。

Memory 可以被任何 Agent 系统使用，只需实现此接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import MemoryEntry, MemoryQuery


class BaseMemory(ABC):
    """
    多层记忆管理器抽象

    四层记忆架构：
    1. working  — 当前会话的上下文缓存（快速读写）
    2. episodic — 历史对话的摘要（发生了什么）
    3. semantic — 长期知识和事实（是什么）
    4. procedural — 成功的执行模式和策略（怎么做）

    不做的事：
    - 不涉及 Agent 执行
    - 不涉及 Session 状态管理
    - 不涉及消息历史（那是 Session 的职责）
    """

    @abstractmethod
    async def write(self, entry: MemoryEntry) -> str:
        """
        写入一条记忆

        Args:
            entry: 记忆条目

        Returns:
            entry_id: 记忆 ID
        """
        ...

    @abstractmethod
    async def read(self, query: MemoryQuery) -> list[MemoryEntry]:
        """
        按条件读取记忆

        Args:
            query: 查询条件（层级、标签、重要性等）

        Returns:
            匹配的记忆列表
        """
        ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 5, layer: str | None = None) -> list[MemoryEntry]:
        """
        语义搜索记忆（基于 embedding 相似度）

        Args:
            query: 搜索文本
            top_k: 返回前 K 条
            layer: 限定记忆层级

        Returns:
            最相关的记忆列表
        """
        ...

    @abstractmethod
    async def update(self, entry_id: str, updates: dict) -> MemoryEntry | None:
        """
        更新记忆条目（如提升重要性、更新内容）

        Args:
            entry_id: 记忆 ID
            updates: 要更新的字段

        Returns:
            更新后的记忆，或 None
        """
        ...

    @abstractmethod
    async def forget(self, entry_id: str) -> bool:
        """
        删除一条记忆

        Args:
            entry_id: 记忆 ID

        Returns:
            是否删除成功
        """
        ...

    @abstractmethod
    async def collect_garbage(self) -> int:
        """
        垃圾回收：清理过期记忆、低重要性记忆

        回收策略：
        - 超过 TTL 的记忆直接删除
        - 低重要性的记忆在容量超限时优先删除
        - 长时间未访问的记忆降权

        Returns:
            清理的条目数
        """
        ...

    @abstractmethod
    async def summarize_episode(
        self, session_id: str, messages: list, importance: float = 0.5
    ) -> str:
        """
        将一个会话的消息历史总结为情景记忆

        Args:
            session_id: 会话 ID
            messages: 消息列表
            importance: 重要性评分

        Returns:
            新创建的记忆 ID
        """
        ...
