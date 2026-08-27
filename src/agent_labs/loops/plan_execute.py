"""
Plan-Execute 循环模式

工作流程：
1. Plan: LLM 将用户任务分解为多个步骤
2. Execute: 逐步执行每个步骤
3. Review: 汇报执行结果，决定是否修订计划

vs ReAct: ReAct 是边想边做，Plan-Execute 是先规划再执行。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class PlanStep:
    """计划步骤"""

    index: int
    description: str
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str = ""
    depends_on: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "status": self.status.value,
            "result": self.result[:200] if self.result else "",
            "error": self.error,
            "depends_on": self.depends_on,
        }


@dataclass
class Plan:
    """执行计划"""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    revision_count: int = 0
    max_revisions: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def completed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.DONE]

    @property
    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    @property
    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.DONE, StepStatus.SKIPPED) for s in self.steps)

    @property
    def needs_revision(self) -> bool:
        return len(self.failed_steps) > 0 and self.revision_count < self.max_revisions

    def get_next_step(self) -> PlanStep | None:
        """获取下一个可执行的步骤（其依赖已完成）"""
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            if self._dependencies_met(step):
                return step
        return None

    def _dependencies_met(self, step: PlanStep) -> bool:
        for dep_idx in step.depends_on:
            dep_step = self.steps[dep_idx] if dep_idx < len(self.steps) else None
            if dep_step is None or dep_step.status != StepStatus.DONE:
                return False
        return True

    @property
    def progress(self) -> float:
        """计算进度 0-1"""
        if not self.steps:
            return 1.0
        done = len(self.completed_steps) + len(
            [s for s in self.steps if s.status == StepStatus.SKIPPED]
        )
        return done / len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "progress": self.progress(),
            "revision_count": self.revision_count,
            "is_complete": self.is_complete,
        }


class PlanExecutor:
    """Plan-Execute 循环执行器

    管理计划的生命周期：创建 → 逐步执行 → 修订 → 完成。

    使用方式：
        executor = PlanExecutor(tool_executor)
        plan = executor.create_plan("Analyze this codebase")
        while not plan.is_complete:
            step = plan.get_next_step()
            await executor.execute_step(plan, step)
    """

    def __init__(self, tool_executor=None, max_revisions: int = 3):
        self.tool_executor = tool_executor
        self.max_revisions = max_revisions

    def create_plan(
        self,
        goal: str,
        steps_desc: list[str] | None = None,
        tool_mapping: dict[str, str] | None = None,
    ) -> Plan:
        """创建一个执行计划

        Args:
            goal: 任务目标
            steps_desc: 步骤描述列表（如果为 None，需要 LLM 生成）
            tool_mapping: 步骤索引到工具名称的映射

        Returns:
            Plan 对象
        """
        tool_mapping = tool_mapping or {}
        plan = Plan(goal=goal, max_revisions=self.max_revisions)

        if steps_desc:
            for i, desc in enumerate(steps_desc):
                step = PlanStep(
                    index=i,
                    description=desc,
                    tool_name=tool_mapping.get(str(i), ""),
                )
                plan.steps.append(step)
        else:
            # 单步骤计划（简单任务）
            plan.steps.append(
                PlanStep(
                    index=0,
                    description=goal,
                )
            )

        logger.info(f"[PlanExecutor] 创建计划: '{goal[:80]}...' ({len(plan.steps)} 步骤)")
        return plan

    async def execute_step(self, plan: Plan, step: PlanStep) -> StepStatus:
        """执行单个步骤

        Args:
            plan: 执行计划
            step: 要执行的步骤

        Returns:
            步骤执行后的状态
        """
        step.status = StepStatus.IN_PROGRESS
        logger.info(f"[PlanExecutor] 执行步骤 {step.index}: {step.description[:80]}")

        try:
            if step.tool_name and self.tool_executor:
                result = await self.tool_executor.execute(step.tool_name, **step.tool_args)
                if result.success:
                    step.status = StepStatus.DONE
                    step.result = result.content
                else:
                    step.status = StepStatus.FAILED
                    step.error = result.error or "Tool execution failed"
            else:
                # 无工具步骤（纯推理步骤）
                step.status = StepStatus.DONE
                step.result = f"Reasoning step completed: {step.description}"

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            logger.error(f"[PlanExecutor] 步骤 {step.index} 失败: {e}")

        plan.current_step = step.index + 1
        return step.status

    async def execute_all(self, plan: Plan) -> Plan:
        """顺序执行所有步骤直到完成或需要修订

        Args:
            plan: 执行计划

        Returns:
            更新后的计划
        """
        while not plan.is_complete:
            step = plan.get_next_step()
            if step is None:
                if plan.needs_revision:
                    logger.info(
                        f"[PlanExecutor] 计划需要修订 (修订次数: {plan.revision_count + 1})"
                    )
                    plan.revision_count += 1
                    # 重试失败的步骤
                    for s in plan.steps:
                        if s.status == StepStatus.FAILED:
                            s.status = StepStatus.PENDING
                            s.error = ""
                else:
                    break
            else:
                await self.execute_step(plan, step)

        logger.info(
            f"[PlanExecutor] 计划执行完成: "
            f"{len(plan.completed_steps)}/{len(plan.steps)} 成功, "
            f"{len(plan.failed_steps)} 失败"
        )
        return plan

    def revise_plan(self, plan: Plan, new_steps: list[str]) -> Plan:
        """修订计划：添加新的步骤

        Args:
            plan: 原计划
            new_steps: 新增步骤描述

        Returns:
            修订后的计划
        """
        start_idx = len(plan.steps)
        for i, desc in enumerate(new_steps):
            plan.steps.append(
                PlanStep(
                    index=start_idx + i,
                    description=desc,
                )
            )
        plan.revision_count += 1
        logger.info(f"[PlanExecutor] 计划修订: +{len(new_steps)} 步骤")
        return plan

    def get_status_report(self, plan: Plan) -> str:
        """生成状态报告"""
        lines = [
            f"## Plan Status: {plan.goal}",
            f"Progress: {plan.progress:.0%} "
            f"({len(plan.completed_steps)}/{len(plan.steps)} steps done)",
            f"Revisions: {plan.revision_count}/{plan.max_revisions}",
            "",
        ]
        for step in plan.steps:
            icon = {
                StepStatus.PENDING: "⬜",
                StepStatus.IN_PROGRESS: "🔄",
                StepStatus.DONE: "✅",
                StepStatus.FAILED: "❌",
                StepStatus.SKIPPED: "⏭️",
            }.get(step.status, "❓")
            lines.append(f"{icon} Step {step.index}: {step.description}")
            if step.error:
                lines.append(f"   Error: {step.error}")

        return "\n".join(lines)
