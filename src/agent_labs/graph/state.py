"""
LangGraph 图状态定义

图状态是整个 Agent 执行过程中流转的核心数据结构。
使用 TypedDict 定义 LangGraph StateGraph 的状态 schema。
"""

from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages

from ..core.types import AgentContext, AgentInput, Message


class GraphState(dict):
    """
    LangGraph 图状态

    使用 dict 类型以兼容 LangGraph 的 StateGraph。
    状态字段通过 Annotated 类型标记 reducer 行为。

    核心字段：
    - messages: 对话历史 (使用 LangGraph 的 add_messages reducer)
    - input: 原始用户输入
    - context: Agent 运行上下文
    - current_thought: 当前推理内容
    - next_action: LLM 决策的下一步动作
    - tool_results: 工具执行结果缓存
    - iteration: 当前迭代次数
    - tokens_used: 已消耗 token 数
    - should_continue: 是否继续循环
    - error: 错误信息
    - output: 最终输出
    """

    # 对话消息 - 使用 add_messages reducer 自动追加
    messages: Annotated[list[Message], add_messages]

    # 原始输入
    input: AgentInput

    # 运行时上下文
    context: AgentContext

    # 当前推理/思考
    current_thought: str

    # LLM 决定的下一个动作: "tool_call" | "answer" | "call_skill" | "ask_human"
    next_action: str

    # 待执行的工具调用列表
    pending_tool_calls: list[dict[str, Any]]

    # 工具执行结果 (tool_name -> result)
    tool_results: dict[str, Any]

    # 循环计数
    iteration: int

    # Token 使用量
    tokens_used: int

    # 是否继续循环
    should_continue: bool

    # 错误信息
    error: str | None

    # 最终输出
    output: str

    # 待审批的操作
    pending_approval: dict[str, Any] | None

    # 元数据
    metadata: dict[str, Any]

    def __init__(
        self,
        messages: list[Message] | None = None,
        input: AgentInput | None = None,
        context: AgentContext | None = None,
        current_thought: str = "",
        next_action: str = "",
        pending_tool_calls: list[dict[str, Any]] | None = None,
        tool_results: dict[str, Any] | None = None,
        iteration: int = 0,
        tokens_used: int = 0,
        should_continue: bool = True,
        error: str | None = None,
        output: str = "",
        pending_approval: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.messages = messages or []
        self.input = input or AgentInput(query="")
        self.context = context or AgentContext(session_id="")
        self.current_thought = current_thought
        self.next_action = next_action
        self.pending_tool_calls = pending_tool_calls or []
        self.tool_results = tool_results or {}
        self.iteration = iteration
        self.tokens_used = tokens_used
        self.should_continue = should_continue
        self.error = error
        self.output = output
        self.pending_approval = pending_approval
        self.metadata = metadata or {}


def create_initial_state(input: AgentInput, context: AgentContext) -> GraphState:
    """创建初始图状态"""
    user_message = Message(
        role="user",
        content=input.query,
        metadata=input.metadata,
    )
    return GraphState(
        messages=[user_message],
        input=input,
        context=context,
        iteration=0,
        tokens_used=0,
        should_continue=True,
    )
