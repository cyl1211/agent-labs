"""
程序记忆层 (Procedural Memory)

成功执行模式和策略。
- 记录"怎么做"的经验
- 高重要性、长 TTL
- 按任务类型分类
"""

from __future__ import annotations

import logging
from datetime import datetime

from ...core.types import MemoryEntry, MemoryQuery, utc_now

logger = logging.getLogger(__name__)


class ProceduralMemory:
    """程序记忆 — 成功执行模式和策略

    特性:
    - 记录验证过的成功模式
    - 按模式类型分类（推理模式、工具链、对话策略等）
    - 高重要性阈值（默认只保留 importance >= 0.6 的条目）
    - 自动从成功经验中学习

    模式类型：
    - reasoning: 推理模式
    - tool_chain: 工具组合序列
    - response: 回复策略
    - workflow: 工作流程
    """

    PATTERN_TYPES = ["reasoning", "tool_chain", "response", "workflow"]

    def __init__(
        self,
        max_entries: int = 500,
        default_ttl_seconds: int = 86400 * 90,
        min_importance: float = 0.5,
    ):
        self.max_entries = max_entries
        self.default_ttl_seconds = default_ttl_seconds
        self.min_importance = min_importance
        self._entries: dict[str, MemoryEntry] = {}
        # 按模式类型索引
        self._pattern_index: dict[str, list[str]] = {pt: [] for pt in self.PATTERN_TYPES}

    def write(self, entry: MemoryEntry) -> str:
        """写入程序记忆

        低于最低重要性阈值的条目会被拒绝。
        """
        if entry.importance < self.min_importance:
            logger.debug(
                f"[ProceduralMemory] 拒绝低重要性条目 "
                f"(importance={entry.importance} < {self.min_importance})"
            )
            return ""

        entry_id = entry.id

        # 冲突检测：相同标签的模式更新而不是新增
        similar = self._find_by_tags(entry.tags)
        if similar:
            logger.debug(f"[ProceduralMemory] 更新已有模式 (id={similar.id}), 提升重要性")
            new_data = similar.model_dump()
            new_data["importance"] = min(1.0, similar.importance + 0.15)
            new_data["content"] = entry.content
            new_data["last_accessed_at"] = utc_now()
            new_data["access_count"] = similar.access_count + 1
            self._entries[similar.id] = MemoryEntry(**new_data)
            return similar.id

        self._entries[entry_id] = entry

        # 更新模式类型索引
        for tag in entry.tags:
            if tag in self.PATTERN_TYPES:
                self._pattern_index.setdefault(tag, []).append(entry_id)

        # 容量管理
        if len(self._entries) > self.max_entries:
            self._evict_lowest_importance()

        logger.debug(f"[ProceduralMemory] 写入模式: {entry.content[:80]}...")
        return entry_id

    def read(self, query: MemoryQuery) -> list[MemoryEntry]:
        """读取程序记忆"""
        results = []
        for entry in self._entries.values():
            if query.min_importance and entry.importance < query.min_importance:
                continue
            if query.tags and not any(t in entry.tags for t in query.tags):
                continue
            results.append(entry)

        results.sort(key=lambda e: (e.importance, e.access_count), reverse=True)
        return results[: query.limit]

    def search(self, query_str: str, top_k: int = 5) -> list[MemoryEntry]:
        """搜索程序记忆"""
        query_lower = query_str.lower()
        scored = []

        for entry in self._entries.values():
            score = 0.0
            content_lower = entry.content.lower()
            for word in query_lower.split():
                if word in content_lower:
                    score += 1.5  # 程序记忆匹配权重更高
            for tag in entry.tags:
                if tag.lower() in query_lower:
                    score += 3.0  # 标签匹配权重更高
            if score > 0:
                # 考虑使用频率（成功次数越多权重越高）
                score *= 1 + 0.1 * min(entry.access_count, 10)
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def get_by_pattern_type(self, pattern_type: str) -> list[MemoryEntry]:
        """获取指定类型的模式"""
        if pattern_type not in self.PATTERN_TYPES:
            return []
        entry_ids = self._pattern_index.get(pattern_type, [])
        return [self._entries[eid] for eid in entry_ids if eid in self._entries]

    def reinforce(self, entry_id: str, success: bool = True) -> bool:
        """强化（成功）或弱化（失败）一个模式

        成功的模式提升重要性，失败的模式降低。
        """
        if entry_id not in self._entries:
            return False

        entry = self._entries[entry_id]
        new_data = entry.model_dump()

        if success:
            new_data["importance"] = min(1.0, entry.importance + 0.1)
            new_data["access_count"] = entry.access_count + 1
        else:
            new_data["importance"] = max(0.1, entry.importance - 0.15)

        new_data["last_accessed_at"] = utc_now()
        self._entries[entry_id] = MemoryEntry(**new_data)
        return True

    def extract_pattern(
        self,
        content: str,
        pattern_type: str,
        tags: list[str] | None = None,
        importance: float = 0.6,
    ) -> str:
        """从成功经验中提取模式"""
        if pattern_type not in self.PATTERN_TYPES:
            pattern_type = "workflow"

        all_tags = [pattern_type] + (tags or [])
        entry = MemoryEntry(
            layer="procedural",
            content=content[:500],
            importance=importance,
            tags=all_tags,
            ttl_seconds=self.default_ttl_seconds,
        )
        return self.write(entry)

    def _find_by_tags(self, tags: list[str]) -> MemoryEntry | None:
        """通过标签查找相似模式"""
        tag_set = set(tags)
        for entry in self._entries.values():
            entry_tags = set(entry.tags)
            if tag_set & entry_tags:
                return entry
        return None

    def forget(self, entry_id: str) -> bool:
        """删除一条程序记忆"""
        if entry_id in self._entries:
            entry = self._entries.pop(entry_id)
            # 清理模式索引
            for tag in entry.tags:
                if tag in self._pattern_index and entry_id in self._pattern_index[tag]:
                    self._pattern_index[tag].remove(entry_id)
            return True
        return False

    def collect_garbage(self, now: datetime | None = None) -> int:
        """垃圾回收"""
        now = now or utc_now()
        removed = 0
        expired_ids = []

        for eid, entry in self._entries.items():
            age = (now - entry.created_at).total_seconds()
            if age > entry.ttl_seconds:
                expired_ids.append(eid)
                continue
            # 程序记忆更持久，但低重要性 + 长时间未访问仍需清理
            if entry.importance < 0.3 and entry.access_count < 1:
                age_days = age / 86400
                if age_days > 30:
                    expired_ids.append(eid)

        for eid in expired_ids:
            self.forget(eid)
            removed += 1

        if removed:
            logger.debug(f"[ProceduralMemory] GC: 移除 {removed} 条")
        return removed

    def _evict_lowest_importance(self) -> None:
        """淘汰最弱的模式"""
        if not self._entries:
            return
        lowest = min(
            self._entries.values(), key=lambda e: e.importance * (1 + e.access_count * 0.1)
        )
        self.forget(lowest.id)
        logger.debug(f"[ProceduralMemory] 淘汰: {lowest.content[:50]}...")

    def __len__(self) -> int:
        return len(self._entries)
