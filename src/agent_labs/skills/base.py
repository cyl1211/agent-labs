"""
技能抽象基类

技能是多个工具调用的编排组合。一个技能定义了：
- 名称、描述
- 触发关键词（用于自动匹配）
- 所需工具列表
- 执行逻辑（工具调用序列）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.types import SkillContext, SkillResult


class BaseSkill(ABC):
    """技能抽象基类

    子类需要定义:
    - name: 技能名称
    - description: 技能描述
    - triggers: 触发关键词列表
    - required_tools: 所需工具名列表
    - execute(): 执行逻辑
    """

    name: str = ""
    description: str = ""
    triggers: list[str] = []
    required_tools: list[str] = []

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """执行技能

        Args:
            context: 技能执行上下文，包含 session_id、agent_context、
                     tool_results、params

        Returns:
            SkillResult: 执行结果
        """
        ...

    def matches(self, query: str) -> tuple[bool, float]:
        """检查查询是否匹配此技能

        Args:
            query: 用户查询文本

        Returns:
            (是否匹配, 置信度 0-1)
        """
        query_lower = query.lower()
        matched = 0
        total = len(self.triggers)

        if total == 0:
            return False, 0.0

        for trigger in self.triggers:
            if trigger.lower() in query_lower:
                matched += 1

        if matched == 0:
            return False, 0.0

        # 基础置信度 0.5，最多匹配全部触发词时达到 1.0
        # 这避免了多语言触发器（中英文混合）导致置信度过低的问题
        confidence = 0.5 + 0.5 * (matched / total)
        return True, confidence

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "required_tools": self.required_tools,
        }

    def __repr__(self) -> str:
        return f"<Skill(name={self.name!r})>"
