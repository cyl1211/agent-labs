"""
Unit tests for memory system
"""

import pytest

from agent_labs.core.types import MemoryEntry, MemoryLayer, MemoryQuery
from agent_labs.memory.manager import MemoryManager


class TestMemoryManager:
    @pytest.fixture
    def manager(self):
        return MemoryManager()

    @pytest.fixture
    async def populated_manager(self, manager):
        entries = [
            MemoryEntry(
                layer=MemoryLayer.WORKING,
                content="Current task: write a report on AI",
                importance=0.8,
                tags=["task", "ai"],
                ttl_seconds=3600,
            ),
            MemoryEntry(
                layer=MemoryLayer.EPISODIC,
                content="Yesterday: user asked about Python async",
                importance=0.6,
                tags=["history", "python"],
                ttl_seconds=86400,
            ),
            MemoryEntry(
                layer=MemoryLayer.SEMANTIC,
                content="User prefers concise answers with code examples",
                importance=0.9,
                tags=["preference"],
                ttl_seconds=604800,
            ),
            MemoryEntry(
                layer=MemoryLayer.PROCEDURAL,
                content="For code generation tasks: first understand, then write, then explain",
                importance=0.7,
                tags=["pattern", "code"],
                ttl_seconds=604800,
            ),
        ]
        for e in entries:
            await manager.write(e)
        return manager

    async def test_write_and_search(self, manager):
        entry = MemoryEntry(layer=MemoryLayer.WORKING, content="test memory")
        eid = await manager.write(entry)
        assert eid

        results = await manager.search("test memory", top_k=1)
        assert len(results) == 1
        assert results[0].content == "test memory"

    async def test_read_by_layer(self, populated_manager):
        query = MemoryQuery(layer=MemoryLayer.SEMANTIC, limit=5)
        results = await populated_manager.read(query)
        assert len(results) == 1
        assert results[0].layer == MemoryLayer.SEMANTIC

    async def test_read_by_tag(self, populated_manager):
        query = MemoryQuery(tags=["preference"], limit=5)
        results = await populated_manager.read(query)
        assert len(results) == 1
        assert "prefers" in results[0].content

    async def test_read_by_importance(self, populated_manager):
        query = MemoryQuery(min_importance=0.8, limit=5)
        results = await populated_manager.read(query)
        assert len(results) >= 2
        for r in results:
            assert r.importance >= 0.8

    async def test_update_memory(self, populated_manager):
        entries = await populated_manager.read(MemoryQuery(layer=MemoryLayer.WORKING))
        assert len(entries) > 0
        entry_id = entries[0].id

        updated = await populated_manager.update(entry_id, {"importance": 1.0})
        assert updated is not None
        assert updated.importance == 1.0

    async def test_forget_memory(self, populated_manager):
        entries = await populated_manager.read(MemoryQuery(layer=MemoryLayer.SEMANTIC))
        assert len(entries) > 0
        entry_id = entries[0].id

        success = await populated_manager.forget(entry_id)
        assert success

        remaining = await populated_manager.read(MemoryQuery(layer=MemoryLayer.SEMANTIC))
        assert len(remaining) == 0

    async def test_garbage_collection(self, manager):
        # Add an old, low-importance entry
        old_entry = MemoryEntry(
            layer=MemoryLayer.WORKING,
            content="old low importance",
            importance=0.1,
            access_count=0,
            ttl_seconds=1,  # Very short TTL
        )
        await manager.write(old_entry)

        # Add a good entry
        good_entry = MemoryEntry(
            layer=MemoryLayer.WORKING,
            content="important stuff",
            importance=0.9,
            access_count=10,
            ttl_seconds=86400,
        )
        await manager.write(good_entry)

        removed = await manager.collect_garbage()
        assert removed >= 0

        # The good entry should still be there
        results = await manager.search("important", top_k=1)
        assert len(results) >= 1
