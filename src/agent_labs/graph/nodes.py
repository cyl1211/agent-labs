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

from ..core.types import (
    Message,
    Role,
    ToolResult,
    new_id,
)
from ..models.manager import ModelManager
from .state import GraphState

logger = logging.getLogger(__name__)


class GraphNodes:
    """图节点集合 - 封装所有节点逻辑"""

    def __init__(
        self,
        model_manager: ModelManager,
        tool_executor: Any = None,
        context_builder: Any = None,
        context_compressor: Any = None,
        knowledge_injector: Any = None,
        tracer: Any = None,
        token_monitor: Any = None,
        approval_manager: Any = None,
        email_notifier: Any = None,
        timeout_manager: Any = None,
        skill_executor: Any = None,
        memory_manager: Any = None,
    ):
        self.model_manager = model_manager
        self.tool_executor = tool_executor
        self.context_builder = context_builder
        self.context_compressor = context_compressor
        self.knowledge_injector = knowledge_injector
        self.tracer = tracer
        self.token_monitor = token_monitor
        self.approval_manager = approval_manager
        self.email_notifier = email_notifier
        self.timeout_manager = timeout_manager
        self.skill_executor = skill_executor
        self.memory_manager = memory_manager

    # ========================================================================
    # INPUT NODE
    # ========================================================================

    async def input_node(self, state: GraphState) -> dict[str, Any]:
        """解析输入，确保消息格式正确"""
        logger.debug(f"[input_node] query: {state['input'].query[:100]}...")

        # 确保系统消息存在
        has_system = any(
            isinstance(m, Message) and m.role == Role.SYSTEM for m in state["messages"]
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
        """注入记忆和会话上下文

        使用 ContextBuilder + KnowledgeInjector 替代内联实现：
        1. 使用 ContextCompressor 检查是否需要压缩对话历史
        2. 使用 KnowledgeInjector 动态检索相关知识
        3. 使用 ContextBuilder 构建结构化上下文
        """
        context = state["context"]
        result: dict[str, Any] = {}

        # 1. 压缩超长对话历史（如果启用）
        if self.context_compressor:
            messages = state.get("messages", [])
            if self.context_compressor.should_compress(messages):
                compression_result = self.context_compressor.compress(messages)
                if compression_result.compressed:
                    result["messages"] = compression_result.messages
                    logger.info(
                        f"[context_node] 对话已压缩: "
                        f"{compression_result.original_count} → "
                        f"{compression_result.compressed_count} 条消息"
                    )

        # 2. 动态知识注入
        if self.knowledge_injector and self.memory_manager:
            query = state["input"].query
            try:
                knowledge_msgs = await self.knowledge_injector.inject(query, context)
                if knowledge_msgs:
                    existing = result.get("messages", [])
                    result["messages"] = existing + knowledge_msgs
                    logger.debug(f"[context_node] 注入 {len(knowledge_msgs)} 条知识消息")
            except Exception as e:
                logger.warning(f"[context_node] 知识注入失败: {e}")

        # 3. 使用 ContextBuilder 构建结构化上下文
        memories = context.memories if hasattr(context, "memories") else []
        if memories and self.context_builder:
            built_msgs = self.context_builder.build_with_memory_injection(context)
            if built_msgs:
                existing = result.get("messages", [])
                result["messages"] = existing + built_msgs
        elif memories:
            # 回退：内联格式化记忆
            memory_text = "\n".join(
                f"[Memory-{m.layer.value}]: {m.content[:200]}" for m in memories[:5]
            )
            result["messages"] = result.get("messages", []) + [
                Message(role=Role.SYSTEM, content=f"Relevant memories:\n{memory_text}")
            ]

        return result

    # ========================================================================
    # DECIDE NODE
    # ========================================================================

    async def decide_node(self, state: GraphState) -> dict[str, Any]:
        """调用 LLM 决策下一步动作"""
        messages = state["messages"]
        iteration = state.get("iteration", 0)
        session_id = state["context"].session_id
        logger.info(f"[decide_node] iteration={iteration}, messages={len(messages)}")

        # Span 追踪
        span = None
        if self.tracer:
            span = self.tracer.start_span(self.tracer.start_trace(session_id), "decide_node")

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
            elif "TASK_COMPLETE" in response.get("content", "") or "FINAL_ANSWER" in response.get(
                "content", ""
            ):
                updates["next_action"] = "answer"
            else:
                updates["next_action"] = "answer"

            # 累计 token
            new_tokens = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
            updates["tokens_used"] = state.get("tokens_used", 0) + new_tokens

            # 记录 Token 使用
            if self.token_monitor:
                self.token_monitor.record_tokens(
                    session_id,
                    "decide",
                    input_tokens=tokens.get("input_tokens", 0),
                    output_tokens=tokens.get("output_tokens", 0),
                )

            if span:
                self.tracer.end_span(
                    span,
                    output_data={"action": updates["next_action"]},
                    tokens_used=new_tokens,
                )

            return updates

        except Exception as e:
            logger.error(f"[decide_node] LLM call failed: {e}")
            if span:
                self.tracer.end_span(span, error=str(e))
            return {
                "error": str(e),
                "next_action": "error",
                "current_thought": f"Error during LLM call: {e}",
            }

    # ========================================================================
    # TOOL NODE
    # ========================================================================

    async def tool_node(self, state: GraphState) -> dict[str, Any]:
        """执行工具调用（带 trace、timeout、approval）"""
        pending = state.get("pending_tool_calls", [])
        if not pending:
            return {"next_action": "answer"}

        session_id = state["context"].session_id
        results: dict[str, Any] = {}
        tool_messages: list[Message] = []
        pending_approvals: list[dict[str, Any]] = []

        for tool_call in pending:
            tool_name = tool_call.get("name", "unknown")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", new_id())
            logger.info(f"[tool_node] executing: {tool_name}")

            # Span 追踪
            span = None
            if self.tracer:
                span = self.tracer.start_span(
                    self.tracer.start_trace(session_id),
                    f"tool:{tool_name}",
                    input_data={"tool_name": tool_name, "args": tool_args},
                )

            # 审批检查
            if self.approval_manager and self.approval_manager.needs_approval(tool_name):
                approval_action = self.approval_manager.get_approval_action(tool_name)
                if approval_action:
                    request = self.approval_manager.create_request(
                        action=approval_action,
                        description=f"Execute {tool_name}: {str(tool_args)[:100]}",
                        details={"tool_name": tool_name, "args": tool_args},
                        session_id=session_id,
                    )
                    pending_approvals.append(
                        {
                            "tool_name": tool_name,
                            "request_id": request.request_id,
                        }
                    )
                    logger.info(f"[tool_node] 审批请求: {request.request_id} for {tool_name}")
                    # 将审批请求添加到 pending
                    continue  # 跳过需要审批的工具调用，等待人工确认

            # 执行工具（带超时管理）
            start = time.monotonic()
            try:
                if self.tool_executor:
                    if self.timeout_manager:
                        result: ToolResult = await self.timeout_manager.run_with_timeout(
                            self.tool_executor.execute(tool_name, **tool_args),
                            name=tool_name,
                            timeout_seconds=self.timeout_manager.get_tool_timeout(tool_name),
                            on_timeout=lambda name=tool_name: ToolResult(
                                success=False,
                                content="",
                                error=f"Tool '{name}' timed out",
                            ),
                        )
                    else:
                        result = await self.tool_executor.execute(tool_name, **tool_args)
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

            # 记录 Node 监控
            if self.token_monitor:
                self.token_monitor.record_node(
                    session_id, f"tool:{tool_name}", duration_ms=duration_ms
                )
                self.token_monitor.record_tool_call(session_id)

            # 完成 span
            if span:
                self.tracer.end_span(
                    span,
                    output_data={"success": result.success},
                    error=result.error or "",
                )

            # 创建工具结果消息
            tool_msg = Message(
                role=Role.TOOL,
                content=result.content if result.success else f"Error: {result.error}",
                tool_name=tool_name,
                tool_call_id=tool_id,
                metadata={"success": result.success, "duration_ms": duration_ms},
            )
            tool_messages.append(tool_msg)

        result_dict: dict[str, Any] = {
            "tool_results": {**state.get("tool_results", {}), **results},
            "messages": tool_messages,
            "pending_tool_calls": [],
            "next_action": "decide",
        }

        # 如果有待审批的操作，标记等待人工确认
        if pending_approvals:
            result_dict["pending_approval"] = {
                "items": pending_approvals,
                "message": f"Waiting for approval on {len(pending_approvals)} tool(s)",
            }
            result_dict["next_action"] = "ask_human"

        return result_dict

    # ========================================================================
    # MEMORY NODE
    # ========================================================================

    async def memory_node(self, state: GraphState) -> dict[str, Any]:
        """写入记忆到 MemoryManager

        将当前对话摘要保存为情景记忆，供后续检索。
        """
        if not self.memory_manager:
            return {}

        session_id = state["context"].session_id
        messages = state.get("messages", [])

        if messages:
            try:
                await self.memory_manager.summarize_episode(
                    session_id=session_id,
                    messages=messages[-20:],  # 最近 20 条
                    importance=0.5,
                )
                logger.debug(f"[memory_node] 记忆已写入 session={session_id}")
            except Exception as e:
                logger.warning(f"[memory_node] 记忆写入失败: {e}")

        return {}

    # ========================================================================
    # SKILL NODE
    # ========================================================================

    async def skill_node(self, state: GraphState) -> dict[str, Any]:
        """执行技能调用

        当 LLM 决定调用技能（而非单个工具）时触发。
        技能是多个工具的组合编排。
        """
        if not self.skill_executor:
            return {"next_action": "decide"}

        current_thought = state.get("current_thought", "")
        session_id = state["context"].session_id

        # 从 current_thought 中提取技能名
        # 或在 state 中添加 skill_name 字段
        skill_name = state.get("pending_skill", "")
        if not skill_name and current_thought:
            # 尝试从 LLM 输出中解析技能名
            skill_name = self._parse_skill_name(current_thought)

        if not skill_name:
            logger.warning("[skill_node] 未指定技能名")
            return {"next_action": "decide"}

        logger.info(f"[skill_node] 执行技能: {skill_name}")

        from ..core.types import SkillContext

        span = None
        if self.tracer:
            span = self.tracer.start_span(
                self.tracer.start_trace(session_id), f"skill:{skill_name}"
            )

        try:
            context = SkillContext(
                session_id=session_id,
                agent_context=state.get("context"),
                tool_results=state.get("tool_results", {}),
                params={"query": state["input"].query},
            )
            result = await self.skill_executor.execute(skill_name, context)

            if self.token_monitor:
                self.token_monitor.record_node(
                    session_id,
                    f"skill:{skill_name}",
                    duration_ms=result.metadata.get("duration_ms", 0),
                )

            if span:
                self.tracer.end_span(span, output_data={"success": result.success})

            # 将技能结果作为工具结果注入
            skill_msg = Message(
                role=Role.TOOL,
                content=result.content if result.success else f"Skill error: {result.error}",
                tool_name=f"skill:{skill_name}",
                metadata={"success": result.success, "skill": True},
            )

            return {
                "messages": [skill_msg],
                "next_action": "decide",
                "pending_skill": "",
            }

        except Exception as e:
            logger.error(f"[skill_node] 技能执行失败: {e}")
            if span:
                self.tracer.end_span(span, error=str(e))
            return {
                "error": f"Skill '{skill_name}' failed: {e}",
                "next_action": "error",
            }

    def _parse_skill_name(self, thought: str) -> str:
        """从 LLM 输出中解析技能名

        支持的格式: "CALL_SKILL: <name>" 或 "use skill <name>"
        """
        if "CALL_SKILL:" in thought:
            parts = thought.split("CALL_SKILL:", 1)
            if len(parts) > 1:
                return parts[1].strip().split("\n")[0].strip()
        for prefix in ["use skill ", "调用技能 ", "使用技能 "]:
            if prefix in thought.lower():
                parts = thought.lower().split(prefix, 1)
                if len(parts) > 1:
                    return parts[1].strip().split("\n")[0].strip().strip('"').strip("'")
        return ""

    # ========================================================================
    # HUMAN NODE
    # ========================================================================

    async def human_node(self, state: GraphState) -> dict[str, Any]:
        """人工确认检查点 - 等待审批通过后继续执行"""
        pending = state.get("pending_approval", {})
        if not pending:
            return {"next_action": "decide"}

        items = pending.get("items", [])
        logger.info(f"[human_node] 等待审批: {len(items)} 项")

        if self.approval_manager:
            # 检查所有审批请求是否已处理
            all_resolved = True
            for item in items:
                req = self.approval_manager.get_request(item.get("request_id", ""))
                if req and req.status.value == "pending":
                    all_resolved = False
                    break

            if all_resolved:
                logger.info("[human_node] 所有审批已处理，继续执行")
                return {"next_action": "decide", "pending_approval": None}

        # LangGraph interrupt 机制在此暂停
        return {"next_action": "decide"}

    # ========================================================================
    # NOTIFY NODE
    # ========================================================================

    async def notify_node(self, state: GraphState) -> dict[str, Any]:
        """发送通知（错误、完成等）

        使用 EmailNotifier 发送邮件通知。
        """
        if not self.email_notifier:
            return {}

        error = state.get("error")
        output = state.get("output", "")
        session_id = state["context"].session_id

        try:
            if error:
                logger.warning(f"[notify_node] 发送错误通知: {error[:100]}")
                await self.email_notifier.send_error(
                    error=error,
                    session_id=session_id,
                )
            elif output:
                logger.info(f"[notify_node] 发送完成通知: session={session_id}")
                await self.email_notifier.send_completion(
                    result_summary=output[:500],
                    session_id=session_id,
                    metadata={
                        "iterations": state.get("iteration", 0),
                        "tokens_used": state.get("tokens_used", 0),
                    },
                )
        except Exception as e:
            logger.warning(f"[notify_node] 通知发送失败: {e}")

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
                "output": (
                    "Task terminated due to reaching maximum iterations "
                    f"({max_iter}). Last error: {error}"
                ),
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
