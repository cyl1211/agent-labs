"""
RAG 管道

端到端的检索增强生成流程：
1. 查询分析 → 确定检索策略
2. 多源检索 → 文档块 + 语义记忆 + 程序模式
3. 上下文聚合 → 去重、排序、截断
4. 增强生成 → 构建含检索结果的提示词
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .indexing import DocumentChunk, DocumentIndexer
from .retrieval import RetrievalResult, VectorRetriever

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """RAG 上下文 — 检索和聚合的结果"""

    query: str
    results: list[RetrievalResult] = field(default_factory=list)
    total_found: int = 0
    strategies_used: list[str] = field(default_factory=list)

    def get_context_text(self, max_chars: int = 4000) -> str:
        """获取拼接好的上下文文本"""
        if not self.results:
            return ""

        lines = [f"## Retrieved Context for: {self.query}", ""]
        total = 0

        for i, r in enumerate(self.results, 1):
            snippet = r.content[:500]
            lines.append(f"### Source {i} (score: {r.score:.2f})")
            lines.append(snippet)
            lines.append("")
            total += len(snippet)
            if total >= max_chars:
                lines.append(f"... [截断: {len(self.results) - i} 个结果省略]")
                break

        return "\n".join(lines)

    def to_prompt_context(self, max_tokens: int = 3000) -> str:
        """转换为适合 LLM 提示词的上下文格式"""
        if not self.results:
            return "No relevant documents found."

        lines = ["Relevant context from knowledge base:"]
        chars_per_token = 4
        max_chars = max_tokens * chars_per_token
        used = 0

        for i, r in enumerate(self.results, 1):
            entry = f"\n[{i}] {r.content[:400]}"
            if used + len(entry) > max_chars:
                break
            lines.append(entry)
            used += len(entry)

        return "\n".join(lines)


class RAGPipeline:
    """RAG 管道

    端到端的检索增强生成流程。

    使用方式：
        pipeline = RAGPipeline(indexer, retriever)
        rag_context = pipeline.run(query="How to use FastAPI?")
        # 将 rag_context 注入 LLM 的上下文中
    """

    def __init__(
        self,
        indexer: DocumentIndexer | None = None,
        retriever: VectorRetriever | None = None,
        memory_manager=None,
        default_top_k: int = 5,
        max_context_tokens: int = 4000,
    ):
        self.indexer = indexer or DocumentIndexer()
        self.retriever = retriever or VectorRetriever(indexer=self.indexer)
        self._memory = memory_manager
        self.default_top_k = default_top_k
        self.max_context_tokens = max_context_tokens

    def run(
        self,
        query: str,
        top_k: int | None = None,
        strategy: str = "hybrid",
        use_memory: bool = True,
    ) -> RAGContext:
        """执行 RAG 管道

        流程：
        1. 查询分析 → 提取关键词和意图
        2. 多源检索 → 索引 + 记忆
        3. 聚合去重 → 按分数合并排序
        4. 构建上下文 → 生成 RAGContext

        Args:
            query: 用户查询
            top_k: 各源返回的条目数
            strategy: 检索策略
            use_memory: 是否使用语义记忆作为额外来源

        Returns:
            RAGContext 包含所有检索结果
        """
        top_k = top_k or self.default_top_k

        all_results: list[RetrievalResult] = []
        strategies_used: list[str] = []

        # 1. 文档索引检索
        index_results = self.retriever.retrieve(query, top_k=top_k, strategy=strategy)
        all_results.extend(index_results)
        strategies_used.append(f"index:{strategy}")

        # 2. 语义记忆检索
        if use_memory and self._memory:
            memory_results = self._retrieve_from_memory(query, top_k)
            if memory_results:
                all_results.extend(memory_results)
                strategies_used.append("memory:semantic")

        # 3. 排序和去重
        merged = self._deduplicate_and_rank(all_results, top_k)

        logger.info(
            f"[RAGPipeline] 检索完成: '{query[:50]}...' → "
            f"{len(merged)} 个结果 (来源: {strategies_used})"
        )

        return RAGContext(
            query=query,
            results=merged,
            total_found=len(all_results),
            strategies_used=strategies_used,
        )

    def run_with_indexing(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> RAGContext:
        """先索引文档再搜索

        适合临时文档的 RAG（不需要预先索引）。

        Args:
            query: 用户查询
            documents: 要即时索引的文本列表
            top_k: 返回数量

        Returns:
            RAGContext
        """
        # 临时索引
        for i, doc_text in enumerate(documents):
            self.indexer.index_text(doc_text, source=f"temp_doc_{i}")

        result = self.run(query, top_k=top_k, use_memory=False)

        # 清理临时索引
        for i in range(len(documents)):
            source = f"temp_doc_{i}"
            # 移除临时文档的块
            to_remove = [
                cid
                for cid, chunk in self.indexer._chunks.items()
                if chunk.metadata.get("source") == source
            ]
            for cid in to_remove:
                self.indexer._chunks.pop(cid, None)

        return result

    def _retrieve_from_memory(self, query: str, top_k: int) -> list[RetrievalResult]:
        """从语义记忆中检索"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._async_memory_search, query, top_k)
                    return future.result(timeout=10)
            else:
                return asyncio.run(self._async_memory_search(query, top_k))
        except Exception as e:
            logger.error(f"[RAGPipeline] 记忆检索失败: {e}")
            return []

    async def _async_memory_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        """异步搜索语义记忆"""
        if not self._memory:
            return []

        try:
            entries = await self._memory.search(query, top_k=top_k, layer="semantic")
        except Exception:
            return []

        return [
            RetrievalResult(
                content=entry.content,
                score=entry.importance,
                metadata={"memory_layer": "semantic", **entry.metadata},
                source=f"memory:{entry.id}",
            )
            for entry in entries
        ]

    def _deduplicate_and_rank(
        self, results: list[RetrievalResult], top_k: int
    ) -> list[RetrievalResult]:
        """去重并重排结果

        去重策略：内容前 100 字符相同的视为重复，保留高分者。
        """
        seen: dict[str, RetrievalResult] = {}

        for r in results:
            key = r.content[:100].strip().lower()
            if key not in seen or r.score > seen[key].score:
                seen[key] = r

        ranked = sorted(seen.values(), key=lambda x: x.score, reverse=True)
        return ranked[:top_k]

    def index_document(self, file_path: str) -> list[DocumentChunk]:
        """索引单个文档"""
        return self.indexer.index_file(file_path)

    def index_directory(self, directory: str) -> dict[str, list[DocumentChunk]]:
        """索引目录"""
        return self.indexer.index_directory(directory)

    def get_stats(self) -> dict[str, Any]:
        """获取管道统计"""
        return {
            "indexer": self.indexer.get_stats(),
            "default_top_k": self.default_top_k,
            "max_context_tokens": self.max_context_tokens,
        }

    def set_memory_manager(self, manager) -> None:
        """设置记忆管理器"""
        self._memory = manager
        self.retriever.set_memory_manager(manager)
