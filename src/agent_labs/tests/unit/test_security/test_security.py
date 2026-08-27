"""Unit tests for security sandbox and timeout"""

import pytest

from agent_labs.security.sandbox import (
    ProcessSandbox,
    SandboxConfig,
    SandboxFactory,
)
from agent_labs.security.timeout import TimeoutConfig, TimeoutManager


class TestProcessSandbox:
    @pytest.fixture
    def sandbox(self):
        return ProcessSandbox(SandboxConfig(timeout_seconds=10))

    async def test_execute_code(self, sandbox):
        result = await sandbox.execute(code="print('hello')")
        assert result.success
        assert "hello" in result.stdout
        assert result.exit_code == 0

    async def test_execute_command(self, sandbox):
        result = await sandbox.execute(command="echo test_output")
        assert result.success
        assert "test_output" in result.stdout

    async def test_execute_code_error(self, sandbox):
        result = await sandbox.execute(code="raise ValueError('test error')")
        assert not result.success
        assert result.exit_code != 0

    async def test_execute_empty(self, sandbox):
        result = await sandbox.execute()
        assert not result.success
        assert "No code" in result.error

    async def test_sandbox_factory(self):
        ps = SandboxFactory.create(SandboxConfig(mode="process"))
        assert isinstance(ps, ProcessSandbox)

        ds = SandboxFactory.create(SandboxConfig(mode="docker"))
        from agent_labs.security.sandbox import DockerSandbox

        assert isinstance(ds, DockerSandbox)


class TestTimeoutManager:
    def test_config_defaults(self):
        config = TimeoutConfig()
        assert config.tool_timeout_seconds == 60
        assert config.task_timeout_seconds == 36000

    def test_get_tool_timeout(self):
        mgr = TimeoutManager()
        assert mgr.get_tool_timeout("execute_command") == 120
        assert mgr.get_tool_timeout("read_file") == 30
        assert mgr.get_tool_timeout("unknown_tool") == 60

    async def test_run_with_timeout_ok(self):
        mgr = TimeoutManager()
        import asyncio

        result = await mgr.run_with_timeout(asyncio.sleep(0.01), name="quick", timeout_seconds=5)
        assert result is None  # sleep returns None

    async def test_run_with_timeout_exceeded(self):
        mgr = TimeoutManager()
        import asyncio

        with pytest.raises(asyncio.TimeoutError):
            await mgr.run_with_timeout(
                asyncio.sleep(10),
                name="slow",
                timeout_seconds=0.01,
            )

    async def test_run_with_timeout_fallback(self):
        mgr = TimeoutManager()
        import asyncio

        result = await mgr.run_with_timeout(
            asyncio.sleep(10),
            name="slow",
            timeout_seconds=0.01,
            on_timeout=lambda: "fallback",
        )
        assert result == "fallback"

    def test_get_timeout_stats(self):
        mgr = TimeoutManager()
        stats = mgr.get_timeout_stats()
        assert stats["total_timeouts"] == 0
