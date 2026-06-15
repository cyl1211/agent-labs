"""
LangGraph 图构建器

将配置编译为可执行的 LangGraph StateGraph。
支持三种循环模式：
- ReAct: decide ⇄ tool
- Plan-Execute: plan → execute → review
- Supervisor: supervisor ⇄ workers
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .nodes import GraphNodes
from .state import GraphState

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    图构建工厂

    使用方式：
        nodes = GraphNodes(model_manager, tool_executor)
        builder = GraphBuilder(nodes)
        graph = builder.build_react_graph()
        # 或: graph = builder.build_plan_execute_graph()
        # 或: graph = builder.build_supervisor_graph()
    """

    def __init__(self, nodes: GraphNodes):
        self.nodes = nodes
        self._checkpointer = MemorySaver()

    def build_react_graph(self, enable_human_loop: bool = False) -> StateGraph:
        """
        构建 ReAct (Reasoning + Acting) 循环图

        图结构：
            input → context → decide
                              ├→ tool → memory → loop → decide
                              ├→ human (if enabled) → loop → decide
                              └→ output → notify → END

        特点：
        - 每次迭代经过 decide → tool → loop
        - 工具结果返回 decide 重新评估
        - 支持人工确认中断
        """
        workflow = StateGraph(GraphState)

        # 注册节点
        workflow.add_node("input", self.nodes.input_node)
        workflow.add_node("context", self.nodes.context_node)
        workflow.add_node("decide", self.nodes.decide_node)
        workflow.add_node("tool", self.nodes.tool_node)
        workflow.add_node("memory", self.nodes.memory_node)
        workflow.add_node("output", self.nodes.output_node)
        workflow.add_node("notify", self.nodes.notify_node)
        workflow.add_node("error", self.nodes.error_node)
        workflow.add_node("loop", self.nodes.loop_node)

        if enable_human_loop:
            workflow.add_node("human", self.nodes.human_node)

        # 入口
        workflow.set_entry_point("input")

        # 主流程: input → context → decide
        workflow.add_edge("input", "context")
        workflow.add_edge("context", "decide")

        # decide 条件路由
        workflow.add_conditional_edges(
            "decide",
            self._route_after_decide,
            {
                "tool": "tool",
                "human": "human" if enable_human_loop else "output",
                "answer": "output",
                "error": "error",
            },
        )

        # tool → memory → loop
        workflow.add_edge("tool", "memory")
        workflow.add_edge("memory", "loop")

        # loop 条件路由
        workflow.add_conditional_edges(
            "loop",
            self._route_after_loop,
            {
                "decide": "decide",
                "error": "error",
                "end": END,
            },
        )

        if enable_human_loop:
            workflow.add_edge("human", "loop")

        # error → loop (允许重试) 或 → notify → END
        workflow.add_conditional_edges(
            "error",
            self._route_after_error,
            {
                "loop": "loop",
                "end": "notify",
            },
        )

        # output → notify → END
        workflow.add_edge("output", "notify")
        workflow.add_edge("notify", END)

        return workflow.compile(checkpointer=self._checkpointer)

    def build_plan_execute_graph(self) -> StateGraph:
        """
        构建 Plan-Execute 循环图

        图结构：
            input → plan → [execute_step_1, execute_step_2, ...] → review → output

        特点：
        - 先制定计划，再逐步执行
        - 每步执行后汇总评估
        - 支持计划修订

        注意：此模式较复杂，Phase 1 先提供框架，后续完善。
        """
        workflow = StateGraph(GraphState)

        workflow.add_node("input", self.nodes.input_node)
        workflow.add_node("context", self.nodes.context_node)
        workflow.add_node("decide", self.nodes.decide_node)
        workflow.add_node("tool", self.nodes.tool_node)
        workflow.add_node("output", self.nodes.output_node)
        workflow.add_node("error", self.nodes.error_node)

        workflow.set_entry_point("input")
        workflow.add_edge("input", "context")
        workflow.add_edge("context", "decide")

        workflow.add_conditional_edges(
            "decide",
            self._route_after_decide,
            {"tool": "tool", "answer": "output", "error": "error"},
        )

        workflow.add_conditional_edges(
            "tool",
            self._route_after_tool,
            {"decide": "decide", "output": "output", "error": "error"},
        )

        workflow.add_edge("output", END)
        workflow.add_edge("error", END)

        return workflow.compile(checkpointer=self._checkpointer)

    def build_supervisor_graph(self) -> StateGraph:
        """
        构建 Supervisor 多 Agent 协调图（框架）

        图结构：
            supervisor → [worker_a, worker_b, ...] → supervisor → output

        特点：
        - Supervisor 负责任务分配
        - 每个 Worker 是独立 Agent
        - 通过 subgraph 实现子 Agent 隔离

        注意：Phase 4 完整实现。
        """
        workflow = StateGraph(GraphState)

        workflow.add_node("input", self.nodes.input_node)
        workflow.add_node("decide", self.nodes.decide_node)
        workflow.add_node("tool", self.nodes.tool_node)
        workflow.add_node("output", self.nodes.output_node)
        workflow.add_node("error", self.nodes.error_node)

        workflow.set_entry_point("input")
        workflow.add_edge("input", "decide")

        workflow.add_conditional_edges(
            "decide",
            self._route_after_decide,
            {"tool": "tool", "answer": "output", "error": "error"},
        )

        workflow.add_conditional_edges(
            "tool",
            self._route_after_tool,
            {"decide": "decide", "output": "output", "error": "error"},
        )

        workflow.add_edge("output", END)
        workflow.add_edge("error", END)

        return workflow.compile(checkpointer=self._checkpointer)

    # ========================================================================
    # 路由函数
    # ========================================================================

    def _route_after_decide(self, state: GraphState) -> str:
        """decide 节点后的路由"""
        next_action = state.get("next_action", "answer")

        if state.get("error"):
            return "error"

        if next_action == "tool_call":
            return "tool"
        elif next_action == "answer":
            content = state.get("current_thought", "")
            # 检查是否需要人工确认
            if "APPROVAL_NEEDED" in content:
                return "human"
            return "answer"
        return "answer"

    def _route_after_tool(self, state: GraphState) -> str:
        """tool 节点后的路由"""
        if state.get("error"):
            return "error"

        # 检查是否所有工具都已执行
        next_action = state.get("next_action", "decide")
        if next_action == "answer":
            return "output"
        return "decide"

    def _route_after_loop(self, state: GraphState) -> str:
        """loop 节点后的路由"""
        should_continue = state.get("should_continue", False)
        next_action = state.get("next_action", "decide")

        if not should_continue:
            return "end"

        if next_action == "error":
            return "error"

        return "decide"

    def _route_after_error(self, state: GraphState) -> str:
        """error 节点后的路由"""
        should_continue = state.get("should_continue", False)
        if should_continue:
            return "loop"
        return "end"
