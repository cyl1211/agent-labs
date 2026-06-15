"""
LangGraph 图节点实现

11 个核心节点：
- input_node: 解析/标准化输入
- context_node: 构建上下文（注入 memory + session）
- decide_node: 调用 LLM 决策下一步
- tool_node: 执行工具调用
- skill_node: 执行技能
- memory_node: 读写记忆
- human_node: 人工确认检查点
- notify_node: 发送通知
- output_node: 格式化最终输出
- error_node: 统一错误处理
- loop_node: 循环控制
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..core.types import AgentEvent, Message, Role, ToolResult, new_id, utc_now
from ..models.manager import ModelManager
from .state import GraphState

logger = logging.getLogger(__name__)


class GraphNodes:
    """图节点集合 - 封装所有节点逻辑"""

    def __init__(self, model_manager: ModelManager, tool_executor: Any = None):
        self.model_manager = model_manager
        self.tool_executor = tool_executor

    # ========================================================================
    # INPUT NODE
    # ========================================================================

    async def input_node(self, state: GraphState) -> dict[str, Any]:
        """解析输入，确保消息格式正确"""
        logger.debug(f"[input_node] query: {state['input'].query[:100]}...")

        # 确保系统消息存在
        has_system = any(
            isinstance(m, Message) and m.role == Role.SYSTEM
            for m in state["messages"]
        )
        if not has_system:
            system_msg = Message(
                role=Role.SYSTEM,
                content=self._build_system_prompt(state),
            )
            return {"messages": [system_msg]}

        return {}

    def _build_system_prompt(self, state: GraphState) -> str:
        """构建系统提示词"""
        tools_desc = ""
        if self.tool_executor:
            tool_names = getattr(self.tool_executor, "list_tools", lambda: [])()
            tools_desc = "\n".join(f"- {t}" for t in tool_names)

        return f"""You are an intelligent AI agent. Follow this reasoning pattern:

1. Understand the user's request carefully
2. Break complex tasks into steps
3. Use available tools when needed
4. Report tool results accurately
5. Provide a clear final answer

Available tools:
{tools_desc or "No tools available. Use reasoning only."}

