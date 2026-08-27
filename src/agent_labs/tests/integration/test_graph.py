"""Graph 集成测试 — 验证 LangGraph 图编译和执行"""

import pytest

from agent_labs.core.types import AgentContext, AgentInput, Role
from agent_labs.graph.state import create_initial_state


class TestGraphCompilation:
    def test_build_react_graph(self):
        """验证 ReAct 图可以成功编译"""
        from agent_labs.graph.builder import GraphBuilder
        from agent_labs.graph.nodes import GraphNodes
        from agent_labs.models.manager import ModelManager

        nodes = GraphNodes(ModelManager())
        builder = GraphBuilder(nodes)
        graph = builder.build_react_graph()
        assert graph is not None

    def test_build_react_graph_with_skill(self):
        """验证带 skill_node 的图可以编译"""
        from agent_labs.graph.builder import GraphBuilder
        from agent_labs.graph.nodes import GraphNodes
        from agent_labs.models.manager import ModelManager

        nodes = GraphNodes(ModelManager())
        builder = GraphBuilder(nodes)
        graph = builder.build_react_graph(enable_skill_node=True)
        assert graph is not None

    def test_build_react_graph_with_human_loop(self):
        """验证带 human_node 的图可以编译"""
        from agent_labs.graph.builder import GraphBuilder
        from agent_labs.graph.nodes import GraphNodes
        from agent_labs.models.manager import ModelManager

        nodes = GraphNodes(ModelManager())
        builder = GraphBuilder(nodes)
        graph = builder.build_react_graph(enable_human_loop=True)
        assert graph is not None

    def test_build_all_graphs(self):
        """验证所有图模式都可以编译"""
        from agent_labs.graph.builder import GraphBuilder
        from agent_labs.graph.nodes import GraphNodes
        from agent_labs.models.manager import ModelManager

        nodes = GraphNodes(ModelManager())
        builder = GraphBuilder(nodes)

        for g in [
            builder.build_react_graph(),
            builder.build_react_graph(enable_human_loop=True),
            builder.build_react_graph(enable_skill_node=True),
            builder.build_plan_execute_graph(),
            builder.build_supervisor_graph(),
        ]:
            assert g is not None


class TestGraphState:
    def test_create_initial_state(self):
        inp = AgentInput(query="test query")
        ctx = AgentContext(session_id="test-sess")
        state = create_initial_state(inp, ctx)
        assert state["input"].query == "test query"
        assert state["context"].session_id == "test-sess"
        assert state["iteration"] == 0
        assert len(state["messages"]) == 1
        assert state["messages"][0].role == Role.USER


class TestGraphNodesIsolated:
    """测试各节点的独立行为（不依赖 LLM）"""

    @pytest.fixture
    def nodes(self):
        from agent_labs.graph.nodes import GraphNodes
        from agent_labs.models.manager import ModelManager

        return GraphNodes(ModelManager())

    @pytest.fixture
    def state(self):
        inp = AgentInput(query="test")
        ctx = AgentContext(session_id="test")
        return create_initial_state(inp, ctx)

    async def test_input_node(self, nodes, state):
        result = await nodes.input_node(state)
        assert isinstance(result, dict)

    async def test_context_node(self, nodes, state):
        result = await nodes.context_node(state)
        assert isinstance(result, dict)

    async def test_output_node(self, nodes, state):
        state["current_thought"] = "TASK_COMPLETE The answer is 42"
        result = await nodes.output_node(state)
        assert "output" in result
        assert "TASK_COMPLETE" not in result.get("output", "")

    async def test_error_node(self, nodes, state):
        state["error"] = "test error"
        state["metadata"] = {"max_iterations": 25}
        result = await nodes.error_node(state)
        assert "messages" in result

    async def test_loop_node_continue(self, nodes, state):
        state["iteration"] = 0
        state["metadata"] = {"max_iterations": 25}
        result = await nodes.loop_node(state)
        assert result["should_continue"]

    async def test_loop_node_max(self, nodes, state):
        state["iteration"] = 25
        state["metadata"] = {"max_iterations": 25}
        result = await nodes.loop_node(state)
        assert not result["should_continue"]

    async def test_memory_node(self, nodes, state):
        result = await nodes.memory_node(state)
        assert isinstance(result, dict)


class TestBuiltinToolsIntegration:
    """验证内置工具可以被正确注册和执行"""

    def test_all_tools_registered(self):
        from agent_labs.tools.builtin import register_all_builtin_tools
        from agent_labs.tools.registry import ToolRegistry

        registry = ToolRegistry()
        register_all_builtin_tools(registry)
        assert len(registry) == 4

    async def test_read_file_tool(self):
        import os
        import tempfile

        from agent_labs.tools.builtin.read_file import ReadFileTool

        tool = ReadFileTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            path = f.name
        try:
            result = await tool.execute(path=path)
            assert result.success
            assert "test content" in result.content
        finally:
            os.unlink(path)


class TestSkillIntegration:
    """验证技能注册和执行"""

    def test_skills_registered(self):
        from agent_labs.skills.builtin import register_all_builtin_skills
        from agent_labs.skills.registry import SkillRegistry

        registry = SkillRegistry()
        register_all_builtin_skills(registry)
        assert len(registry) >= 1
