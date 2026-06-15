"""
Unit tests for tool system
"""

import asyncio

import pytest

from agent_labs.core.types import ToolResult
from agent_labs.tools.base import BaseTool
from agent_labs.tools.executor import ToolExecutor
from agent_labs.tools.registry import ToolRegistry


# ---- Test Tools ----

class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back the input"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo"},
        },
        "required": ["message"],
    }

    async def execute(self, message: str = "", **kwargs) -> ToolResult:
        return ToolResult(success=True, content=f"Echo: {message}")


class FailingTool(BaseTool):
    name = "failer"
    description = "Always fails"
    parameters = {}

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("I always fail")


class SlowTool(BaseTool):
    name = "slowpoke"
    description = "Very slow tool"
    parameters = {}

    async def execute(self, **kwargs) -> ToolResult:
        await asyncio.sleep(10)
        return ToolResult(success=True, content="Done")


# ---- Registry Tests ----

class TestToolRegistry:
    def test_register_tool(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        assert "echo" in registry
        assert len(registry) == 1

    def test_register_duplicate_raises(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(EchoTool())

    def test_unregister_tool(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.unregister("echo")
        assert "echo" not in registry
        assert len(registry) == 0

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        assert registry.list_tools() == ["echo"]

    def test_get_nonexistent(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None


# ---- Executor Tests ----

class TestToolExecutor:
    async def test_execute_success(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        executor = ToolExecutor(registry)

        result = await executor.execute("echo", message="hello")
        assert result.success
        assert "Echo: hello" in result.content
        assert result.duration_ms >= 0

    async def test_execute_not_found(self):
        registry = ToolRegistry()
        executor = ToolExecutor(registry)

        result = await executor.execute("nonexistent")
        assert not result.success
        assert "not found" in result.error

    async def test_execute_with_retries(self):
        registry = ToolRegistry()
        registry.register(FailingTool())
        executor = ToolExecutor(registry, default_retries=2)

        result = await executor.execute("failer")
        assert not result.success
        assert "I always fail" in result.error

    async def test_execute_timeout(self):
        registry = ToolRegistry()
        registry.register(SlowTool())
        executor = ToolExecutor(registry, default_timeout=0.1, default_retries=0)

        result = await executor.execute("slowpoke")
        assert not result.success
        assert "timed out" in result.error.lower()

    def test_get_tool_definitions(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        executor = ToolExecutor(registry)

        definitions = executor.get_tool_definitions()
        assert len(definitions) == 1
        assert definitions[0]["name"] == "echo"
        assert "parameters" in definitions[0]

    async def test_execute_batch(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        executor = ToolExecutor(registry)

        results = await executor.execute_batch([
            {"name": "echo", "args": {"message": "first"}},
            {"name": "echo", "args": {"message": "second"}},
        ])
        assert len(results) == 2
        assert results[0]["name"] == "echo"
        assert results[0]["result"].success
        assert "first" in results[0]["result"].content
        assert "second" in results[1]["result"].content
