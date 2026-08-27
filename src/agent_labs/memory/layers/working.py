"""
工作记忆层 (Working Memory)

当前会话的上下文缓存，最快速读写。
- 容量限制 (默认 50 条消息)
- 最短 TTL (默认 1 小时)
- 仅内存存储，不持久化
"""

from __future__ import annotations

import contextlib
import logging
from collections import deque
from datetime import datetime

from ...core.types import MemoryEntry, MemoryQuery, utc_now

logger = logging.getLogger(__name__)


class WorkingMemory:
    """工作记忆 — 当前会话的短期上下文

    特性:
    - 固定容量队列（FIFO，超出时自动淘汰最旧条目）
    - 极快读写（纯内存操作）
    - 会话结束即过期
    """

    def __init__(self, max_entries: int = 50, default_ttl_seconds: int = 3600):
        self.max_entries = max_entries
        self.default_ttl_seconds = default_ttl_seconds
        self._entries: dict[str, MemoryEntry] = {}
        self._order: deque[str] = deque()  # 维护插入顺序

    def write(self, entry: MemoryEntry) -> str:
        """写入工作记忆

        超出容量时自动淘汰最旧的条目。
        """
        entry_id = entry.id

        # 容量管理：FIFO 淘汰
        while len(self._entries) >= self.max_entries and self._order:
            oldest_id = self._order.popleft()
            removed = self._entries.pop(oldest_id, None)
            if removed:
                logger.debug(f"[WorkingMemory] 容量满，淘汰: {removed.content[:50]}...")

        self._entries[entry_id] = entry
        self._order.append(entry_id)
        logger.debug(f"[WorkingMemory] 写入: {entry.content[:80]}... (共 {len(self._entries)} 条)")
        return entry_id

    def read(self, query: MemoryQuery) -> list[MemoryEntry]:
        """读取工作记忆"""
        results = []
        for entry in self._entries.values():
            if query.min_importance and entry.importance < query.min_importance:
                continue
            if query.tags and not any(t in entry.tags for t in query.tags):
                continue
            results.append(entry)

        results.sort(key=lambda e: (e.importance, e.created_at), reverse=True)
        return results[: query.limit]

    def search(self, query_str: str, top_k: int = 5) -> list[MemoryEntry]:
        """关键词搜索工作记忆"""
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

    def get_all(self) -> list[MemoryEntry]:
        """获取所有工作记忆（按插入顺序）"""
        return [self._entries[eid] for eid in self._order if eid in self._entries]

    def get_recent(self, n: int = 10) -> list[MemoryEntry]:
        """获取最近 N 条工作记忆"""
        recent_ids = list(self._order)[-n:]
        return [self._entries[eid] for eid in recent_ids if eid in self._entries]

    def forget(self, entry_id: str) -> bool:
        """删除一条工作记忆"""
        if entry_id in self._entries:
            del self._entries[entry_id]
            with contextlib.suppress(ValueError):
                self._order.remove(entry_id)
            return True
        return False

    def clear(self) -> int:
        """清空所有工作记忆"""
        count = len(self._entries)
        self._entries.clear()
        self._order.clear()
        logger.debug(f"[WorkingMemory] 清空 {count} 条记忆")
        return count

    def collect_garbage(self, now: datetime | None = None) -> int:
        """垃圾回收：清理过期条目"""
        now = now or utc_now()
        removed = 0
        expired_ids = []

        for eid, entry in self._entries.items():
            age = (now - entry.created_at).total_seconds()
            if age > entry.ttl_seconds:
                expired_ids.append(eid)

        for eid in expired_ids:
            self.forget(eid)
            removed += 1

        if removed:
            logger.debug(f"[WorkingMemory] GC: 移除 {removed} 条过期记忆")
        return removed

    def __len__(self) -> int:
        return len(self._entries)
