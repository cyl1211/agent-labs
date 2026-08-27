"""
文档索引器

将文档分块、提取元数据、建立索引。
支持多种文档格式和分块策略。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ..core.types import MemoryEntry, MemoryLayer

logger = logging.getLogger(__name__)


class DocumentChunk:
    """文档块"""

    __slots__ = ("id", "content", "metadata", "chunk_index", "total_chunks")

    def __init__(
        self,
        id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        chunk_index: int = 0,
        total_chunks: int = 1,
    ):
        self.id = id
        self.content = content
        self.metadata = metadata or {}
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks

    def to_memory_entry(self, layer: str = "semantic") -> MemoryEntry:
        """转换为记忆条目，用于存入语义记忆层"""
        return MemoryEntry(
            layer=MemoryLayer.SEMANTIC,
            content=self.content[:1000],
            importance=0.6,
            tags=["rag", "document", f"doc:{self.metadata.get('source', 'unknown')}"],
            metadata={
                "chunk_id": self.id,
                "chunk_index": self.chunk_index,
                "total_chunks": self.total_chunks,
                **self.metadata,
            },
        )


class DocumentIndexer:
    """文档索引器

    负责：
    - 加载文档（文件路径或文本内容）
    - 分块（固定大小、段落、句子、语义）
    - 提取元数据
    - 建立倒排索引

    使用方式：
        indexer = DocumentIndexer(chunk_size=500, chunk_overlap=50)
        chunks = indexer.index_file("docs/architecture.md")
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
        max_chunks_per_doc: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunks_per_doc = max_chunks_per_doc

        # 倒排索引: word → set(chunk_id)
        self._inverted_index: dict[str, set[str]] = {}
        # 文档块存储
        self._chunks: dict[str, DocumentChunk] = {}
        # 文档元数据
        self._documents: dict[str, dict[str, Any]] = {}

    def index_text(
        self,
        text: str,
        source: str = "inline",
        metadata: dict[str, Any] | None = None,
        strategy: str = "fixed_size",
    ) -> list[DocumentChunk]:
        """索引文本内容

        Args:
            text: 文本内容
            source: 来源标识
            metadata: 元数据
            strategy: 分块策略 (fixed_size, paragraph, sentence)

        Returns:
            生成的文档块列表
        """
        if not text.strip():
            logger.warning(f"[Indexer] 跳过空文档: {source}")
            return []

        # 分块
        if strategy == "paragraph":
            chunks_content = self._chunk_by_paragraph(text)
        elif strategy == "sentence":
            chunks_content = self._chunk_by_sentence(text)
        else:
            chunks_content = self._chunk_fixed_size(text)

        # 限制块数
        if len(chunks_content) > self.max_chunks_per_doc:
            logger.warning(
                f"[Indexer] 文档 '{source}' 分块过多 ({len(chunks_content)}), "
                f"限制为 {self.max_chunks_per_doc}"
            )
            chunks_content = chunks_content[: self.max_chunks_per_doc]

        # 构建 DocumentChunk 对象
        chunks = []
        doc_id = source
        self._documents[doc_id] = {"source": source, **(metadata or {})}

        for i, content in enumerate(chunks_content):
            if len(content.strip()) < self.min_chunk_size:
                continue

            chunk_id = f"{doc_id}#{i}"
            chunk = DocumentChunk(
                id=chunk_id,
                content=content,
                metadata={"source": source, **(metadata or {})},
                chunk_index=i,
                total_chunks=len(chunks_content),
            )
            chunks.append(chunk)
            self._chunks[chunk_id] = chunk

            # 更新倒排索引
            self._update_inverted_index(chunk_id, content)

        logger.info(
            f"[Indexer] 索引完成: '{source}' → {len(chunks)} 个块 "
            f"(策略: {strategy}, 块大小: {self.chunk_size})"
        )
        return chunks

    def index_file(
        self,
        file_path: str | Path,
        strategy: str = "fixed_size",
    ) -> list[DocumentChunk]:
        """索引文件

        Args:
            file_path: 文件路径
            strategy: 分块策略

        Returns:
            文档块列表
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if file_path.suffix not in self._supported_formats():
            raise ValueError(f"不支持的文件格式: {file_path.suffix}")

        try:
            with open(file_path, encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, encoding="gbk") as f:
                text = f.read()

        metadata = {
            "file_path": str(file_path.absolute()),
            "file_name": file_path.name,
            "file_type": file_path.suffix,
            "file_size": file_path.stat().st_size,
        }

        return self.index_text(text, source=file_path.name, metadata=metadata, strategy=strategy)

    def index_directory(
        self,
        directory: str | Path,
        glob_pattern: str = "**/*",
        strategy: str = "fixed_size",
    ) -> dict[str, list[DocumentChunk]]:
        """批量索引目录中的文件

        Args:
            directory: 目录路径
            glob_pattern: 文件匹配模式
            strategy: 分块策略

        Returns:
            {文件名: [文档块]}
        """
        directory = Path(directory)
        results: dict[str, list[DocumentChunk]] = {}
        supported = self._supported_formats()

        for file_path in directory.glob(glob_pattern):
            if not file_path.is_file():
                continue
            if file_path.suffix not in supported:
                continue
            try:
                chunks = self.index_file(file_path, strategy)
                if chunks:
                    results[file_path.name] = chunks
            except Exception as e:
                logger.error(f"[Indexer] 索引文件失败 '{file_path}': {e}")

        logger.info(f"[Indexer] 目录索引完成: {len(results)} 个文件")
        return results

    def _chunk_fixed_size(self, text: str) -> list[str]:
        """固定大小分块（带重叠）"""
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            chunk_text = text[start:end]

            # 尝试在句子边界截断
            if end < text_len:
                last_period = chunk_text.rfind("。")
                last_newline = chunk_text.rfind("\n")
                cutoff = max(last_period, last_newline)
                if cutoff > self.chunk_size // 2:
                    end = start + cutoff + 1
                    chunk_text = text[start:end]

            chunks.append(chunk_text.strip())
            start = end - self.chunk_overlap

        return chunks

    def _chunk_by_paragraph(self, text: str) -> list[str]:
        """按段落分块"""
        paragraphs = re.split(r"\n\s*\n", text)
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current) + len(para) <= self.chunk_size:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append(current)
                # 如果段落本身超长，进一步拆分
                if len(para) > self.chunk_size:
                    sub_chunks = self._chunk_fixed_size(para)
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks

    def _chunk_by_sentence(self, text: str) -> list[str]:
        """按句子分块（智能合并短句）"""
        sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
        chunks = []
        current = ""

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            if len(current) + len(sent) <= self.chunk_size:
                current += sent
            else:
                if current:
                    chunks.append(current)
                current = sent

        if current:
            chunks.append(current)

        return chunks

    def _update_inverted_index(self, chunk_id: str, content: str) -> None:
        """更新倒排索引"""
        # 分词（简单按空格和标点分割）
        words = set(re.findall(r"\w+", content.lower()))
        for word in words:
            if len(word) < 2:  # 跳过单字符
                continue
            self._inverted_index.setdefault(word, set()).add(chunk_id)

    def search_by_keyword(self, query: str, top_k: int = 10) -> list[DocumentChunk]:
        """基于倒排索引的关键词检索

        Args:
            query: 搜索查询
            top_k: 返回数量

        Returns:
            匹配的文档块列表
        """
        query_words = set(re.findall(r"\w+", query.lower()))
        if not query_words:
            return []

        # 计算每个 chunk 的匹配分数
        scores: dict[str, float] = {}
        for word in query_words:
            if len(word) < 2:
                continue
            matching_chunks = self._inverted_index.get(word, set())
            for chunk_id in matching_chunks:
                scores[chunk_id] = scores.get(chunk_id, 0) + 1.0

        # 排序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [self._chunks[cid] for cid, _ in ranked[:top_k] if cid in self._chunks]

    def to_memory_entries(self, chunks: list[DocumentChunk]) -> list[MemoryEntry]:
        """将文档块转换为记忆条目"""
        return [chunk.to_memory_entry() for chunk in chunks]

    def get_chunk(self, chunk_id: str) -> DocumentChunk | None:
        """获取指定文档块"""
        return self._chunks.get(chunk_id)

    def get_stats(self) -> dict[str, Any]:
        """获取索引统计"""
        return {
            "total_documents": len(self._documents),
            "total_chunks": len(self._chunks),
            "inverted_index_size": len(self._inverted_index),
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }

    def clear(self) -> None:
        """清空索引"""
        self._chunks.clear()
        self._inverted_index.clear()
        self._documents.clear()

    @staticmethod
    def _supported_formats() -> set[str]:
        """支持的文件格式"""
        return {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".html",
            ".css",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".rst",
            ".java",
            ".go",
            ".rs",
            ".cpp",
            ".c",
            ".h",
            ".rb",
            ".php",
            ".sh",
            ".bat",
            ".sql",
            ".xml",
            ".csv",
        }
