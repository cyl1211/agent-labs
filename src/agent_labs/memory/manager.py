"""
记忆管理器实现

内置实现，基于嵌入向量 + 关键词的记忆存储。
实现 BaseMemory 接口，四层记忆架构。
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.base_memory import BaseMemory
from ..core.types import (
    MemoryEntry,
    MemoryLayer,
    MemoryQuery,
    new_id,
    utc_now,
)

logger = logging.getLogger(__name__)


class MemoryManager(BaseMemory):
    """
    内置记忆管理器

    四层记忆：
    1. working: 内存列表，快速读写，会话级
    2. episodic: 带嵌入的摘要存储，跨会话
    3. semantic: 长期事实/知识，高持久性
    4. procedural: 成功模式，高重要性

    存储策略：
    - working → 内存列表（快速）
    - 其他层 → ChromaDB 或其他向量数据库（Phase 3 实现）
    - 当前阶段使用内存结构，后续可无缝切换后端
    """

    def __init__(self):
        self._stores: dict[str, list[MemoryEntry]] = {
            "working": [],
            "episodic": [],
            "semantic": [],
            "procedural": [],
        }

    async def write(self, entry: MemoryEntry) -> str:
        """写入一条记忆"""
        if entry.layer.value not in self._stores:
            raise ValueError(f"Unknown memory layer: {entry.layer.value}")
        self._stores[entry.layer.value].append(entry)
        logger.debug(f"Memory written: [{entry.layer.value}] {entry.content[:100]}...")
        return entry.id

    async def read(self, query: MemoryQuery) -> list[MemoryEntry]:
        """按条件读取记忆"""
        results = []

        layers = [query.layer.value] if query.layer else list(self._stores.keys())
        for layer in layers:
            store = self._stores.get(layer, [])
            for entry in store:
                if query.min_importance and entry.importance < query.min_importance:
                    continue
                if query.tags and not any(t in entry.tags for t in query.tags):
                    continue
                results.append(entry)

        # 按重要性 + 最近访问时间排序
        results.sort(key=lambda e: (e.importance, e.last_accessed_at), reverse=True)
        return results[:query.limit]

    async def search(self, query: str, top_k: int = 5, layer: str | None = None) -> list[MemoryEntry]:
        """
        语义搜索 (当前使用简单关键词匹配，Phase 3 替换为向量搜索)
        """
        query_lower = query.lower()
        scored: list[tuple[float, MemoryEntry]] = []

        layers = [layer] if layer else list(self._stores.keys())
        for lname in layers:
            for entry in self._stores.get(lname, []):
                score = 0.0
                content_lower = entry.content.lower()
                # 简单关键词匹配
                for word in query_lower.split():
                    if word in content_lower:
                        score += 1.0
                # 标签匹配加分
                for tag in entry.tags:
                    if tag.lower() in query_lower:
                        score += 2.0
                if score > 0:
                    scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    async def update(self, entry_id: str, updates: dict) -> MemoryEntry | None:
        for store in self._stores.values():
            for i, entry in enumerate(store):
                if entry.id == entry_id:
                    # 使用新值创建更新后的条目
                    updated_data = entry.model_dump()
                    updated_data.update(updates)
                    updated_data["last_accessed_at"] = utc_now()
                    new_entry = MemoryEntry(**updated_data)
                    store[i] = new_entry
                    return new_entry
        return None

    async def forget(self, entry_id: str) -> bool:
        for store in self._stores.values():
            for i, entry in enumerate(store):
                if entry.id == entry_id:
                    store.pop(i)
                    return True
        return False

    async def collect_garbage(self) -> int:
        """垃圾回收"""
        removed = 0
        now = utc_now()

        for layer_name, store in list(self._stores.items()):
            kept = []
            for entry in store:
                # TTL 过期检查
                age = (now - entry.created_at).total_seconds()
                if age > entry.ttl_seconds:
                    removed += 1
                    continue
                # 低重要性 + 低访问量 清理
                if entry.importance < 0.2 and entry.access_count < 2:
                    age_days = age / 86400
                    if age_days > 7:  # 一周以上
                        removed += 1
                        continue
                kept.append(entry)
            self._stores[layer_name] = kept

        logger.info(f"Memory GC: removed {removed} entries")
        return removed

    async def summarize_episode(
        self, session_id: str, messages: list, importance: float = 0.5
    ) -> str:
        """将消息历史总结为情景记忆"""
        # 简单实现：拼接消息内容作为摘要
        # Phase 3 会用 LLM 生成更好的摘要
        summary_parts = []
        for msg in messages[-10:]:  # 取最近 10 条
            if hasattr(msg, "content"):
                summary_parts.append(msg.content[:100])
            elif isinstance(msg, dict):
                summary_parts.append(str(msg.get("content", ""))[:100])

        summary = " | ".join(summary_parts)
        entry = MemoryEntry(
            layer=MemoryLayer.EPISODIC,
            content=summary[:500],
            importance=importance,
            tags=[f"session:{session_id}"],
            ttl_seconds=86400 * 30,  # 30 天
        )
        return await self.write(entry)