When you complete the task, include "TASK_COMPLETE" in your response.
"""

    # ========================================================================
    # CONTEXT NODE
    # ========================================================================

    async def context_node(self, state: GraphState) -> dict[str, Any]:
        """注入记忆和会话上下文"""
        context = state["context"]
        memories = context.memories if hasattr(context, "memories") else []

        if memories:
            memory_text = "\n".join(
                f"[Memory-{m.layer.value}]: {m.content[:200]}" for m in memories[:5]
            )
            context_msg = Message(
                role=Role.SYSTEM,
                content=f"Relevant memories:\n{memory_text}",
            )
            return {"messages": [context_msg]}

        return {}

    # ========================================================================
    # DECIDE NODE
    # ========================================================================

    async def decide_node(self, state: GraphState) -> dict[str, Any]:
        """调用 LLM 决策下一步动作"""
        messages = state["messages"]
        iteration = state.get("iteration", 0)
        logger.info(f"[decide_node] iteration={iteration}, messages={len(messages)}")

        # 构建工具定义
        tools = []
        if self.tool_executor:
            tools = self.tool_executor.get_tool_definitions()

        try:
            response = await self.model_manager.chat(
                messages=messages,
                temperature=0.7,
                tools=tools if tools else None,
            )

            assistant_message = Message(
                role=Role.ASSISTANT,
                content=response.get("content", ""),
            )

            tool_calls = response.get("tool_calls", [])
            tokens = response.get("usage", {})

            updates: dict[str, Any] = {
                "messages": [assistant_message],
                "current_thought": response.get("content", ""),
            }

            if tool_calls:
                updates["next_action"] = "tool_call"
                updates["pending_tool_calls"] = tool_calls
            elif "TASK_COMPLETE" in response.get("content", "") or "FINAL_ANSWER" in response.get("content", ""):
                updates["next_action"] = "answer"
            else:
                updates["next_action"] = "answer"

            # 累计 token
            new_tokens = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
            updates["tokens_used"] = state.get("tokens_used", 0) + new_tokens

            return updates

        except Exception as e:
            logger.error(f"[decide_node] LLM call failed: {e}")
            return {
                "error": str(e),
                "next_action": "error",
                "current_thought": f"Error during LLM call: {e}",
            }

    # ========================================================================
    # TOOL NODE
    # ========================================================================

    async def tool_node(self, state: GraphState) -> dict[str, Any]:
        """执行工具调用"""
        pending = state.get("pending_tool_calls", [])
        if not pending:
            return {"next_action": "answer"}

        results: dict[str, Any] = {}
        tool_messages: list[Message] = []

        for tool_call in pending:
            tool_name = tool_call.get("name", "unknown")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", new_id())
            logger.info(f"[tool_node] executing: {tool_name}")

            start = time.monotonic()
            try:
                if self.tool_executor:
                    result: ToolResult = await self.tool_executor.execute(tool_name, **tool_args)
                else:
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"No tool executor configured. Tool '{tool_name}' not available.",
                    )
            except Exception as e:
                result = ToolResult(success=False, content="", error=str(e))

            duration_ms = (time.monotonic() - start) * 1000
            result.duration_ms = duration_ms
            results[tool_name] = result

            # 创建工具结果消息
            tool_msg = Message(
                role=Role.TOOL,
                content=result.content if result.success else f"Error: {result.error}",
                tool_name=tool_name,
                tool_call_id=tool_id,
                metadata={"success": result.success, "duration_ms": duration_ms},
            )
            tool_messages.append(tool_msg)

        return {
            "tool_results": {**state.get("tool_results", {}), **results},
            "messages": tool_messages,
            "pending_tool_calls": [],
            "next_action": "decide",  # 返回 decide 评估结果
        }

    # ========================================================================
    # MEMORY NODE
    # ========================================================================

    async def memory_node(self, state: GraphState) -> dict[str, Any]:
        """异步写入记忆（侧边节点，不阻塞主流程）"""
        # 记忆写入在 GraphNodes 层面是轻量操作
        # 实际持久化由 MemoryManager 处理
        logger.debug(f"[memory_node] recording memory for session {state['context'].session_id}")
        return {}

    # ========================================================================
    # HUMAN NODE
    # ========================================================================

    async def human_node(self, state: GraphState) -> dict[str, Any]:
        """人工确认检查点 - 中断图执行等待审批"""
        pending = state.get("pending_approval", {})
        if not pending:
            return {"next_action": "decide"}

        logger.info(f"[human_node] waiting for approval: {pending.get('action', 'unknown')}")

        # 这里 LangGraph 会通过 interrupt 机制暂停
        # 审批通过后继续执行
        return {"next_action": "decide"}

    # ========================================================================
    # NOTIFY NODE
    # ========================================================================

    async def notify_node(self, state: GraphState) -> dict[str, Any]:
        """发送通知（错误、完成等）"""
        error = state.get("error")
        output = state.get("output", "")

        if error:
            logger.warning(f"[notify_node] sending error notification: {error}")
            # TODO: 触发邮件通知
        elif output:
            logger.info(f"[notify_node] task completed for session {state['context'].session_id}")
            # TODO: 触发完成通知

        return {}

    # ========================================================================
    # OUTPUT NODE
    # ========================================================================

    async def output_node(self, state: GraphState) -> dict[str, Any]:
        """格式化最终输出"""
        content = state.get("current_thought", "")

        # 去掉 TASK_COMPLETE 标记
        content = content.replace("TASK_COMPLETE", "").replace("FINAL_ANSWER", "").strip()

        return {
            "output": content,
            "should_continue": False,
        }

    # ========================================================================
    # ERROR NODE
    # ========================================================================

    async def error_node(self, state: GraphState) -> dict[str, Any]:
        """统一错误处理"""
        error = state.get("error", "Unknown error")
        logger.error(f"[error_node] handling error: {error}")

        error_message = Message(
            role=Role.ASSISTANT,
            content=f"I encountered an error: {error}. Let me try a different approach.",
        )

        # 如果超过最大迭代次数，强制终止
        max_iter = state.get("metadata", {}).get("max_iterations", 25)
        if state.get("iteration", 0) >= max_iter:
            return {
                "output": f"Task terminated due to reaching maximum iterations ({max_iter}). Last error: {error}",
                "should_continue": False,
                "messages": [error_message],
            }

        return {
            "messages": [error_message],
            "next_action": "decide",
            "error": None,  # 清除错误，继续尝试
        }

    # ========================================================================
    # LOOP NODE
    # ========================================================================

    async def loop_node(self, state: GraphState) -> dict[str, Any]:
        """循环控制 - 判断终止条件"""
        iteration = state.get("iteration", 0)
        max_iter = state.get("metadata", {}).get("max_iterations", 25)
        error = state.get("error")

        if error:
            return {"should_continue": True, "next_action": "error"}

        if iteration >= max_iter:
            logger.warning(f"[loop_node] max iterations ({max_iter}) reached")
            return {
                "should_continue": False,
                "output": state.get("current_thought", "Maximum iterations reached."),
            }

        # 正常继续
        next_action = state.get("next_action", "decide")
        return {
            "should_continue": True,
            "iteration": iteration + 1,
            "next_action": next_action,
        }
