"""
Supervisor 多 Agent 协调循环

Supervisor 模式：
- Supervisor Agent: 负责任务分解和分配
- Worker Agents: 执行具体的子任务
- 通过消息传递协调多个 Agent

工作流程：
1. Supervisor 分析任务，分配给合适的 Worker
2. Worker 独立执行子任务
3. Supervisor 汇总结果并决策下一步
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class WorkerStatus(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    DONE = "done"
    ERROR = "error"


class TaskPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class WorkerTask:
    """分配给 Worker 的子任务"""

    task_id: str
    description: str
    priority: TaskPriority = TaskPriority.NORMAL
    assigned_worker: str = ""
    result: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "priority": self.priority.name,
            "assigned_worker": self.assigned_worker,
            "result": self.result[:200],
            "error": self.error,
        }


@dataclass
class Worker:
    """Worker Agent 描述"""

    name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    status: WorkerStatus = WorkerStatus.IDLE
    current_task: WorkerTask | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0

    @property
    def is_available(self) -> bool:
        return self.status in (WorkerStatus.IDLE, WorkerStatus.DONE)

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total > 0 else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "success_rate": self.success_rate,
        }


@dataclass
class SupervisorState:
    """Supervisor 的运行状态"""

    goal: str
    workers: dict[str, Worker] = field(default_factory=dict)
    pending_tasks: list[WorkerTask] = field(default_factory=list)
    completed_tasks: list[WorkerTask] = field(default_factory=list)
    failed_tasks: list[WorkerTask] = field(default_factory=list)
    current_round: int = 0
    max_rounds: int = 10

    @property
    def all_tasks_done(self) -> bool:
        return len(self.pending_tasks) == 0 and all(
            w.status != WorkerStatus.BUSY for w in self.workers.values()
        )

    @property
    def available_workers(self) -> list[Worker]:
        return [w for w in self.workers.values() if w.is_available]

    @property
    def progress(self) -> float:
        total = len(self.completed_tasks) + len(self.failed_tasks) + len(self.pending_tasks)
        return (len(self.completed_tasks) + len(self.failed_tasks)) / max(total, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "workers": {n: w.to_dict() for n, w in self.workers.items()},
            "pending_tasks": len(self.pending_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "current_round": self.current_round,
            "progress": self.progress,
        }


class Supervisor:
    """Supervisor 协调器

    管理多 Agent 的任务分配和执行。

    使用方式：
        supervisor = Supervisor()
        supervisor.register_worker(Worker("coder", capabilities=["python", "debug"]))
        state = supervisor.create_work("Build a web app")
        while not state.all_tasks_done:
            supervisor.assign_next(state)
    """

    def __init__(self, max_rounds: int = 10):
        self.max_rounds = max_rounds

    def create_work(self, goal: str, tasks_desc: list[str] | None = None) -> SupervisorState:
        """创建工作状态

        Args:
            goal: 总体目标
            tasks_desc: 子任务描述列表

        Returns:
            SupervisorState
        """
        state = SupervisorState(goal=goal, max_rounds=self.max_rounds)

        if tasks_desc:
            for i, desc in enumerate(tasks_desc):
                state.pending_tasks.append(
                    WorkerTask(
                        task_id=f"task_{i}",
                        description=desc,
                    )
                )

        logger.info(f"[Supervisor] 创建工作: '{goal[:80]}' ({len(state.pending_tasks)} 子任务)")
        return state

    def register_worker(self, state: SupervisorState, worker: Worker) -> None:
        """注册一个 Worker

        Args:
            state: Supervisor 状态
            worker: Worker 实例
        """
        state.workers[worker.name] = worker
        logger.info(f"[Supervisor] 注册 Worker: {worker.name} ({worker.capabilities})")

    def assign_task(
        self,
        state: SupervisorState,
        task: WorkerTask,
    ) -> Worker | None:
        """为任务分配合适的 Worker

        策略：优先选择具备匹配能力的空闲 Worker。

        Args:
            state: Supervisor 状态
            task: 要分配的任务

        Returns:
            分配的 Worker，或 None（无可用 Worker）
        """
        available = state.available_workers
        if not available:
            logger.debug("[Supervisor] 无可用 Worker")
            return None

        # 按能力匹配度排序
        scored: list[tuple[float, Worker]] = []
        task_keywords = set(task.description.lower().split())

        for worker in available:
            score = 0.0
            for cap in worker.capabilities:
                if cap.lower() in task.description.lower():
                    score += 2.0
                for kw in task_keywords:
                    if kw in cap.lower():
                        score += 1.0
            score += worker.success_rate * 0.5
            scored.append((score, worker))

        scored.sort(key=lambda x: x[0], reverse=True)

        if scored and scored[0][0] > 0:
            best_worker = scored[0][1]
            task.assigned_worker = best_worker.name
            best_worker.status = WorkerStatus.BUSY
            best_worker.current_task = task
            logger.info(f"[Supervisor] 分配 '{task.description[:60]}' → {best_worker.name}")
            return best_worker

        # 无障碍匹配，分配给第一个可用 Worker
        first = available[0]
        task.assigned_worker = first.name
        first.status = WorkerStatus.BUSY
        first.current_task = task
        logger.info(f"[Supervisor] 分配 '{task.description[:60]}' → {first.name} (fallback)")
        return first

    def complete_task(
        self, state: SupervisorState, task_id: str, result: str = "", error: str = ""
    ) -> None:
        """标记任务完成

        Args:
            state: Supervisor 状态
            task_id: 任务 ID
            result: 执行结果
            error: 错误信息
        """
        # 查找任务
        task = None
        for t in state.pending_tasks:
            if t.task_id == task_id:
                task = t
                state.pending_tasks.remove(t)
                break

        if task is None:
            logger.warning(f"[Supervisor] 未找到任务: {task_id}")
            return

        task.result = result
        task.error = error

        if error:
            state.failed_tasks.append(task)
        else:
            state.completed_tasks.append(task)

        # 释放 Worker
        worker = state.workers.get(task.assigned_worker)
        if worker:
            worker.status = WorkerStatus.DONE if not error else WorkerStatus.IDLE
            if error:
                worker.tasks_failed += 1
            else:
                worker.tasks_completed += 1
            worker.current_task = None

        logger.info(f"[Supervisor] 任务 {task_id} {'失败' if error else '完成'}")

    def assign_next(self, state: SupervisorState) -> WorkerTask | None:
        """分配下一个待处理的任务

        Args:
            state: Supervisor 状态

        Returns:
            被分配的任务，或 None
        """
        if not state.pending_tasks:
            return None

        if state.current_round >= state.max_rounds:
            logger.warning("[Supervisor] 达到最大轮次")
            return None

        # 按优先级排序
        state.pending_tasks.sort(key=lambda t: t.priority.value, reverse=True)
        task = state.pending_tasks[0]
        worker = self.assign_task(state, task)

        if worker is None:
            return None

        state.current_round += 1
        return task

    def get_report(self, state: SupervisorState) -> str:
        """生成协调报告"""
        lines = [
            f"## Supervisor Report: {state.goal}",
            f"Round: {state.current_round}/{state.max_rounds}",
            f"Workers: {len(state.workers)} ({len(state.available_workers)} available)",
            (
                f"Tasks: {len(state.completed_tasks)} done / "
                f"{len(state.failed_tasks)} failed / "
                f"{len(state.pending_tasks)} pending"
            ),
            "",
            "### Workers",
        ]
        for worker in state.workers.values():
            icon = "🟢" if worker.is_available else "🔴"
            lines.append(
                f"{icon} {worker.name}: {worker.tasks_completed} done, "
                f"{worker.tasks_failed} failed ({worker.success_rate:.0%} success)"
            )

        if state.completed_tasks:
            lines.append("")
            lines.append("### Completed Tasks")
            for t in state.completed_tasks[-5:]:
                lines.append(f"- [{t.assigned_worker}] {t.description[:80]}")

        if state.failed_tasks:
            lines.append("")
            lines.append("### Failed Tasks")
            for t in state.failed_tasks:
                lines.append(f"- [{t.assigned_worker}] {t.description[:80]}: {t.error}")

        return "\n".join(lines)
