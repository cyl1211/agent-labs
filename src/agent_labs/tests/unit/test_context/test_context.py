"""
Unit tests for context engineering
"""

import pytest

from agent_labs.context.builder import ContextBuilder
from agent_labs.context.compressor import CompressionResult, ContextCompressor
from agent_labs.context.knowledge import KnowledgeInjector
from agent_labs.core.types import AgentContext, MemoryEntry, MemoryLayer, Message, Role


def make_msg(role: Role, content: str) -> Message:
    return Message(role=role, content=content)


class TestContextBuilder:
    def test_build_basic(self):
        builder = ContextBuilder(max_tokens=10000)
        context = AgentContext(
            session_id="test",
            messages=[
                make_msg(Role.USER, "Hello"),
                make_msg(Role.ASSISTANT, "Hi there!"),
            ],
        )
        messages = builder.build(context)
        assert len(messages) >= 2  # system + history
        has_system = any(m.role == Role.SYSTEM for m in messages)
        assert has_system

    def test_build_with_memories(self):
        builder = ContextBuilder(max_tokens=10000)
        memories = [
            MemoryEntry(
                layer=MemoryLayer.SEMANTIC,
                content="User prefers concise answers",
                importance=0.8,
            ),
            MemoryEntry(
                layer=MemoryLayer.WORKING,
                content="Current task: debugging",
                importance=0.9,
            ),
        ]
        context = AgentContext(
            session_id="test",
            messages=[make_msg(Role.USER, "help")],
            memories=memories,
        )
        messages = builder.build(context)
        assert len(messages) > 0
        # 系统消息应包含记忆
        system_msg = next(m for m in messages if m.role == Role.SYSTEM)
        assert "concise" in system_msg.content or "debugging" in system_msg.content

    def test_token_budget_truncation(self):
        builder = ContextBuilder(max_tokens=100)  # 很小的预算
        messages = []
        for _i in range(50):
            messages.append(make_msg(Role.USER, "x" * 50))

        context = AgentContext(session_id="test", messages=messages)
        result = builder.build(context)
        # 应该被截断
        assert len(result) < 50

    def test_build_with_memory_injection(self):
        builder = ContextBuilder()
        memories = [
            MemoryEntry(
                layer=MemoryLayer.SEMANTIC,
                content="Important fact",
                importance=0.9,
            ),
        ]
        context = AgentContext(session_id="test", memories=memories)
        msgs = builder.build_with_memory_injection(context, "test query")
        assert len(msgs) > 0
        assert "Important fact" in msgs[0].content

    def test_get_budget_info(self):
        builder = ContextBuilder(
            max_tokens=10000, system_reserve_tokens=1000, response_reserve_tokens=2000
        )
        info = builder.get_budget_info()
        assert info["max_tokens"] == 10000
        assert info["system_reserve"] == 1000


class TestContextCompressor:
    def test_should_compress_by_count(self):
        compressor = ContextCompressor(threshold_messages=5)
        messages = [make_msg(Role.USER, f"msg {i}") for i in range(10)]
        assert compressor.should_compress(messages)

    def test_should_not_compress_short(self):
        compressor = ContextCompressor(threshold_messages=50)
        messages = [make_msg(Role.USER, f"msg {i}") for i in range(3)]
        assert not compressor.should_compress(messages)

    def test_compress(self):
        compressor = ContextCompressor(
            threshold_messages=10,
            keep_recent=3,
            max_summary_length=500,
        )
        messages = [make_msg(Role.USER, f"message {i}") for i in range(20)]
        result = compressor.compress(messages)

        assert result.compressed
        assert result.original_count == 20
        assert result.compressed_count < 20
        assert len(result.summary) > 0

    def test_compress_small_list_noop(self):
        compressor = ContextCompressor(threshold_messages=100, keep_recent=10)
        messages = [make_msg(Role.USER, f"msg {i}") for i in range(5)]
        result = compressor.compress(messages)

        assert not result.compressed
        assert len(result.messages) == 5

    def test_preserves_recent(self):
        compressor = ContextCompressor(threshold_messages=5, keep_recent=3)
        messages = [make_msg(Role.USER, f"msg {i}") for i in range(10)]
        result = compressor.compress(messages)

        # 最近的消息应该保留
        last_message = result.messages[-1]
        assert "msg 9" in last_message.content

    def test_compression_result_to_dict(self):
        result = CompressionResult(
            messages=[],
            compressed=True,
            summary="test summary",
            original_count=50,
            compressed_count=10,
            summarized_count=40,
        )
        d = result.to_dict()
        assert d["compressed"]
        assert d["original_count"] == 50
        assert "test" in d["summary_preview"]

    def test_get_stats(self):
        compressor = ContextCompressor(max_tokens=10000, threshold_messages=20)
        messages = [make_msg(Role.USER, "hello") for _ in range(30)]
        stats = compressor.get_stats(messages)
        assert stats["message_count"] == 30
        assert stats["needs_compression"]


class TestKnowledgeInjector:
    @pytest.fixture
    def mock_memory(self):
        class MockMemory:
            async def search(self, query, top_k=5, layer=None):
                if layer == "semantic":
                    return [
                        MemoryEntry(
                            layer=MemoryLayer.SEMANTIC,
                            content=f"Knowledge about {query}: fact",
                            importance=0.8,
                        )
                    ]
                elif layer == "procedural":
                    return [
                        MemoryEntry(
                            layer=MemoryLayer.PROCEDURAL,
                            content=f"Pattern for {query}: step-by-step",
                            importance=0.7,
                        )
                    ]
                elif layer == "episodic" or layer == "working":
                    return []
                return []

        return MockMemory()

    @pytest.mark.asyncio
    async def test_inject_knowledge(self, mock_memory):
        injector = KnowledgeInjector(memory_manager=mock_memory)
        context = AgentContext(session_id="test")
        messages = await injector.inject("Python async", context)

        assert len(messages) >= 1
        content = messages[0].content
        assert "Knowledge" in content or "Pattern" in content

    @pytest.mark.asyncio
    async def test_inject_no_memory(self):
        injector = KnowledgeInjector(memory_manager=None)
        context = AgentContext(session_id="test")
        messages = await injector.inject("test", context)
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_inject_empty_query(self, mock_memory):
        injector = KnowledgeInjector(memory_manager=mock_memory)
        context = AgentContext(session_id="test")
        messages = await injector.inject("", context)
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_inject_targeted_layers(self, mock_memory):
        injector = KnowledgeInjector(memory_manager=mock_memory)
        context = AgentContext(session_id="test")
        messages = await injector.inject_targeted("Python", context, layers=["semantic"])
        assert len(messages) >= 1
        assert "Knowledge" in messages[0].content
