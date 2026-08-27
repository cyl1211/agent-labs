"""
Unit tests for RAG system
"""

import pytest

from agent_labs.rag.indexing import DocumentChunk, DocumentIndexer
from agent_labs.rag.pipeline import RAGContext, RAGPipeline
from agent_labs.rag.retrieval import RetrievalResult, VectorRetriever

SAMPLE_TEXT = """
Python is a high-level programming language. It is widely used for web development,
data science, artificial intelligence, and automation.

FastAPI is a modern web framework for building APIs with Python. It is based on
standard Python type hints and provides automatic OpenAPI documentation.

Asynchronous programming in Python uses async/await syntax. The asyncio library
provides the foundation for concurrent code execution.
"""


class TestDocumentIndexer:
    def test_index_text_fixed_size(self):
        indexer = DocumentIndexer(chunk_size=200, chunk_overlap=20)
        chunks = indexer.index_text(SAMPLE_TEXT, source="test_doc")

        assert len(chunks) >= 2
        for chunk in chunks:
            assert isinstance(chunk, DocumentChunk)
            assert chunk.content
            assert chunk.metadata["source"] == "test_doc"

    def test_index_text_paragraph(self):
        indexer = DocumentIndexer(chunk_size=500)
        chunks = indexer.index_text(SAMPLE_TEXT, source="test", strategy="paragraph")
        assert len(chunks) >= 1

    def test_index_text_sentence(self):
        indexer = DocumentIndexer(chunk_size=300)
        chunks = indexer.index_text(SAMPLE_TEXT, source="test", strategy="sentence")
        assert len(chunks) >= 1

    def test_empty_text(self):
        indexer = DocumentIndexer()
        chunks = indexer.index_text("", source="empty")
        assert len(chunks) == 0

    def test_keyword_search(self):
        indexer = DocumentIndexer(chunk_size=200)
        indexer.index_text(SAMPLE_TEXT, source="test")

        results = indexer.search_by_keyword("FastAPI web framework")
        assert len(results) >= 1
        # 搜索结果应该包含 FastAPI 相关内容
        found_fastapi = False
        for r in results:
            if "FastAPI" in r.content:
                found_fastapi = True
                break
        assert found_fastapi

    def test_to_memory_entries(self):
        indexer = DocumentIndexer(chunk_size=200)
        chunks = indexer.index_text(SAMPLE_TEXT, source="test")

        entries = indexer.to_memory_entries(chunks)
        assert len(entries) == len(chunks)
        assert all(e.layer.value == "semantic" for e in entries)
        assert all("rag" in e.tags for e in entries)

    def test_get_stats(self):
        indexer = DocumentIndexer(chunk_size=200)
        indexer.index_text(SAMPLE_TEXT, source="doc1")
        indexer.index_text("Another document", source="doc2")

        stats = indexer.get_stats()
        assert stats["total_documents"] == 2
        assert stats["total_chunks"] > 0
        assert stats["inverted_index_size"] > 0

    def test_get_chunk(self):
        indexer = DocumentIndexer(chunk_size=200)
        indexer.index_text("test content here", source="test")

        chunk = indexer.get_chunk("test#0")
        assert chunk is not None
        assert "test content" in chunk.content

    def test_clear(self):
        indexer = DocumentIndexer()
        indexer.index_text(SAMPLE_TEXT, source="test")
        indexer.clear()

        stats = indexer.get_stats()
        assert stats["total_documents"] == 0
        assert stats["total_chunks"] == 0

    def test_min_chunk_size_filter(self):
        indexer = DocumentIndexer(chunk_size=200, min_chunk_size=200)
        # 创建一个短文本，分块后不够 min_chunk_size
        chunks = indexer.index_text("short", source="tiny")
        # 太短的块应被过滤
        assert len(chunks) == 0


class TestVectorRetriever:
    @pytest.fixture
    def indexer(self):
        idx = DocumentIndexer(chunk_size=150)
        idx.index_text(SAMPLE_TEXT, source="python_docs")
        return idx

    @pytest.fixture
    def retriever(self, indexer):
        return VectorRetriever(indexer=indexer)

    def test_keyword_retrieve(self, retriever):
        results = retriever.retrieve("FastAPI web framework", top_k=3, strategy="keyword")
        assert len(results) >= 1
        assert isinstance(results[0], RetrievalResult)

    def test_tfidf_retrieve(self, retriever):
        results = retriever.retrieve("Python programming", top_k=3, strategy="tfidf")
        assert len(results) >= 1
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_hybrid_retrieve(self, retriever):
        results = retriever.retrieve("async programming Python", top_k=5, strategy="hybrid")
        assert len(results) >= 1

    def test_empty_query(self, retriever):
        results = retriever.retrieve("", strategy="keyword")
        assert len(results) == 0

    def test_retrieval_result_to_dict(self, retriever):
        results = retriever.retrieve("Python", top_k=1, strategy="keyword")
        if results:
            d = results[0].to_dict()
            assert "content" in d
            assert "score" in d


class TestRAGPipeline:
    @pytest.fixture
    def pipeline(self):
        return RAGPipeline(default_top_k=3)

    def test_pipeline_basic(self, pipeline):
        # 先索引一些文档
        pipeline.indexer.index_text(SAMPLE_TEXT, source="python_info")
        pipeline.indexer.index_text(
            "Django is a Python web framework for building full-stack applications.",
            source="django_info",
        )

        result = pipeline.run("Python web framework", top_k=3)
        assert isinstance(result, RAGContext)
        assert len(result.results) >= 1

    def test_pipeline_context_text(self, pipeline):
        pipeline.indexer.index_text(SAMPLE_TEXT, source="test")

        result = pipeline.run("FastAPI", top_k=2)
        context_text = result.get_context_text()
        assert len(context_text) > 0
        assert "Retrieved Context" in context_text

    def test_pipeline_to_prompt_context(self, pipeline):
        pipeline.indexer.index_text(SAMPLE_TEXT, source="test")

        result = pipeline.run("Python", top_k=2)
        prompt_ctx = result.to_prompt_context(max_tokens=500)
        assert len(prompt_ctx) > 0

    def test_pipeline_no_results(self, pipeline):
        result = pipeline.run("xylophone quantum mechanics", top_k=3)
        assert isinstance(result, RAGContext)
        # 可能返回 0 个结果
        assert result.total_found >= 0

    def test_pipeline_run_with_indexing(self, pipeline):
        docs = ["Python is great for data science", "Python is used in web dev"]
        result = pipeline.run_with_indexing("Python data", documents=docs, top_k=2)
        assert len(result.results) >= 1

    def test_pipeline_stats(self, pipeline):
        pipeline.indexer.index_text(SAMPLE_TEXT, source="test")
        stats = pipeline.get_stats()
        assert "indexer" in stats
        assert stats["default_top_k"] == 3
