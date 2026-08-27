"""Unit tests for loop modes"""

import pytest

from agent_labs.loops.plan_execute import Plan, PlanExecutor, PlanStep, StepStatus
from agent_labs.loops.supervisor import (
    Supervisor,
    Worker,
    WorkerStatus,
)


class TestPlanExecutor:
    def test_create_plan(self):
        executor = PlanExecutor()
        plan = executor.create_plan("Test goal", ["step 1", "step 2", "step 3"])
        assert len(plan.steps) == 3
        assert plan.goal == "Test goal"
        assert plan.progress == 0

    def test_plan_get_next_step(self):
        executor = PlanExecutor()
        plan = executor.create_plan("Test", ["a", "b", "c"])
        step = plan.get_next_step()
        assert step is not None
        assert step.index == 0
        assert step.description == "a"

    async def test_execute_step_success(self):
        executor = PlanExecutor()
        plan = executor.create_plan("Test", ["step"])
        step = plan.get_next_step()
        status = await executor.execute_step(plan, step)
        assert status == StepStatus.DONE
        assert len(plan.completed_steps) == 1

    async def test_execute_all(self):
        executor = PlanExecutor()
        plan = executor.create_plan("Test", ["a", "b"])
        plan = await executor.execute_all(plan)
        assert plan.is_complete
        assert len(plan.completed_steps) == 2

    def test_plan_with_dependencies(self):
        plan = Plan(goal="test")
        s0 = PlanStep(index=0, description="setup")
        s1 = PlanStep(index=1, description="main", depends_on=[0])
        plan.steps = [s0, s1]
        s0.status = StepStatus.DONE
        next_step = plan.get_next_step()
        assert next_step is not None
        assert next_step.index == 1

    def test_revise_plan(self):
        executor = PlanExecutor()
        plan = executor.create_plan("Test", ["step 1"])
        plan = executor.revise_plan(plan, ["step 2", "step 3"])
        assert len(plan.steps) == 3
        assert plan.revision_count == 1

    def test_status_report(self):
        executor = PlanExecutor()
        plan = executor.create_plan("Test", ["a", "b"])
        plan.steps[0].status = StepStatus.DONE
        report = executor.get_status_report(plan)
        assert "Test" in report
        assert "50%" in report

    def test_progress(self):
        plan = Plan(goal="test")
        plan.steps = [
            PlanStep(index=0, description="a", status=StepStatus.DONE),
            PlanStep(index=1, description="b", status=StepStatus.PENDING),
        ]
        assert plan.progress == pytest.approx(0.5)


class TestSupervisor:
    def test_create_work(self):
        sup = Supervisor()
        state = sup.create_work("Build app", ["task1", "task2"])
        assert len(state.pending_tasks) == 2
        assert state.goal == "Build app"

    def test_register_worker(self):
        sup = Supervisor()
        state = sup.create_work("Test")
        worker = Worker(name="coder", capabilities=["python"])
        sup.register_worker(state, worker)
        assert "coder" in state.workers
        assert state.workers["coder"].is_available

    def test_assign_task(self):
        sup = Supervisor()
        state = sup.create_work("Test", ["write python code"])
        sup.register_worker(state, Worker("coder", capabilities=["python"]))
        task = state.pending_tasks[0]
        worker = sup.assign_task(state, task)
        assert worker is not None
        assert worker.name == "coder"
        assert worker.status == WorkerStatus.BUSY

    def test_complete_task(self):
        sup = Supervisor()
        state = sup.create_work("Test", ["task1"])
        sup.register_worker(state, Worker("worker1"))
        sup.assign_task(state, state.pending_tasks[0])
        sup.complete_task(state, "task_0", result="done")
        assert len(state.completed_tasks) == 1
        assert state.workers["worker1"].status == WorkerStatus.DONE

    def test_complete_task_with_error(self):
        sup = Supervisor()
        state = sup.create_work("Test", ["task1"])
        sup.register_worker(state, Worker("worker1"))
        sup.assign_task(state, state.pending_tasks[0])
        sup.complete_task(state, "task_0", error="failed")
        assert len(state.failed_tasks) == 1
        assert state.workers["worker1"].tasks_failed == 1

    def test_all_tasks_done(self):
        sup = Supervisor()
        state = sup.create_work("Test", ["task1"])
        sup.register_worker(state, Worker("w"))
        sup.assign_task(state, state.pending_tasks[0])
        sup.complete_task(state, "task_0", result="ok")
        assert state.all_tasks_done

    def test_report(self):
        sup = Supervisor()
        state = sup.create_work("Test", ["task1"])
        sup.register_worker(state, Worker("w"))
        sup.assign_task(state, state.pending_tasks[0])
        sup.complete_task(state, "task_0", result="ok")
        report = sup.get_report(state)
        assert "Test" in report
        assert "w" in report

    def test_worker_success_rate(self):
        w = Worker("test")
        w.tasks_completed = 8
        w.tasks_failed = 2
        assert w.success_rate == 0.8
