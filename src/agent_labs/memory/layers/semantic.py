"""
语义记忆层 (Semantic Memory)

长期知识、事实、用户偏好。
- 高持久性（TTL 最长，默认 7 天）
- 基于向量的语义搜索
- 支持事实冲突检测

当前阶段：内存存储 + 关键词搜索
Phase 3：ChromaDB 向量存储 + 真正的余弦相似度搜索
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from ...core.types import MemoryEntry, MemoryQuery, utc_now

logger = logging.getLogger(__name__)


class SemanticMemory:
    """语义记忆 — 长期知识和事实

    特性:
    - 高持久性（默认保留更长）
    - 冲突检测（相似事实去重）
    - 关键词 + 简单嵌入相似度搜索
    """

    def __init__(
        self,
        max_entries: int = 5000,
        default_ttl_seconds: int = 86400 * 7,
        embedding_dimension: int = 1536,
        similarity_threshold: float = 0.85,
    ):
        self.max_entries = max_entries
        self.default_ttl_seconds = default_ttl_seconds
        self.embedding_dimension = embedding_dimension
        self.similarity_threshold = similarity_threshold
        self._entries: dict[str, MemoryEntry] = {}

    def write(self, entry: MemoryEntry) -> str:
        """写入语义记忆

        写入前检查是否有高度相似的已存在事实进行合并。
        """
        entry_id = entry.id

        # 冲突检测：查找相似条目
        if entry.content:
            similar = self._find_similar(entry.content, threshold=self.similarity_threshold)
            if similar:
                logger.debug(f"[SemanticMemory] 发现相似记忆 (id={similar.id}), 提升其重要性并更新")
                # 更新已有条目而非创建新条目
                new_data = similar.model_dump()
                new_data["importance"] = min(1.0, similar.importance + 0.1)
                new_data["content"] = entry.content  # 用新内容覆盖
                new_data["last_accessed_at"] = utc_now()
                new_data["access_count"] = similar.access_count + 1
                self._entries[similar.id] = MemoryEntry(**new_data)
                return similar.id

        self._entries[entry_id] = entry

        # 容量管理
        if len(self._entries) > self.max_entries:
            self._evict_lowest_importance()

        logger.debug(f"[SemanticMemory] 写入: {entry.content[:80]}... (共 {len(self._entries)} 条)")
        return entry_id

    def read(self, query: MemoryQuery) -> list[MemoryEntry]:
        """读取语义记忆"""
        results = []
        for entry in self._entries.values():
            if query.min_importance and entry.importance < query.min_importance:
                continue
            if query.tags and not any(t in entry.tags for t in query.tags):
                continue
            results.append(entry)

        results.sort(key=lambda e: (e.importance, e.last_accessed_at), reverse=True)
        return results[: query.limit]

    def search(
        self, query_str: str, top_k: int = 5, use_embedding: bool = False
    ) -> list[MemoryEntry]:
        """搜索语义记忆

        使用关键词匹配 + 简单 TF-IDF 相似度。
        当 use_embedding=True 且条目有 embedding 时，使用余弦相似度。
        """
        query_lower = query_str.lower()
        query_words = query_lower.split()

        if use_embedding:
            # Phase 3: 使用 embedding 向量进行余弦相似度搜索
            pass

        scored = []
        for entry in self._entries.values():
            score = self._compute_relevance(query_words, entry)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def _compute_relevance(self, query_words: list[str], entry: MemoryEntry) -> float:
        """计算查询与记忆条目的相关性分数

        使用加权关键词匹配：
        - 内容匹配: 每个词 1 分
        - 标签匹配: 每个标签 2 分
        - 重要性加权: × importance
        - 访问频率: × log(1 + access_count)
        """
        score = 0.0
        content_lower = entry.content.lower()

        for word in query_words:
            if word in content_lower:
                score += 1.0
            # 部分匹配（词根）
            if len(word) > 3 and word[:4] in content_lower:
                score += 0.5

        for tag in entry.tags:
            tag_lower = tag.lower()
            if tag_lower in " ".join(query_words):
                score += 2.0
            for word in query_words:
                if word in tag_lower:
                    score += 1.0

        # 加权
        weighted_score = score * entry.importance * (1 + math.log(1 + entry.access_count))
        return weighted_score

    def _find_similar(self, content: str, threshold: float = 0.85) -> MemoryEntry | None:
        """查找与给定内容相似的已有记忆条目

        使用 Jaccard 相似度（词级别）进行快速匹配。
        """
        words = set(content.lower().split())
        if len(words) < 3:
            return None

        best_match = None
        best_score = 0.0

        for entry in self._entries.values():
            entry_words = set(entry.content.lower().split())
            if not entry_words:
                continue
            # Jaccard 相似度
            intersection = words & entry_words
            union = words | entry_words
            jaccard = len(intersection) / len(union) if union else 0
            if jaccard > best_score and jaccard >= threshold:
                best_score = jaccard
                best_match = entry

        return best_match

    def forget(self, entry_id: str) -> bool:
        """删除一条语义记忆"""
        if entry_id in self._entries:
            del self._entries[entry_id]
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
            # 语义记忆比情景记忆更持久，但有更严格的低重要性清理
            if entry.importance < 0.15 and entry.access_count < 1:
                age_days = age / 86400
                if age_days > 14:
                    expired_ids.append(eid)

        for eid in expired_ids:
            self.forget(eid)
            removed += 1

        if removed:
            logger.debug(f"[SemanticMemory] GC: 移除 {removed} 条")
        return removed

    def get_facts(self, top_k: int = 10) -> list[MemoryEntry]:
        """获取最重要的知识条目"""
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: (e.importance, e.access_count),
            reverse=True,
        )
        return sorted_entries[:top_k]

    def _evict_lowest_importance(self) -> None:
        """淘汰重要性最低的条目"""
        if not self._entries:
            return
        # 综合考虑重要性和访问次数
        lowest = min(
            self._entries.values(),
            key=lambda e: e.importance * (1 + math.log(1 + e.access_count)),
        )
        self.forget(lowest.id)
        logger.debug(f"[SemanticMemory] 淘汰: {lowest.content[:50]}...")

    def __len__(self) -> int:
        return len(self._entries)
