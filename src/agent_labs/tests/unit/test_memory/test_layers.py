"""
Unit tests for memory layers
"""

from agent_labs.core.types import MemoryEntry, MemoryLayer, MemoryQuery
from agent_labs.memory.layers.episodic import EpisodicMemory
from agent_labs.memory.layers.procedural import ProceduralMemory
from agent_labs.memory.layers.semantic import SemanticMemory
from agent_labs.memory.layers.working import WorkingMemory
from agent_labs.memory.manager import MemoryManager


def make_entry(layer: MemoryLayer, content: str, **kwargs) -> MemoryEntry:
    """Helper to create memory entries"""
    defaults = {
        "layer": layer,
        "content": content,
        "importance": 0.5,
        "tags": [],
        "ttl_seconds": 86400,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


class TestWorkingMemory:
    async def test_write_and_read(self):
        wm = WorkingMemory(max_entries=10)
        entry = make_entry(MemoryLayer.WORKING, "current task info")
        wm.write(entry)

        results = wm.read(MemoryQuery(limit=5))
        assert len(results) == 1
        assert results[0].content == "current task info"

    async def test_get_recent(self):
        wm = WorkingMemory(max_entries=10)
        for i in range(5):
            wm.write(make_entry(MemoryLayer.WORKING, f"task {i}"))

        recent = wm.get_recent(2)
        assert len(recent) == 2
        assert "task 4" in recent[-1].content

    async def test_capacity_eviction(self):
        wm = WorkingMemory(max_entries=3)
        for i in range(5):
            wm.write(make_entry(MemoryLayer.WORKING, f"task {i}"))

        assert len(wm) == 3
        # 最旧的应该被淘汰
        all_content = [e.content for e in wm.get_all()]
        assert "task 0" not in all_content
        assert "task 4" in all_content

    async def test_search(self):
        wm = WorkingMemory()
        wm.write(make_entry(MemoryLayer.WORKING, "Python async programming"))
        wm.write(make_entry(MemoryLayer.WORKING, "JavaScript fetch API"))
        wm.write(make_entry(MemoryLayer.WORKING, "Python pandas tutorial"))

        results = wm.search("Python programming", top_k=2)
        assert len(results) >= 1
        assert any("Python" in r.content for r in results)

    async def test_forget(self):
        wm = WorkingMemory()
        entry = make_entry(MemoryLayer.WORKING, "to be removed")
        eid = wm.write(entry)

        assert wm.forget(eid)
        assert len(wm) == 0
        assert not wm.forget("nonexistent")

    async def test_clear(self):
        wm = WorkingMemory()
        for i in range(3):
            wm.write(make_entry(MemoryLayer.WORKING, f"task {i}"))

        removed = wm.clear()
        assert removed == 3
        assert len(wm) == 0

    async def test_tag_search(self):
        wm = WorkingMemory()
        wm.write(make_entry(MemoryLayer.WORKING, "task A", tags=["python", "async"]))
        wm.write(make_entry(MemoryLayer.WORKING, "task B", tags=["javascript"]))

        results = wm.read(MemoryQuery(tags=["python"], limit=5))
        assert len(results) == 1
        assert "task A" in results[0].content


class TestEpisodicMemory:
    async def test_write_and_read(self):
        em = EpisodicMemory()
        entry = make_entry(MemoryLayer.EPISODIC, "conversation about AI")
        em.write(entry)

        results = em.read(MemoryQuery(limit=5))
        assert len(results) == 1
        assert "AI" in results[0].content

    async def test_session_grouping(self):
        em = EpisodicMemory()
        for i in range(3):
            entry = make_entry(
                MemoryLayer.EPISODIC,
                f"episode {i}",
                tags=[f"session:sess_{i % 2}"],
            )
            em.write(entry)

        sess_0 = em.get_by_session("sess_0")
        sess_1 = em.get_by_session("sess_1")
        assert len(sess_0) >= 1
        assert len(sess_1) >= 1

    async def test_summarize_session(self):
        em = EpisodicMemory(max_entries=100)
        messages = [
            type("Msg", (), {"content": "Hello"})(),
            type("Msg", (), {"content": "How to use async?"})(),
            type("Msg", (), {"content": "Here is the answer"})(),
        ]
        eid = em.summarize_session("sess_test", messages, importance=0.7)
        assert eid

        episodes = em.get_by_session("sess_test")
        assert len(episodes) == 1
        assert "async" in episodes[0].content.lower()

    async def test_importance_search(self):
        em = EpisodicMemory()
        em.write(make_entry(MemoryLayer.EPISODIC, "low priority", importance=0.3))
        em.write(make_entry(MemoryLayer.EPISODIC, "high priority", importance=0.9))

        results = em.read(MemoryQuery(min_importance=0.5, limit=5))
        assert len(results) == 1
        assert "high" in results[0].content

    async def test_capacity_eviction(self):
        em = EpisodicMemory(max_entries=3)
        for i in range(5):
            em.write(
                make_entry(
                    MemoryLayer.EPISODIC,
                    f"episode {i}",
                    importance=0.5 + i * 0.1,
                )
            )

        assert len(em) == 3


class TestSemanticMemory:
    async def test_write_and_read(self):
        sm = SemanticMemory()
        entry = make_entry(MemoryLayer.SEMANTIC, "User prefers Python over JavaScript")
        sm.write(entry)

        results = sm.read(MemoryQuery(limit=5))
        assert len(results) == 1

    async def test_deduplication(self):
        sm = SemanticMemory(similarity_threshold=0.5)
        eid1 = sm.write(make_entry(MemoryLayer.SEMANTIC, "Python async programming guide"))
        eid2 = sm.write(make_entry(MemoryLayer.SEMANTIC, "Python async programming tutorial"))

        # 第二个应该合并到第一个（和并更新）
        assert eid1 == eid2  # 返回的是已有条目的 ID
        assert len(sm) == 1

    async def test_relevance_scoring(self):
        sm = SemanticMemory()
        sm.write(make_entry(MemoryLayer.SEMANTIC, "FastAPI web framework usage", importance=0.8))
        sm.write(make_entry(MemoryLayer.SEMANTIC, "Django ORM tutorial", importance=0.6))
        sm.write(make_entry(MemoryLayer.SEMANTIC, "JavaScript React hooks", importance=0.5))

        results = sm.search("FastAPI web Python", top_k=2)
        assert len(results) >= 1
        assert "FastAPI" in results[0].content

    async def test_get_facts(self):
        sm = SemanticMemory()
        sm.write(make_entry(MemoryLayer.SEMANTIC, "fact A", importance=0.9))
        sm.write(make_entry(MemoryLayer.SEMANTIC, "fact B", importance=0.5))
        sm.write(make_entry(MemoryLayer.SEMANTIC, "fact C", importance=0.7))

        facts = sm.get_facts(top_k=2)
        assert len(facts) == 2
        assert facts[0].importance >= facts[1].importance

    async def test_forget(self):
        sm = SemanticMemory()
        entry = make_entry(MemoryLayer.SEMANTIC, "to forget")
        eid = sm.write(entry)
        assert sm.forget(eid)
        assert len(sm) == 0


class TestProceduralMemory:
    async def test_write_pattern(self):
        pm = ProceduralMemory(min_importance=0.5)
        entry = make_entry(
            MemoryLayer.PROCEDURAL,
            "For code generation: first understand, then write",
            importance=0.7,
            tags=["reasoning", "code"],
        )
        eid = pm.write(entry)
        assert eid

        results = pm.read(MemoryQuery(limit=5))
        assert len(results) == 1

    async def test_reject_low_importance(self):
        pm = ProceduralMemory(min_importance=0.6)
        entry = make_entry(
            MemoryLayer.PROCEDURAL,
            "low importance pattern",
            importance=0.3,
        )
        eid = pm.write(entry)
        assert eid == ""  # 拒绝
        assert len(pm) == 0

    async def test_tag_deduplication(self):
        pm = ProceduralMemory(min_importance=0.5)
        pm.write(
            make_entry(
                MemoryLayer.PROCEDURAL,
                "pattern v1",
                importance=0.6,
                tags=["reasoning"],
            )
        )
        pm.write(
            make_entry(
                MemoryLayer.PROCEDURAL,
                "pattern v2 improved",
                importance=0.7,
                tags=["reasoning"],
            )
        )

        # 相同标签应该更新而非新增
        assert len(pm) == 1

    async def test_reinforce(self):
        pm = ProceduralMemory(min_importance=0.5)
        entry = make_entry(
            MemoryLayer.PROCEDURAL,
            "test pattern",
            importance=0.6,
            tags=["workflow"],
        )
        eid = pm.write(entry)

        original = pm._entries[eid]
        assert pm.reinforce(eid, success=True)
        assert pm._entries[eid].importance > original.importance

    async def test_get_by_pattern_type(self):
        pm = ProceduralMemory(min_importance=0.5)
        pm.write(
            make_entry(
                MemoryLayer.PROCEDURAL,
                "reasoning pattern",
                importance=0.7,
                tags=["reasoning"],
            )
        )
        pm.write(
            make_entry(
                MemoryLayer.PROCEDURAL,
                "tool chain pattern",
                importance=0.7,
                tags=["tool_chain"],
            )
        )

        reasoning = pm.get_by_pattern_type("reasoning")
        tool_chain = pm.get_by_pattern_type("tool_chain")
        assert len(reasoning) == 1
        assert len(tool_chain) == 1

    async def test_extract_pattern(self):
        pm = ProceduralMemory(min_importance=0.5)
        eid = pm.extract_pattern(
            "First check types, then validate, then execute",
            pattern_type="workflow",
            tags=["validation"],
            importance=0.7,
        )
        assert eid
        pattern = pm.get_by_pattern_type("workflow")
        assert len(pattern) == 1


class TestMemoryManagerWithLayers:
    """验证 MemoryManager 正确委托到各层"""

    async def test_write_routes_to_correct_layer(self):
        mm = MemoryManager()
        entry = make_entry(MemoryLayer.WORKING, "test")
        await mm.write(entry)
        assert len(mm.working) == 1

    async def test_search_cross_layer(self):
        mm = MemoryManager()
        await mm.write(make_entry(MemoryLayer.WORKING, "Python async", importance=0.8))
        await mm.write(make_entry(MemoryLayer.SEMANTIC, "Python basics", importance=0.7))
        await mm.write(make_entry(MemoryLayer.PROCEDURAL, "Python patterns", importance=0.9))

        results = await mm.search("Python", top_k=10)
        assert len(results) >= 2

    async def test_layer_accessors(self):
        mm = MemoryManager()
        assert isinstance(mm.working, WorkingMemory)
        assert isinstance(mm.episodic, EpisodicMemory)
        assert isinstance(mm.semantic, SemanticMemory)
        assert isinstance(mm.procedural, ProceduralMemory)

    async def test_get_session_episodes(self):
        mm = MemoryManager()
        await mm.write(
            make_entry(
                MemoryLayer.EPISODIC,
                "test episode",
                tags=["session:test123"],
            )
        )
        episodes = mm.get_session_episodes("test123")
        assert len(episodes) == 1

    async def test_extract_procedural_pattern(self):
        mm = MemoryManager()
        eid = mm.extract_procedural_pattern(
            "test workflow pattern",
            pattern_type="workflow",
            importance=0.7,
        )
        assert eid
        patterns = mm.get_procedural_patterns("workflow")
        assert len(patterns) == 1
