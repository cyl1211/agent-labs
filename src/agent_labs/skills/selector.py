"""
技能选择器 — 根据用户查询选择最合适的技能

选择策略（按优先级）：
1. 精确名称匹配（用户显式指定技能名）
2. 关键词触发匹配（基于 triggers 列表）
3. LLM 语义匹配（可选，当关键词匹配不够时）
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseSkill
from .registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillSelector:
    """技能选择器

    根据用户输入选择最合适的技能。

    使用方式：
        selector = SkillSelector(registry)
        skill, confidence = selector.select("分析这段代码")
    """

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def select(
        self,
        query: str,
        min_confidence: float = 0.3,
    ) -> tuple[BaseSkill | None, float, str]:
        """选择最合适的技能

        Args:
            query: 用户查询
            min_confidence: 最低置信度

        Returns:
            (技能, 置信度, 匹配原因)
        """
        # 策略 1: 精确名称匹配
        skill, confidence = self._match_by_name(query)
        if skill:
            return skill, confidence, "exact_name"

        # 策略 2: 关键词触发匹配
        matches = self.registry.find_matching(query, min_confidence)
        if matches:
            skill, confidence = matches[0]
            return skill, confidence, "keyword_trigger"

        # 策略 3: 无匹配，返回默认或空
        return None, 0.0, "no_match"

    def select_top_k(
        self,
        query: str,
        k: int = 3,
        min_confidence: float = 0.2,
    ) -> list[tuple[BaseSkill, float]]:
        """选择 top-k 个匹配技能

        Args:
            query: 用户查询
            k: 返回数量
            min_confidence: 最低置信度

        Returns:
            [(技能, 置信度), ...]
        """
        matches = self.registry.find_matching(query, min_confidence)
        return matches[:k]

    def _match_by_name(self, query: str) -> tuple[BaseSkill | None, float]:
        """通过精确名称匹配

        检查用户是否在查询中显式提到了技能名。
        例如: "用代码分析技能" → 匹配 "代码分析"
        """
        query_lower = query.lower()
        for skill in self.registry.get_all():
            # 检查技能名是否完整出现在查询中
            if skill.name.lower() in query_lower:
                return skill, 1.0
        return None, 0.0

    def get_skill_info(self, name: str) -> dict[str, Any] | None:
        """获取技能信息"""
        skill = self.registry.get(name)
        if skill:
            return skill.to_dict()
        return None
