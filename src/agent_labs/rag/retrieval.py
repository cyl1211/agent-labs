"""
向量检索器

提供多种检索策略：
- TF-IDF 关键词检索（当前实现）
- 简单向量相似度（Phase 3: 替换为 ChromaDB + embedding）
- 混合检索（关键词 + 语义）
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


class RetrievalResult:
    """检索结果"""

    __slots__ = ("content", "score", "metadata", "source")

    def __init__(
        self,
        content: str,
        score: float,
        metadata: dict[str, Any] | None = None,
        source: str = "",
    ):
        self.content = content
        self.score = score
        self.metadata = metadata or {}
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content[:300],
            "score": round(self.score, 4),
            "source": self.source,
            "metadata": self.metadata,
        }


class VectorRetriever:
    """向量检索器

    检索策略按优先级：
    1. TF-IDF + 关键词匹配（当前可用）
    2. 向量余弦相似度（Phase 3，需要 embedding 模型）
    3. 混合检索（关键词 + 语义加权）

    使用方式：
        retriever = VectorRetriever(indexer, memory_manager)
        results = retriever.retrieve("How to implement RAG?", top_k=5)
    """

    def __init__(
        self,
        indexer=None,
        memory_manager=None,
        default_top_k: int = 5,
        hybrid_weight: float = 0.5,
    ):
        self.indexer = indexer
        self._memory = memory_manager
        self.default_top_k = default_top_k
        self.hybrid_weight = hybrid_weight

        # TF-IDF 缓存
        self._idf_cache: dict[str, float] = {}
        self._tf_cache: dict[str, dict[str, float]] = {}
        self._total_docs: int = 0

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        strategy: str = "hybrid",
    ) -> list[RetrievalResult]:
        """检索相关文档

        Args:
            query: 搜索查询
            top_k: 返回数量
            strategy: 检索策略 (keyword, tfidf, semantic, hybrid)

        Returns:
            检索结果列表
        """
        top_k = top_k or self.default_top_k
        query = query.strip()

        if not query:
            return []

        if strategy == "keyword" and self.indexer:
            return self._keyword_retrieve(query, top_k)
        elif strategy == "tfidf" and self.indexer:
            return self._tfidf_retrieve(query, top_k)
        elif strategy == "semantic" and self._memory:
            return self._semantic_retrieve(query, top_k)
        elif strategy == "hybrid":
            return self._hybrid_retrieve(query, top_k)
        else:
            # 回退到可用策略
            if self.indexer:
                return self._keyword_retrieve(query, top_k)
            if self._memory:
                return self._semantic_retrieve(query, top_k)
            return []

    def _keyword_retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """基于关键词的检索"""
        chunks = self.indexer.search_by_keyword(query, top_k)
        return [
            RetrievalResult(
                content=chunk.content,
                score=1.0 / (i + 1),  # 简单排名分数
                metadata=chunk.metadata,
                source=chunk.metadata.get("source", ""),
            )
            for i, chunk in enumerate(chunks)
        ]

    def _tfidf_retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """基于 TF-IDF 的检索"""
        # 构建或更新 IDF
        if not self._idf_cache:
            self._build_tfidf_index()

        query_words = query.lower().split()
        if not query_words:
            return []

        # 计算查询 TF-IDF 向量
        query_tf = Counter(query_words)
        query_vector: dict[str, float] = {}
        for word, count in query_tf.items():
            idf = self._idf_cache.get(word, 0.0)
            query_vector[word] = count * idf

        # 计算每个文档的余弦相似度
        scores = []
        for chunk_id, doc_tfidf in self._tf_cache.items():
            similarity = self._cosine_similarity(query_vector, doc_tfidf)
            if similarity > 0:
                scores.append((chunk_id, similarity))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for chunk_id, score in scores[:top_k]:
            chunk = self.indexer.get_chunk(chunk_id) if self.indexer else None
            if chunk:
                results.append(
                    RetrievalResult(
                        content=chunk.content,
                        score=score,
                        metadata=chunk.metadata,
                        source=chunk.metadata.get("source", ""),
                    )
                )

        return results

    async def _semantic_retrieve_async(self, query: str, top_k: int) -> list[RetrievalResult]:
        """基于语义记忆的异步检索"""
        if not self._memory:
            return []

        try:
            entries = await self._memory.search(query, top_k=top_k, layer="semantic")
        except Exception as e:
            logger.warning(f"[Retriever] 语义检索失败: {e}")
            return []

        return [
            RetrievalResult(
                content=entry.content,
                score=entry.importance,
                metadata=entry.metadata,
                source="semantic_memory",
            )
            for entry in entries
        ]

    def _semantic_retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """同步语义检索"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在线程池中运行
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, self._semantic_retrieve_async(query, top_k)
                    )
                    return future.result(timeout=10)
            else:
                return asyncio.run(self._semantic_retrieve_async(query, top_k))
        except Exception as e:
            logger.error(f"[Retriever] 语义检索异常: {e}")
            return []

    def _hybrid_retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """混合检索：结合关键词和语义检索结果

        使用加权融合策略：
        - 关键词匹配: 精确但覆盖面窄
        - 语义匹配: 覆盖面广但精确度低
        通过 hybrid_weight 调节两者的权重。
        """
        keyword_results = []
        semantic_results = []

        # 关键词检索
        if self.indexer:
            keyword_results = self._keyword_retrieve(query, top_k)

        # 语义检索
        if self._memory:
            semantic_results = self._semantic_retrieve(query, top_k)

        # 融合结果
        merged: dict[str, RetrievalResult] = {}

        # 关键词结果，权重 = 1 - hybrid_weight
        kw_weight = 1.0 - self.hybrid_weight
        for r in keyword_results:
            key = r.content[:100]
            merged[key] = RetrievalResult(
                content=r.content,
                score=r.score * kw_weight,
                metadata={**r.metadata, "strategy": "keyword"},
                source=r.source,
            )

        # 语义结果，权重 = hybrid_weight
        for r in semantic_results:
            key = r.content[:100]
            if key in merged:
                # 两个策略都找到了同一条，分数相加
                merged[key].score += r.score * self.hybrid_weight
                merged[key].metadata["strategy"] = "hybrid"
            else:
                merged[key] = RetrievalResult(
                    content=r.content,
                    score=r.score * self.hybrid_weight,
                    metadata={**r.metadata, "strategy": "semantic"},
                    source=r.source,
                )

        # 排序
        ranked = sorted(merged.values(), key=lambda x: x.score, reverse=True)
        return ranked[:top_k]

    def _build_tfidf_index(self) -> None:
        """构建 TF-IDF 索引"""
        if not self.indexer:
            return

        self._idf_cache.clear()
        self._tf_cache.clear()

        # 收集所有文档
        all_words_per_doc: dict[str, Counter] = {}
        for chunk_id, chunk in self.indexer._chunks.items():
            words = chunk.content.lower().split()
            all_words_per_doc[chunk_id] = Counter(words)

        self._total_docs = len(all_words_per_doc)
        if self._total_docs == 0:
            return

        # 计算 IDF
        doc_freq: Counter = Counter()
        for word_counts in all_words_per_doc.values():
            doc_freq.update(word_counts.keys())

        for word, df in doc_freq.items():
            self._idf_cache[word] = math.log((self._total_docs + 1) / (df + 1)) + 1.0

        # 计算 TF-IDF
        for chunk_id, word_counts in all_words_per_doc.items():
            tfidf = {}
            total_words = sum(word_counts.values()) or 1
            for word, count in word_counts.items():
                tf = count / total_words
                tfidf[word] = tf * self._idf_cache.get(word, 0)
            self._tf_cache[chunk_id] = tfidf

    @staticmethod
    def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
        """计算两个稀疏向量的余弦相似度"""
        dot_product = 0.0
        norm1 = 0.0
        norm2 = 0.0

        for word, val1 in vec1.items():
            val2 = vec2.get(word, 0.0)
            dot_product += val1 * val2
            norm1 += val1 * val1

        for val2 in vec2.values():
            norm2 += val2 * val2

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))

    def set_memory_manager(self, manager) -> None:
        """设置记忆管理器"""
        self._memory = manager

    def set_indexer(self, indexer) -> None:
        """设置索引器"""
        self.indexer = indexer
        self._idf_cache.clear()
        self._tf_cache.clear()
