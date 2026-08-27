"""
Unit tests for skill system
"""

import pytest

from agent_labs.core.types import SkillContext, SkillResult, ToolResult
from agent_labs.skills.base import BaseSkill
from agent_labs.skills.executor import SkillExecutor
from agent_labs.skills.registry import SkillRegistry
from agent_labs.skills.selector import SkillSelector
from agent_labs.tools.base import BaseTool
from agent_labs.tools.executor import ToolExecutor
from agent_labs.tools.registry import ToolRegistry

# ---- Test Skill ----


class GreetSkill(BaseSkill):
    name = "greet"
    description = "Greet the user"
    triggers = ["hello", "hi", "greet", "你好", "打招呼"]
    required_tools = ["echo"]

    async def execute(self, context: SkillContext) -> SkillResult:
        name = context.params.get("name", "World")
        echo_result = context.tool_results.get("echo")
        if echo_result:
            return SkillResult(
                success=True,
                content=f"Greeting: {echo_result.content}",
                tool_calls=[{"tool": "echo", "purpose": "echo greeting"}],
            )
        return SkillResult(
            success=True,
            content=f"Hello, {name}!",
        )


class AnalysisSkill(BaseSkill):
    name = "analysis"
    description = "Analyze something"
    triggers = ["分析", "analyze", "review"]
    required_tools = ["read_file"]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(
            success=True,
            content="Analysis complete",
            tool_calls=[],
        )


# ---- Test Tools for Skills ----


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
        },
        "required": ["message"],
    }

    async def execute(self, message: str = "", **kwargs) -> ToolResult:
        return ToolResult(success=True, content=f"Echo: {message}")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    }

    async def execute(self, path: str = "", **kwargs) -> ToolResult:
        return ToolResult(success=True, content=f"Content of {path}")


# ---- Registry Tests ----


class TestSkillRegistry:
    def test_register_skill(self):
        registry = SkillRegistry()
        registry.register(GreetSkill())
        assert "greet" in registry
        assert len(registry) == 1

    def test_register_duplicate_raises(self):
        registry = SkillRegistry()
        registry.register(GreetSkill())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(GreetSkill())

    def test_unregister_skill(self):
        registry = SkillRegistry()
        registry.register(GreetSkill())
        registry.unregister("greet")
        assert "greet" not in registry

    def test_list_skills(self):
        registry = SkillRegistry()
        registry.register(GreetSkill())
        assert "greet" in registry.list_skills()

    def test_find_matching_exact(self):
        registry = SkillRegistry()
        registry.register(GreetSkill())
        registry.register(AnalysisSkill())

        matches = registry.find_matching("hello world")
        assert len(matches) >= 1
        assert matches[0][0].name == "greet"

    def test_find_matching_no_match(self):
        registry = SkillRegistry()
        registry.register(GreetSkill())

        matches = registry.find_matching("xyz unknown query")
        assert len(matches) == 0

    def test_find_matching_chinese(self):
        registry = SkillRegistry()
        registry.register(AnalysisSkill())

        matches = registry.find_matching("请分析这段代码")
        assert len(matches) >= 1
        assert matches[0][0].name == "analysis"

    def test_to_dict(self):
        registry = SkillRegistry()
        registry.register(GreetSkill())
        d = registry.to_dict()
        assert "greet" in d
        assert d["greet"]["name"] == "greet"


# ---- Selector Tests ----


class TestSkillSelector:
    @pytest.fixture
    def registry(self):
        reg = SkillRegistry()
        reg.register(GreetSkill())
        reg.register(AnalysisSkill())
        return reg

    def test_select_by_trigger(self, registry):
        selector = SkillSelector(registry)
        skill, confidence, reason = selector.select("hello there")
        assert skill is not None
        assert skill.name == "greet"
        assert confidence > 0
        assert reason == "keyword_trigger"

    def test_select_by_exact_name(self, registry):
        selector = SkillSelector(registry)
        skill, confidence, reason = selector.select("用 greet 技能")
        assert skill is not None
        assert skill.name == "greet"
        assert confidence == 1.0
        assert reason == "exact_name"

    def test_select_no_match(self, registry):
        selector = SkillSelector(registry)
        skill, confidence, reason = selector.select("random query")
        assert skill is None
        assert reason == "no_match"

    def test_select_top_k(self, registry):
        selector = SkillSelector(registry)
        results = selector.select_top_k("hello 分析", k=2)
        assert len(results) == 2

    def test_get_skill_info(self, registry):
        selector = SkillSelector(registry)
        info = selector.get_skill_info("greet")
        assert info is not None
        assert info["name"] == "greet"


# ---- Executor Tests ----


class TestSkillExecutor:
    @pytest.fixture
    def tool_registry(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        reg.register(ReadFileTool())
        return reg

    @pytest.fixture
    def tool_executor(self, tool_registry):
        return ToolExecutor(tool_registry)

    @pytest.fixture
    def skill_registry(self):
        reg = SkillRegistry()
        reg.register(GreetSkill())
        reg.register(AnalysisSkill())
        return reg

    @pytest.fixture
    def executor(self, skill_registry, tool_executor):
        return SkillExecutor(skill_registry, tool_executor)

    async def test_execute_success(self, executor):
        context = SkillContext(
            session_id="test-123",
            params={"name": "Alice"},
        )
        result = await executor.execute("greet", context)
        assert result.success
        assert "Hello" in result.content or "Alice" in result.content

    async def test_execute_skill_not_found(self, executor):
        context = SkillContext(session_id="test-123")
        result = await executor.execute("nonexistent", context)
        assert not result.success
        assert "不存在" in result.error

    async def test_execute_by_query(self, executor):
        context = SkillContext(session_id="test-123")
        result = await executor.execute_by_query("hello world", context)
        assert result.success

    async def test_execute_by_query_no_match(self, executor):
        context = SkillContext(session_id="test-123")
        result = await executor.execute_by_query("xyz no match", context)
        assert not result.success
        assert "未找到匹配" in result.error

    async def test_list_available_skills(self, executor):
        available = executor.list_available_skills()
        assert len(available) == 2
        greet_info = [s for s in available if s["name"] == "greet"][0]
        assert greet_info["ready"] is True  # EchoTool is registered

    def test_skill_to_dict(self):
        skill = GreetSkill()
        d = skill.to_dict()
        assert d["name"] == "greet"
        assert "echo" in d["required_tools"]
        assert "hello" in d["triggers"]
