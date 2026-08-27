"""
动态知识注入器

根据用户查询从记忆库中检索相关知识并注入到上下文。
支持多种知识来源：
- 语义记忆（事实、偏好）
- 程序记忆（成功模式）
- 情景记忆（相关历史对话）
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.types import (
    AgentContext,
    MemoryEntry,
    Message,
    Role,
)

logger = logging.getLogger(__name__)


class KnowledgeInjector:
    """动态知识注入器

    根据用户查询智能检索和注入相关知识。

    使用方式：
        injector = KnowledgeInjector(memory_manager)
        knowledge_messages = await injector.inject(query, context)
    """

    def __init__(
        self,
        memory_manager=None,
        max_knowledge_items: int = 8,
        min_relevance_score: float = 0.3,
    ):
        self._memory = memory_manager
        self.max_knowledge_items = max_knowledge_items
        self.min_relevance_score = min_relevance_score

    async def inject(self, query: str, context: AgentContext) -> list[Message]:
        """检索并注入相关知识

        检索策略：
        1. 语义记忆：查找与查询相关的事实和偏好
        2. 程序记忆：查找匹配的成功模式
        3. 情景记忆：查找相关历史对话
        4. 聚合所有知识，格式化为系统消息

        Args:
            query: 用户查询
            context: Agent 上下文

        Returns:
            包含注入知识的系统消息列表
        """
        if not self._memory or not query.strip():
            return []

        knowledge_items: list[KnowledgeItem] = []

        # 1. 语义知识检索
        semantic_matches = await self._retrieve_semantic(query)
        knowledge_items.extend(semantic_matches)

        # 2. 程序模式检索
        procedural_matches = await self._retrieve_procedural(query)
        knowledge_items.extend(procedural_matches)

        # 3. 情景记忆检索
        episodic_matches = await self._retrieve_episodic(query, context)
        knowledge_items.extend(episodic_matches)

        if not knowledge_items:
            return []

        # 按相关性排序
        knowledge_items.sort(key=lambda x: x.relevance, reverse=True)
        knowledge_items = knowledge_items[: self.max_knowledge_items]

        # 格式化为系统消息
        return self._format_knowledge_messages(knowledge_items)

    async def inject_targeted(
        self,
        query: str,
        context: AgentContext,
        layers: list[str] | None = None,
    ) -> list[Message]:
        """定向知识注入：只从指定层级检索

        Args:
            query: 用户查询
            context: Agent 上下文
            layers: 要检索的记忆层列表 (如 ["semantic", "procedural"])

        Returns:
            包含注入知识的系统消息列表
        """
        if not self._memory or not query.strip():
            return []

        layers = layers or ["semantic", "procedural"]
        knowledge_items: list[KnowledgeItem] = []

        for layer_name in layers:
            if layer_name == "semantic":
                knowledge_items.extend(await self._retrieve_semantic(query))
            elif layer_name == "procedural":
                knowledge_items.extend(await self._retrieve_procedural(query))
            elif layer_name == "episodic":
                knowledge_items.extend(await self._retrieve_episodic(query, context))
            elif layer_name == "working":
                knowledge_items.extend(await self._retrieve_working(query))

        knowledge_items.sort(key=lambda x: x.relevance, reverse=True)
        knowledge_items = knowledge_items[: self.max_knowledge_items]

        return self._format_knowledge_messages(knowledge_items)

    async def _retrieve_semantic(self, query: str) -> list[KnowledgeItem]:
        """检索语义记忆"""
        try:
            results = await self._memory.search(query, top_k=5, layer="semantic")
        except Exception:
            return []

        return [
            KnowledgeItem(
                content=entry.content,
                source="semantic",
                relevance=min(0.9, 0.5 + entry.importance * 0.5),
                entry=entry,
            )
            for entry in results
        ]

    async def _retrieve_procedural(self, query: str) -> list[KnowledgeItem]:
        """检索程序记忆"""
        try:
            results = await self._memory.search(query, top_k=3, layer="procedural")
        except Exception:
            return []

        return [
            KnowledgeItem(
                content=entry.content,
                source="procedural",
                relevance=min(0.9, 0.5 + entry.importance * 0.5),
                entry=entry,
            )
            for entry in results
        ]

    async def _retrieve_episodic(self, query: str, context: AgentContext) -> list[KnowledgeItem]:
        """检索情景记忆"""
        try:
            results = await self._memory.search(query, top_k=3, layer="episodic")
        except Exception:
            return []

        return [
            KnowledgeItem(
                content=entry.content,
                source="episodic",
                relevance=min(0.8, 0.4 + entry.importance * 0.4),
                entry=entry,
            )
            for entry in results
        ]

    async def _retrieve_working(self, query: str) -> list[KnowledgeItem]:
        """检索工作记忆"""
        try:
            results = await self._memory.search(query, top_k=5, layer="working")
        except Exception:
            return []

        return [
            KnowledgeItem(
                content=entry.content,
                source="working",
                relevance=min(1.0, 0.6 + entry.importance * 0.4),
                entry=entry,
            )
            for entry in results
        ]

    def _format_knowledge_messages(self, items: list[KnowledgeItem]) -> list[Message]:
        """格式化知识条目为系统消息"""
        if not items:
            return []

        sections: dict[str, list[KnowledgeItem]] = {}
        for item in items:
            sections.setdefault(item.source, []).append(item)

        source_labels = {
            "semantic": "🧠 Knowledge & Facts",
            "procedural": "🔧 Proven Patterns",
            "episodic": "📝 Related History",
            "working": "📋 Current Context",
        }

        lines = ["## Injected Knowledge"]
        lines.append("The following relevant knowledge was retrieved:\n")

        for source in ["working", "semantic", "procedural", "episodic"]:
            source_items = sections.get(source, [])
            if not source_items:
                continue
            label = source_labels.get(source, source)
            lines.append(f"### {label}")
            for item in source_items:
                lines.append(f"- [{item.relevance:.0%}] {item.content[:300]}")
            lines.append("")

        return [
            Message(
                role=Role.SYSTEM,
                content="\n".join(lines),
            )
        ]

    def set_memory_manager(self, manager) -> None:
        """设置记忆管理器"""
        self._memory = manager


class KnowledgeItem:
    """知识条目"""

    __slots__ = ("content", "source", "relevance", "entry")

    def __init__(
        self,
        content: str,
        source: str,
        relevance: float,
        entry: MemoryEntry | None = None,
    ):
        self.content = content
        self.source = source
        self.relevance = relevance
        self.entry = entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content[:200],
            "source": self.source,
            "relevance": self.relevance,
        }
