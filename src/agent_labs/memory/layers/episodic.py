"""
情景记忆层 (Episodic Memory)

跨会话的历史对话摘要。
- 记录"发生了什么"
- 按会话聚合、按重要性排序
- 中等 TTL (默认 30 天)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ...core.types import MemoryEntry, MemoryQuery, utc_now

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """情景记忆 — 历史对话摘要

    特性:
    - 按会话分组存储
    - 支持时间衰减（旧记忆重要性自动降低）
    - 容量限制 + 重要性排序淘汰
    """

    def __init__(self, max_entries: int = 1000, default_ttl_seconds: int = 86400 * 30):
        self.max_entries = max_entries
        self.default_ttl_seconds = default_ttl_seconds
        self._entries: dict[str, MemoryEntry] = {}
        # 按会话分组的索引
        self._session_index: dict[str, list[str]] = {}

    def write(self, entry: MemoryEntry) -> str:
        """写入情景记忆"""
        entry_id = entry.id
        self._entries[entry_id] = entry

        # 更新会话索引
        for tag in entry.tags:
            if tag.startswith("session:"):
                session_id = tag.split(":", 1)[1]
                if session_id not in self._session_index:
                    self._session_index[session_id] = []
                self._session_index[session_id].append(entry_id)

        # 容量管理
        if len(self._entries) > self.max_entries:
            self._evict_lowest_importance()

        logger.debug(f"[EpisodicMemory] 写入: {entry.content[:80]}... (共 {len(self._entries)} 条)")
        return entry_id

    def read(self, query: MemoryQuery) -> list[MemoryEntry]:
        """读取情景记忆"""
        results = []
        for entry in self._entries.values():
            if query.min_importance and entry.importance < query.min_importance:
                continue
            if query.tags and not any(t in entry.tags for t in query.tags):
                continue
            results.append(entry)

        results.sort(key=lambda e: (e.importance, e.last_accessed_at), reverse=True)
        return results[: query.limit]

    def search(self, query_str: str, top_k: int = 5) -> list[MemoryEntry]:
        """关键词搜索情景记忆"""
        query_lower = query_str.lower()
        scored = []
        for entry in self._entries.values():
            score = 0.0
            content_lower = entry.content.lower()
            for word in query_lower.split():
                if word in content_lower:
                    score += 1.0
            for tag in entry.tags:
                if tag.lower() in query_lower:
                    score += 2.0
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def get_by_session(self, session_id: str) -> list[MemoryEntry]:
        """获取指定会话的所有情景记忆"""
        entry_ids = self._session_index.get(session_id, [])
        return [self._entries[eid] for eid in entry_ids if eid in self._entries]

    def summarize_session(
        self, session_id: str, messages: list[Any], importance: float = 0.5
    ) -> str:
        """将消息历史总结为一条情景记忆"""
        summary_parts = []
        for msg in messages[-20:]:  # 最近 20 条
            if hasattr(msg, "content"):
                content = str(msg.content)[:200]
            elif isinstance(msg, dict):
                content = str(msg.get("content", ""))[:200]
            else:
                content = str(msg)[:200]
            if content.strip():
                summary_parts.append(content.strip())

        summary = " | ".join(summary_parts)
        entry = MemoryEntry(
            layer="episodic",
            content=summary[:1000],
            importance=importance,
            tags=[f"session:{session_id}"],
            ttl_seconds=self.default_ttl_seconds,
        )
        return self.write(entry)

    def apply_time_decay(self) -> int:
        """应用时间衰减：降低旧记忆的重要性"""
        now = utc_now()
        decayed = 0
        for entry in self._entries.values():
            age_days = (now - entry.created_at).total_seconds() / 86400
            if age_days > 7:  # 超过 7 天开始衰减
                decay_factor = max(0.3, 1.0 - (age_days - 7) * 0.01)
                old_importance = entry.importance
                # 创建新条目（原条目是 frozen 的）
                new_data = entry.model_dump()
                new_data["importance"] = round(old_importance * decay_factor, 3)
                new_data["last_accessed_at"] = now
                self._entries[entry.id] = MemoryEntry(**new_data)
                if old_importance != new_data["importance"]:
                    decayed += 1

        if decayed:
            logger.debug(f"[EpisodicMemory] 时间衰减: {decayed} 条")
        return decayed

    def forget(self, entry_id: str) -> bool:
        """删除一条情景记忆"""
        if entry_id in self._entries:
            self._entries.pop(entry_id)
            # 清理会话索引
            for ids in self._session_index.values():
                if entry_id in ids:
                    ids.remove(entry_id)
            return True
        return False

    def collect_garbage(self, now: datetime | None = None) -> int:
        """垃圾回收：清理过期 + 低重要性条目"""
        now = now or utc_now()
        removed = 0

        # 先应用时间衰减
        self.apply_time_decay()

        expired_ids = []
        for eid, entry in self._entries.items():
            age = (now - entry.created_at).total_seconds()
            if age > entry.ttl_seconds:
                expired_ids.append(eid)
                continue
            # 低重要性 + 低访问：超过 7 天清理
            if entry.importance < 0.3 and entry.access_count < 2:
                age_days = age / 86400
                if age_days > 7:
                    expired_ids.append(eid)

        for eid in expired_ids:
            self.forget(eid)
            removed += 1

        if removed:
            logger.debug(f"[EpisodicMemory] GC: 移除 {removed} 条")
        return removed

    def _evict_lowest_importance(self) -> None:
        """淘汰重要性最低的条目"""
        if not self._entries:
            return
        # 找到重要性最低的
        lowest = min(self._entries.values(), key=lambda e: e.importance)
        self.forget(lowest.id)
        logger.debug(
            f"[EpisodicMemory] 淘汰: {lowest.content[:50]}... (importance={lowest.importance})"
        )

    def __len__(self) -> int:
        return len(self._entries)
