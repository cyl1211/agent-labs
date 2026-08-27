"""Unit tests for long-running task support"""

import tempfile

from agent_labs.long_running.decomposer import (
    LongTask,
    SubTask,
    SubTaskStatus,
    TaskDecomposer,
)


class TestTaskDecomposer:
    def test_decompose_linear(self):
        dec = TaskDecomposer()
        task = dec.decompose("Build app", ["design", "implement", "test"])
        assert task.total_steps == 3
        assert len(task.subtasks) == 3
        assert task.progress == 0.0

    def test_decompose_parallel(self):
        dec = TaskDecomposer()
        task = dec.decompose_parallel("Build", [["a", "b"], ["c"]])
        assert task.total_steps == 3

    def test_decompose_phases(self):
        dec = TaskDecomposer()
        task = dec.decompose_phases("Build", {"Phase1": ["a", "b"], "Phase2": ["c"]})
        assert task.total_steps == 3

    def test_get_next_linear(self):
        dec = TaskDecomposer()
        task = dec.decompose("Test", ["a", "b", "c"])
        st = task.get_next()
        assert st is not None
        assert st.description == "a"

    def test_get_next_with_dependencies(self):
        dec = TaskDecomposer()
        task = dec.decompose("Test", ["a", "b"], dependencies={1: [0]})
        st1 = task.get_next()
        assert st1.description == "a"
        st1.status = SubTaskStatus.COMPLETED
        st2 = task.get_next()
        assert st2.description == "b"

    def test_get_available_parallel(self):
        dec = TaskDecomposer()
        task = dec.decompose_parallel("Test", [["a", "b"]])
        available = task.get_available_parallel()
        assert len(available) == 2

    def test_is_complete(self):
        task = LongTask("Test")
        task.subtasks = [
            SubTask("s0", "a", status=SubTaskStatus.COMPLETED),
            SubTask("s1", "b", status=SubTaskStatus.COMPLETED),
        ]
        assert task.is_complete

    def test_is_stalled(self):
        task = LongTask("Test")
        task.subtasks = [
            SubTask("s0", "a", status=SubTaskStatus.FAILED, attempts=3, max_attempts=3),
        ]
        assert task.is_stalled

    def test_can_retry(self):
        st = SubTask("s0", "a", status=SubTaskStatus.FAILED, attempts=1, max_attempts=3)
        assert st.can_retry

        st2 = SubTask("s1", "b", status=SubTaskStatus.FAILED, attempts=3, max_attempts=3)
        assert not st2.can_retry

    def test_progress(self):
        task = LongTask("Test")
        task.subtasks = [
            SubTask("s0", "a", status=SubTaskStatus.COMPLETED),
            SubTask("s1", "b", status=SubTaskStatus.PENDING),
            SubTask("s2", "c", status=SubTaskStatus.PENDING),
        ]
        task.total_steps = 3
        assert task.progress == 1 / 3

    def test_save_restore_checkpoint(self):
        task = LongTask("Test")
        task.subtasks = [
            SubTask("s0", "a", status=SubTaskStatus.COMPLETED, result="done"),
            SubTask("s1", "b", status=SubTaskStatus.PENDING),
        ]
        task.total_steps = 2

        with tempfile.TemporaryDirectory() as tmp:
            cid = task.save_checkpoint("cp1", checkpoint_dir=tmp)
            assert cid == "cp1"

            task2 = LongTask("Test")
            task2.subtasks = [
                SubTask("s0", "a"),
                SubTask("s1", "b"),
            ]
            ok = task2.restore_from_checkpoint("cp1", checkpoint_dir=tmp)
            assert ok
            assert task2.subtasks[0].status == SubTaskStatus.COMPLETED

    def test_status_report(self):
        task = LongTask("Build")
        task.subtasks = [
            SubTask("s0", "done", status=SubTaskStatus.COMPLETED),
            SubTask("s1", "fail", status=SubTaskStatus.FAILED, error="oops"),
        ]
        task.total_steps = 2
        report = task.get_status_report()
        assert "Build" in report
        assert "50%" in report
        assert "oops" in report
