"""
Agent 抽象基类

Agent 是最顶层的执行单元，与 Session 和 Memory 完全解耦。
Agent 通过 AgentContext 获取运行时信息，不直接依赖 Session/Memory 的实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .types import AgentContext, AgentEvent, AgentInput, AgentOutput


class BaseAgent(ABC):
    """
    Agent 抽象接口

    设计原则：
    - Agent 只知道"如何执行任务"，不知道"如何存储状态" (Session 负责)
    - Agent 只知道"如何读取记忆"，不知道"如何持久化记忆" (Memory 负责)
    - Agent 通过 AgentContext 获取只读的运行时视图
    - 每个 Agent 实现可以有自己的 LangGraph 图、循环模式

    要实现自定义 Agent，只需继承此类并实现 invoke() 和 stream()。
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    @abstractmethod
    async def invoke(
        self,
        input: AgentInput,
        context: AgentContext,
    ) -> AgentOutput:
        """
        同步执行 Agent，返回最终结果。

        Args:
            input: 用户输入（query, session_id, metadata 等）
            context: 运行时上下文（session 消息历史、memory 查询结果）

        Returns:
            AgentOutput: 包含 answer、tool_calls_made、tokens_used 等
        """
        ...

    @abstractmethod
    async def stream(
        self,
        input: AgentInput,
        context: AgentContext,
    ) -> AsyncIterator[AgentEvent]:
        """
        流式执行 Agent，逐步返回事件。

        事件类型：
        - "thinking": Agent 正在推理 (data: {thought})
        - "tool_call": 调用工具 (data: {name, args})
        - "tool_result": 工具结果 (data: {name, result})
        - "answer": 部分回答 (data: {chunk})
        - "error": 发生错误 (data: {message, code})
        - "human_approval": 需要人工确认 (data: {action, description})

        Args:
            input: 用户输入
            context: 运行时上下文

        Yields:
            AgentEvent: 流式事件
        """
        ...

    @property
    def agent_id(self) -> str:
        """Agent 唯一标识，默认使用类名"""
        return f"{self.__class__.__name__}:{self.name}"

    def __repr__(self) -> str:
        return f"<{self.agent_id}>"
