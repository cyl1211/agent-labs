"""
记忆管理器实现

内置实现，基于嵌入向量 + 关键词的记忆存储。
实现 BaseMemory 接口，四层记忆架构。
"""

from __future__ import annotations

import logging

from ..core.base_memory import BaseMemory
from ..core.types import (
    MemoryEntry,
    MemoryQuery,
    utc_now,
)
from .layers.episodic import EpisodicMemory
from .layers.procedural import ProceduralMemory
from .layers.semantic import SemanticMemory
from .layers.working import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryManager(BaseMemory):
    """
    内置记忆管理器

    四层记忆架构，每层有独立实现：
    1. working (WorkingMemory): FIFO 队列，快速读写，会话级
    2. episodic (EpisodicMemory): 对话摘要，按会话分组，时间衰减
    3. semantic (SemanticMemory): 长期事实/知识，冲突检测，高持久性
    4. procedural (ProceduralMemory): 成功模式，标签分类，强化学习

    存储策略：
    - 每层独立管理自己的存储和淘汰策略
    - 当前阶段使用内存结构，后续可无缝切换后端
    - 通过 BaseMemory 接口统一对外暴露
    """

    def __init__(
        self,
        working_max_entries: int = 50,
        episodic_max_entries: int = 1000,
        semantic_max_entries: int = 5000,
        procedural_max_entries: int = 500,
    ):
        self._working = WorkingMemory(max_entries=working_max_entries)
        self._episodic = EpisodicMemory(max_entries=episodic_max_entries)
        self._semantic = SemanticMemory(max_entries=semantic_max_entries)
        self._procedural = ProceduralMemory(max_entries=procedural_max_entries)

        # 层名到层实例的映射
        self._layers: dict[
            str, WorkingMemory | EpisodicMemory | SemanticMemory | ProceduralMemory
        ] = {
            "working": self._working,
            "episodic": self._episodic,
            "semantic": self._semantic,
            "procedural": self._procedural,
        }

        # 兼容旧接口的 stores 视图
        self._stores: dict[str, list] = {
            "working": [],
            "episodic": [],
            "semantic": [],
            "procedural": [],
        }

    # ---- 层访问器 ----

    @property
    def working(self) -> WorkingMemory:
        """工作记忆层"""
        return self._working

    @property
    def episodic(self) -> EpisodicMemory:
        """情景记忆层"""
        return self._episodic

    @property
    def semantic(self) -> SemanticMemory:
        """语义记忆层"""
        return self._semantic

    @property
    def procedural(self) -> ProceduralMemory:
        """程序记忆层"""
        return self._procedural

    def _get_layer(self, layer_name: str):
        """获取指定名称的层实例"""
        layer = self._layers.get(layer_name)
        if layer is None:
            raise ValueError(f"Unknown memory layer: {layer_name}")
        return layer

    async def write(self, entry: MemoryEntry) -> str:
        """写入一条记忆

        根据 entry.layer 自动路由到对应的记忆层。
        """
        layer = self._get_layer(entry.layer.value)
        return layer.write(entry)

    async def read(self, query: MemoryQuery) -> list[MemoryEntry]:
        """按条件读取记忆

        可以限定单一层或跨所有层查询。
        """
        if query.layer:
            layer = self._get_layer(query.layer.value)
            return layer.read(query)

        # 跨所有层查询
        results = []
        for layer in self._layers.values():
            results.extend(layer.read(query))

        # 按重要性排序
        results.sort(key=lambda e: (e.importance, e.last_accessed_at), reverse=True)
        return results[: query.limit]

    async def search(
        self, query: str, top_k: int = 5, layer: str | None = None
    ) -> list[MemoryEntry]:
        """
        语义搜索记忆

        委托给各层实现，跨层聚合结果。
        """
        if layer:
            layer_instance = self._get_layer(layer)
            return layer_instance.search(query, top_k)

        # 跨所有层搜索并聚合
        all_results: list[tuple[float, MemoryEntry]] = []
        for layer_name, layer_instance in self._layers.items():
            layer_results = layer_instance.search(query, top_k)
            # 重新打分以跨层比较
            for i, entry in enumerate(layer_results):
                # 越靠前的结果分数越高
                layer_weight = {
                    "working": 1.2,  # 工作记忆最相关
                    "episodic": 0.9,
                    "semantic": 0.8,
                    "procedural": 1.0,
                }.get(layer_name, 1.0)
                score = (top_k - i) * layer_weight
                all_results.append((score, entry))

        all_results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in all_results[:top_k]]

    async def update(self, entry_id: str, updates: dict) -> MemoryEntry | None:
        """更新记忆条目"""
        for layer in self._layers.values():
            if entry_id in getattr(layer, "_entries", {}):
                entry = layer._entries.get(entry_id)
                if entry:
                    updated_data = entry.model_dump()
                    updated_data.update(updates)
                    updated_data["last_accessed_at"] = utc_now()
                    new_entry = MemoryEntry(**updated_data)
                    layer._entries[entry_id] = new_entry
                    return new_entry
        return None

    async def forget(self, entry_id: str) -> bool:
        """删除一条记忆"""
        return any(layer.forget(entry_id) for layer in self._layers.values())

    async def collect_garbage(self) -> int:
        """垃圾回收：清理所有层的过期和低质量记忆"""
        total_removed = 0
        for _, layer in self._layers.items():
            removed = layer.collect_garbage()
            total_removed += removed

        logger.info(f"Memory GC: 总计移除 {total_removed} 条")
        return total_removed

    async def summarize_episode(
        self, session_id: str, messages: list, importance: float = 0.5
    ) -> str:
        """将消息历史总结为情景记忆

        委托给情景记忆层进行摘要。
        """
        return self._episodic.summarize_session(session_id, messages, importance)

    # ---- 扩展方法 ----

    def get_session_episodes(self, session_id: str) -> list[MemoryEntry]:
        """获取指定会话的情景记忆"""
        return self._episodic.get_by_session(session_id)

    def get_procedural_patterns(self, pattern_type: str) -> list[MemoryEntry]:
        """获取指定类型的程序记忆模式"""
        return self._procedural.get_by_pattern_type(pattern_type)

    def get_semantic_facts(self, top_k: int = 10) -> list[MemoryEntry]:
        """获取最重要的语义记忆"""
        return self._semantic.get_facts(top_k)

    def reinforce_pattern(self, entry_id: str, success: bool = True) -> bool:
        """强化或弱化一个程序记忆模式"""
        return self._procedural.reinforce(entry_id, success)

    def extract_procedural_pattern(
        self,
        content: str,
        pattern_type: str,
        tags: list[str] | None = None,
        importance: float = 0.6,
    ) -> str:
        """从经验中提取程序记忆模式"""
        return self._procedural.extract_pattern(content, pattern_type, tags, importance)
