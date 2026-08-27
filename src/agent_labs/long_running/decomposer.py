"""
长任务支持

提供：
- 任务分解器：将大任务拆分为可管理的子任务
- 检查点持久化：在执行过程中保存状态，支持断点续传
- 进度追踪：跟踪整体任务进度
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SubTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTask:
    """子任务"""

    task_id: str
    description: str
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: str = ""
    error: str = ""
    attempts: int = 0
    max_attempts: int = 3
    started_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts and self.status == SubTaskStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result[:500],
            "error": self.error,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
        }


@dataclass
class Checkpoint:
    """检查点 — 保存任务执行的中间状态"""

    checkpoint_id: str
    task_id: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "task_id": self.task_id,
            "data": self.data,
            "created_at": self.created_at,
        }


class TaskDecomposer:
    """任务分解器

    将大型任务分解为多个子任务，支持：
    - 按步骤分解（线性依赖）
    - 按模块分解（独立并行）
    - 按阶段分解（阶段内有依赖，阶段间串行）

    使用方式：
        decomposer = TaskDecomposer()
        task = decomposer.decompose(
            "Build a web application",
            ["Design API", "Implement models", "Add routes", "Write tests", "Deploy"]
        )
        while not task.is_complete:
            subtask = task.get_next()
            await decomposer.execute_subtask(task, subtask)
    """

    def __init__(self, max_attempts_per_task: int = 3):
        self.max_attempts_per_task = max_attempts_per_task

    def decompose(
        self,
        goal: str,
        steps: list[str],
        dependencies: dict[int, list[int]] | None = None,
    ) -> LongTask:
        """分解任务

        Args:
            goal: 总体目标
            steps: 步骤描述列表
            dependencies: 步骤依赖关系 {step_index: [dep_indices]}

        Returns:
            LongTask
        """
        task = LongTask(goal=goal)

        for i, desc in enumerate(steps):
            deps = dependencies.get(i, []) if dependencies else []
            subtask = SubTask(
                task_id=f"subtask_{i}",
                description=desc,
                max_attempts=self.max_attempts_per_task,
                metadata={"dependencies": deps, "step_index": i},
            )
            task.subtasks.append(subtask)

        task.total_steps = len(task.subtasks)
        logger.info(f"[Decomposer] 任务分解: '{goal[:60]}' → {len(steps)} 子任务")
        return task

    def decompose_parallel(
        self,
        goal: str,
        parallel_groups: list[list[str]],
    ) -> LongTask:
        """按并行组分解任务

        每组内的步骤可并行执行，组间串行。

        Args:
            goal: 总体目标
            parallel_groups: [[group1_steps], [group2_steps], ...]

        Returns:
            LongTask
        """
        task = LongTask(goal=goal)
        step_index = 0

        for group_idx, group in enumerate(parallel_groups):
            for step_desc in group:
                # 同组之间无依赖，依赖前面组的所有步骤
                deps = []
                if group_idx > 0:
                    prev_start = step_index - len(group)
                    deps = list(range(prev_start))

                subtask = SubTask(
                    task_id=f"subtask_{step_index}",
                    description=step_desc,
                    max_attempts=self.max_attempts_per_task,
                    metadata={
                        "group": group_idx,
                        "parallel": True,
                        "dependencies": deps,
                    },
                )
                task.subtasks.append(subtask)
                step_index += 1

        task.total_steps = len(task.subtasks)
        logger.info(
            f"[Decomposer] 并行任务分解: '{goal[:60]}' → "
            f"{len(parallel_groups)} 组 / {task.total_steps} 子任务"
        )
        return task

    def decompose_phases(
        self,
        goal: str,
        phases: dict[str, list[str]],
    ) -> LongTask:
        """按阶段分解任务

        每个阶段包含多个步骤，阶段之间有依赖。

        Args:
            goal: 总体目标
            phases: {"phase_name": [steps]}

        Returns:
            LongTask
        """
        task = LongTask(goal=goal)
        step_index = 0
        phase_boundaries: dict[str, tuple[int, int]] = {}

        for phase_name, steps in phases.items():
            start_idx = step_index
            for step_desc in steps:
                # 阶段内的步骤如果有依赖也是内部的
                if step_index > start_idx:
                    [step_index - 1]
                subtask = SubTask(
                    task_id=f"subtask_{step_index}",
                    description=f"[{phase_name}] {step_desc}",
                    max_attempts=self.max_attempts_per_task,
                    metadata={"phase": phase_name},
                )
                task.subtasks.append(subtask)
                step_index += 1
            phase_boundaries[phase_name] = (start_idx, step_index - 1)

        task.total_steps = len(task.subtasks)
        task.metadata["phase_boundaries"] = phase_boundaries
        logger.info(
            f"[Decomposer] 阶段任务分解: '{goal[:60]}' → "
            f"{len(phases)} 阶段 / {task.total_steps} 子任务"
        )
        return task


class LongTask:
    """长任务 — 管理多个子任务的执行"""

    def __init__(self, goal: str = ""):
        self.goal = goal
        self.task_id = f"longtask_{int(time.monotonic() * 1000)}"
        self.subtasks: list[SubTask] = []
        self.total_steps: int = 0
        self.created_at: str = datetime.now(UTC).isoformat()
        self.completed_at: str = ""
        self.metadata: dict[str, Any] = {}
        self._checkpoints: dict[str, Checkpoint] = {}

    @property
    def completed(self) -> list[SubTask]:
        return [s for s in self.subtasks if s.status == SubTaskStatus.COMPLETED]

    @property
    def failed(self) -> list[SubTask]:
        return [s for s in self.subtasks if s.status == SubTaskStatus.FAILED]

    @property
    def pending(self) -> list[SubTask]:
        return [s for s in self.subtasks if s.status == SubTaskStatus.PENDING]

    @property
    def is_complete(self) -> bool:
        return all(
            s.status in (SubTaskStatus.COMPLETED, SubTaskStatus.SKIPPED) for s in self.subtasks
        )

    @property
    def is_stalled(self) -> bool:
        """是否停滞（有失败且无法重试的步骤）"""
        return any(s.status == SubTaskStatus.FAILED and not s.can_retry for s in self.subtasks)

    @property
    def progress(self) -> float:
        if not self.subtasks:
            return 1.0
        done = len(self.completed) + len(
            [s for s in self.subtasks if s.status == SubTaskStatus.SKIPPED]
        )
        return done / len(self.subtasks)

    def get_next(self) -> SubTask | None:
        """获取下一个可执行的子任务（依赖已满足）"""
        for st in self.subtasks:
            if st.status != SubTaskStatus.PENDING:
                continue
            deps = st.metadata.get("dependencies", [])
            deps_met = all(
                self.subtasks[d].status == SubTaskStatus.COMPLETED
                for d in deps
                if d < len(self.subtasks)
            )
            if deps_met:
                return st
        return None

    def get_available_parallel(self) -> list[SubTask]:
        """获取所有依赖已满足的待执行子任务（用于并行执行）"""
        available = []
        for st in self.subtasks:
            if st.status != SubTaskStatus.PENDING:
                continue
            deps = st.metadata.get("dependencies", [])
            deps_met = all(
                self.subtasks[d].status == SubTaskStatus.COMPLETED
                for d in deps
                if d < len(self.subtasks)
            )
            if deps_met:
                available.append(st)
        return available

    def save_checkpoint(self, name: str = "", checkpoint_dir: str = "") -> str:
        """保存检查点

        Args:
            name: 检查点名称
            checkpoint_dir: 检查点目录

        Returns:
            检查点 ID
        """
        checkpoint_id = name or f"checkpoint_{len(self._checkpoints)}_{int(time.monotonic())}"
        data = self.to_dict()
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            task_id=self.task_id,
            data=data,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._checkpoints[checkpoint_id] = checkpoint

        # 持久化到文件
        if checkpoint_dir:
            self._write_checkpoint_file(checkpoint, checkpoint_dir)

        logger.info(f"[LongTask] 检查点已保存: {checkpoint_id}")
        return checkpoint_id

    def restore_from_checkpoint(self, checkpoint_id: str, checkpoint_dir: str = "") -> bool:
        """从检查点恢复

        Args:
            checkpoint_id: 检查点 ID
            checkpoint_dir: 检查点目录

        Returns:
            是否恢复成功
        """
        # 先尝试从内存
        checkpoint = self._checkpoints.get(checkpoint_id)

        # 再尝试从文件
        if not checkpoint and checkpoint_dir:
            checkpoint = self._read_checkpoint_file(checkpoint_id, checkpoint_dir)

        if not checkpoint:
            logger.warning(f"[LongTask] 检查点不存在: {checkpoint_id}")
            return False

        # 恢复状态
        self.total_steps = checkpoint.data.get("total_steps", self.total_steps)
        self.metadata = checkpoint.data.get("metadata", {})

        restored_subtasks = checkpoint.data.get("subtasks", [])
        for i, st_data in enumerate(restored_subtasks):
            if i < len(self.subtasks):
                self.subtasks[i].status = SubTaskStatus(st_data.get("status", "pending"))
                self.subtasks[i].result = st_data.get("result", "")
                self.subtasks[i].error = st_data.get("error", "")
                self.subtasks[i].attempts = st_data.get("attempts", 0)

        logger.info(f"[LongTask] 从检查点恢复: {checkpoint_id}")
        return True

    def _write_checkpoint_file(self, checkpoint: Checkpoint, checkpoint_dir: str) -> None:
        """将检查点写入文件"""
        path = Path(checkpoint_dir) / f"{checkpoint.checkpoint_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)

    def _read_checkpoint_file(self, checkpoint_id: str, checkpoint_dir: str) -> Checkpoint | None:
        """从文件读取检查点"""
        path = Path(checkpoint_dir) / f"{checkpoint_id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return Checkpoint(
            checkpoint_id=data["checkpoint_id"],
            task_id=data["task_id"],
            data=data["data"],
            created_at=data.get("created_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "total_steps": self.total_steps,
            "progress": self.progress,
            "is_complete": self.is_complete,
            "is_stalled": self.is_stalled,
            "metadata": self.metadata,
        }

    def get_status_report(self) -> str:
        """生成状态报告"""
        if self.is_complete:
            status_text = "Complete"
        elif self.is_stalled:
            status_text = "Stalled"
        else:
            status_text = "Running"
        lines = [
            f"## Long Task: {self.goal}",
            f"Progress: {self.progress:.0%} "
            f"({len(self.completed)}/{len(self.subtasks)} done, "
            f"{len(self.failed)} failed)",
            f"Status: {status_text}",
            "",
        ]
        for st in self.subtasks:
            icon = {
                SubTaskStatus.PENDING: "⬜",
                SubTaskStatus.RUNNING: "🔄",
                SubTaskStatus.COMPLETED: "✅",
                SubTaskStatus.FAILED: "❌",
                SubTaskStatus.SKIPPED: "⏭️",
            }.get(st.status, "❓")
            retry_info = f" ({st.attempts}/{st.max_attempts})" if st.attempts > 0 else ""
            lines.append(f"{icon} {st.description}{retry_info}")
            if st.error:
                lines.append(f"   Error: {st.error[:100]}")
        return "\n".join(lines)
