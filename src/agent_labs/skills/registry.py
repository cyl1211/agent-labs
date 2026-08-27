"""
技能注册表 — 管理所有技能的生命周期
"""

from __future__ import annotations

from typing import Any

from .base import BaseSkill


class SkillRegistry:
    """技能注册表

    管理所有已注册的技能，支持按名称查找和按查询匹配。
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """注册一个技能

        Args:
            skill: 技能实例

        Raises:
            ValueError: 技能名已存在
        """
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' is already registered")
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        """注销一个技能"""
        self._skills.pop(name, None)

    def get(self, name: str) -> BaseSkill | None:
        """获取技能"""
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """列出所有技能名"""
        return list(self._skills.keys())

    def get_all(self) -> list[BaseSkill]:
        """获取所有技能实例"""
        return list(self._skills.values())

    def find_matching(
        self, query: str, min_confidence: float = 0.3
    ) -> list[tuple[BaseSkill, float]]:
        """查找匹配查询的技能

        Args:
            query: 用户查询
            min_confidence: 最低置信度阈值

        Returns:
            [(技能, 置信度), ...] 按置信度降序排列
        """
        matches: list[tuple[BaseSkill, float]] = []
        for skill in self._skills.values():
            matched, confidence = skill.matches(query)
            if matched and confidence >= min_confidence:
                matches.append((skill, confidence))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def clear(self) -> None:
        """清空注册表"""
        self._skills.clear()

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def to_dict(self) -> dict[str, Any]:
        """序列化所有技能"""
        return {name: skill.to_dict() for name, skill in self._skills.items()}
