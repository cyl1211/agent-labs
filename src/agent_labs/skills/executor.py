"""
技能执行器 — 负责技能的调用、工具编排和结果聚合
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..core.types import SkillContext, SkillResult
from ..tools.executor import ToolExecutor
from .base import BaseSkill
from .registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillExecutor:
    """技能执行器

    负责：
    - 根据名称或查询找到并执行技能
    - 在执行前验证所需工具可用
    - 记录执行元数据（耗时、工具调用次数等）

    使用方式：
        executor = SkillExecutor(skill_registry, tool_executor)
        result = await executor.execute("代码分析", context)
    """

    def __init__(
        self,
        skill_registry: SkillRegistry,
        tool_executor: ToolExecutor,
    ):
        self.skill_registry = skill_registry
        self.tool_executor = tool_executor

    async def execute(
        self,
        skill_name: str,
        context: SkillContext,
    ) -> SkillResult:
        """执行指定技能

        Args:
            skill_name: 技能名称
            context: 技能执行上下文

        Returns:
            SkillResult: 执行结果
        """
        skill = self.skill_registry.get(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                content="",
                error=f"技能不存在: {skill_name}。可用技能: {self.skill_registry.list_skills()}",
            )

        # 验证所需工具是否已注册
        missing_tools = self._check_required_tools(skill)
        if missing_tools:
            return SkillResult(
                success=False,
                content="",
                error=f"技能 '{skill_name}' 需要的工具未注册: {missing_tools}",
            )

        start = time.monotonic()
        try:
            result = await skill.execute(context)
        except Exception as e:
            logger.error(f"[SkillExecutor] 技能 '{skill_name}' 执行失败: {e}")
            return SkillResult(
                success=False,
                content="",
                error=f"技能执行异常: {e}",
                metadata={"skill_name": skill_name},
            )

        # 补充元数据
        duration_ms = (time.monotonic() - start) * 1000
        if not result.metadata:
            result.metadata = {}
        result.metadata["skill_name"] = skill_name
        result.metadata["duration_ms"] = duration_ms

        return result

    async def execute_by_query(
        self,
        query: str,
        context: SkillContext,
        min_confidence: float = 0.3,
    ) -> SkillResult:
        """通过查询自动匹配并执行技能

        先使用 SkillSelector 查找最佳匹配，再执行。

        Args:
            query: 用户查询
            context: 执行上下文
            min_confidence: 最低置信度

        Returns:
            SkillResult
        """
        from .selector import SkillSelector

        selector = SkillSelector(self.skill_registry)
        skill, confidence, reason = selector.select(query, min_confidence)

        if not skill:
            return SkillResult(
                success=False,
                content="",
                error=f"未找到匹配 '{query}' 的技能（匹配原因: {reason}）",
            )

        logger.info(
            f"[SkillExecutor] 自动匹配技能: {skill.name} (置信度: {confidence:.2f}, 方式: {reason})"
        )

        return await self.execute(skill.name, context)

    async def execute_sequential(
        self,
        skill_names: list[str],
        context: SkillContext,
    ) -> list[SkillResult]:
        """顺序执行多个技能

        前一个技能的结果会注入到后续技能的 context.params 中。

        Args:
            skill_names: 技能名称列表
            context: 执行上下文

        Returns:
            [SkillResult, ...]
        """
        results: list[SkillResult] = []
        for name in skill_names:
            # 将前一个技能的结果注入 context
            if results:
                prev = results[-1]
                context.params[f"_prev_skill_{name}"] = {
                    "success": prev.success,
                    "content": prev.content,
                }

            result = await self.execute(name, context)
            results.append(result)

            # 如果某个技能失败，停止执行后续技能
            if not result.success:
                logger.warning(f"[SkillExecutor] 技能 '{name}' 失败，停止后续执行")
                break

        return results

    def _check_required_tools(self, skill: BaseSkill) -> list[str]:
        """检查技能的所需工具是否已在 ToolRegistry 中注册"""
        missing = []
        for tool_name in skill.required_tools:
            if self.tool_executor.registry.get(tool_name) is None:
                missing.append(tool_name)
        return missing

    def list_available_skills(self) -> list[dict[str, Any]]:
        """列出所有可用技能及其状态"""
        available = []
        for skill in self.skill_registry.get_all():
            missing = self._check_required_tools(skill)
            available.append(
                {
                    "name": skill.name,
                    "description": skill.description,
                    "ready": len(missing) == 0,
                    "missing_tools": missing,
                }
            )
        return available
