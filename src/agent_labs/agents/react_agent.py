"""
ReAct (Reasoning + Acting) Agent 实现

最经典的 Agent 模式：思考 → 行动 → 观察 → 思考... 直到得到最终答案。

基于 LangGraph 的 StateGraph 构建，支持：
- 工具调用
- 失败重试
- 循环终止条件
- 流式输出
- 人工确认中断
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator

from langgraph.errors import GraphRecursionError

from ..core.base_agent import BaseAgent
from ..core.types import (
    AgentContext,
    AgentEvent,
    AgentInput,
    AgentOutput,
    Message,
    Role,
    new_id,
    utc_now,
)
from ..graph.builder import GraphBuilder
from ..graph.nodes import GraphNodes
from ..graph.state import create_initial_state
from ..models.manager import ModelManager
from ..tools.executor import ToolExecutor

logger = logging.getLogger(__name__)


class ReactAgent(BaseAgent):
    """
    ReAct Agent

    工作流程：
    1. 接收用户输入
    2. LLM 思考 + 决策 (调用工具 or 给出答案)
    3. 如有工具调用 → 执行工具 → 结果返回 LLM
    4. 循环直到 LLM 给出最终答案或达到终止条件

    Agent、Session、Memory 解耦：
    - Agent 通过 AgentContext 获取运行时信息
    - Agent 不直接操作 Session（通过 context.messages）
    - Agent 不直接操作 Memory（通过 context.memories）
    """

    def __init__(
        self,
        name: str = "react",
        description: str = "ReAct agent with tool calling",
        model_manager: ModelManager | None = None,
        tool_executor: ToolExecutor | None = None,
        max_iterations: int = 25,
    ):
        super().__init__(name=name, description=description)
        self.model_manager = model_manager or ModelManager()
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self._graph = None

    def _get_graph(self, enable_human_loop: bool = False):
        """懒加载编译好的 LangGraph 图"""
        if self._graph is None:
            nodes = GraphNodes(self.model_manager, self.tool_executor)
            builder = GraphBuilder(nodes)
            self._graph = builder.build_react_graph(enable_human_loop=enable_human_loop)
        return self._graph

    async def invoke(
        self,
        input: AgentInput,
        context: AgentContext,
    ) -> AgentOutput:
        """
        同步执行 Agent

        Args:
            input: 用户输入
            context: 运行时上下文（含 session messages 和 memory entries）

        Returns:
            AgentOutput: 包含 answer、tool_calls_made、tokens_used 等
        """
        start_time = time.monotonic()
        session_id = context.session_id or new_id()
        graph = self._get_graph()

        # 在 context metadata 中放入 max_iterations
        context.metadata["max_iterations"] = self.max_iterations

        initial_state = create_initial_state(input, context)
        initial_state["metadata"] = context.metadata

        # 编译配置
        config = {
            "configurable": {
                "thread_id": session_id,
                "max_iterations": self.max_iterations,
            },
            "recursion_limit": self.max_iterations + 5,
        }

        try:
            final_state = await graph.ainvoke(initial_state, config)
        except GraphRecursionError as e:
            logger.warning(f"[ReactAgent] max recursion reached: {e}")
            return AgentOutput(
                session_id=session_id,
                answer="Task exceeded maximum iterations. Partial results returned.",
                iterations=self.max_iterations,
                duration_ms=(time.monotonic() - start_time) * 1000,
                metadata={"error": "max_recursion"},
            )

        duration_ms = (time.monotonic() - start_time) * 1000

        # 收集工具调用信息
        tool_calls_made = []
        for msg in final_state.get("messages", []):
            if isinstance(msg, Message) and msg.role == Role.TOOL:
                tool_calls_made.append({
                    "name": msg.tool_name,
                    "success": msg.metadata.get("success", False),
                    "duration_ms": msg.metadata.get("duration_ms", 0),
                })

        return AgentOutput(
            session_id=session_id,
            answer=final_state.get("output", "") or final_state.get("current_thought", ""),
            tool_calls_made=tool_calls_made,
            iterations=final_state.get("iteration", 0),
            tokens_used=final_state.get("tokens_used", 0),
            duration_ms=duration_ms,
            metadata={
                "error": final_state.get("error"),
                "next_action": final_state.get("next_action", ""),
            },
        )

    async def stream(
        self,
        input: AgentInput,
        context: AgentContext,
    ) -> AsyncIterator[AgentEvent]:
        """
        流式执行 Agent

        逐步返回事件：
        - thinking: Agent 推理过程
        - tool_call: 调用了工具
        - tool_result: 工具执行结果
        - answer: 最终答案（最后一条）
        - error: 发生错误
        """
        session_id = context.session_id or new_id()
        graph = self._get_graph()

        context.metadata["max_iterations"] = self.max_iterations
        initial_state = create_initial_state(input, context)
        initial_state["metadata"] = context.metadata

        config = {
            "configurable": {
                "thread_id": session_id,
                "max_iterations": self.max_iterations,
            },
            "recursion_limit": self.max_iterations + 5,
        }

        try:
            async for event in graph.astream_events(initial_state, config, version="v2"):
                event_type = event.get("event", "")
                event_name = event.get("name", "")

                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield AgentEvent(
                            event_type="thinking",
                            data={"thought": chunk.content},
                        )

                elif event_type == "on_tool_start":
                    yield AgentEvent(
                        event_type="tool_call",
                        data={
                            "name": event_name,
                            "input": event.get("data", {}).get("input", {}),
                        },
                    )

                elif event_type == "on_tool_end":
                    output = event.get("data", {}).get("output", {})
                    yield AgentEvent(
                        event_type="tool_result",
                        data={"name": event_name, "result": str(output)},
                    )

                elif event_type == "on_chain_end" and event_name == "LangGraph":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict) and output.get("output"):
                        yield AgentEvent(
                            event_type="answer",
                            data={"answer": output["output"]},
                        )

        except GraphRecursionError as e:
            yield AgentEvent(
                event_type="error",
                data={"message": f"Max recursion reached: {e}"},
            )

    async def cleanup(self) -> None:
        """清理资源"""
        self._graph = None
