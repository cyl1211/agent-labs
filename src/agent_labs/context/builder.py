"""
上下文构建器

从 session messages + memory entries 构建注入 LLM 的结构化上下文。
核心职责：
- Token 预算管理：优先保留最新消息，旧消息压缩为摘要
- 多来源整合：session 历史 + 记忆检索 + 系统指令
- 输出为消息列表，可直接注入 LangGraph 状态
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.types import AgentContext, MemoryEntry, Message, Role

logger = logging.getLogger(__name__)

# 粗略 token 估算常量
CHARS_PER_TOKEN = 4  # 平均每 token 约 4 个字符（中英文混合）


class ContextBuilder:
    """上下文构建器

    将分散的上下文来源整合为 LLM 可消费的消息格式。

    使用方式：
        builder = ContextBuilder(max_tokens=100000)
        messages = builder.build(context)
    """

    def __init__(
        self,
        max_tokens: int = 100000,
        system_reserve_tokens: int = 2000,
        response_reserve_tokens: int = 4000,
    ):
        self.max_tokens = max_tokens
        self.system_reserve_tokens = system_reserve_tokens
        self.response_reserve_tokens = response_reserve_tokens

        # 可用于消息内容的 token 预算
        self._usable_tokens = max_tokens - system_reserve_tokens - response_reserve_tokens

    def build(self, context: AgentContext) -> list[Message]:
        """从 AgentContext 构建上下文消息列表

        构建策略：
        1. 系统消息（含记忆注入）
        2. 最近的对话历史（受 token 预算限制）
        3. 当前用户查询已通过 input_node 注入

        Args:
            context: Agent 执行上下文

        Returns:
            构建好的消息列表
        """
        messages: list[Message] = []

        # 1. 构建系统消息
        system_content = self._build_system_content(context)
        if system_content:
            messages.append(Message(role=Role.SYSTEM, content=system_content))

        # 2. 处理现有消息（按 token 预算截断）
        history_messages = self._truncate_history(context.messages)

        # 只保留非系统消息（系统消息已重建）
        for msg in history_messages:
            if msg.role != Role.SYSTEM:
                messages.append(msg)

        if len(context.messages) > len(history_messages):
            logger.info(
                f"[ContextBuilder] 历史消息截断: {len(context.messages)} → {len(history_messages)}"
            )

        return messages

    def _build_system_content(self, context: AgentContext) -> str:
        """构建系统消息内容（含记忆注入）"""
        parts = []

        # 基础指令
        parts.append(self._base_instructions())

        # 注入记忆
        if context.memories:
            memory_text = self._format_memories(context.memories)
            if memory_text:
                parts.append(memory_text)

        # 注入用户偏好
        user_info = self._format_user_context(context)
        if user_info:
            parts.append(user_info)

        return "\n\n".join(parts)

    def _base_instructions(self) -> str:
        """基础系统指令"""
        return (
            "You are an intelligent AI agent with access to tools and memory. "
            "Use the provided context to give accurate, helpful responses. "
            "When relevant, reference past interactions from the memory section."
        )

    def _format_memories(self, memories: list[MemoryEntry]) -> str:
        """格式化记忆条目为上下文文本"""
        if not memories:
            return ""

        lines = ["## Relevant Memories"]

        # 按层级分组
        by_layer: dict[str, list[MemoryEntry]] = {}
        for m in memories:
            layer_name = m.layer.value if hasattr(m.layer, "value") else str(m.layer)
            by_layer.setdefault(layer_name, []).append(m)

        layer_names = {
            "working": "📋 Working (Current Context)",
            "episodic": "📝 Episodic (Past Conversations)",
            "semantic": "🧠 Semantic (Knowledge & Facts)",
            "procedural": "🔧 Procedural (Proven Patterns)",
        }

        for layer_name in ["working", "episodic", "semantic", "procedural"]:
            entries = by_layer.get(layer_name, [])
            if not entries:
                continue
            label = layer_names.get(layer_name, layer_name)
            lines.append(f"\n### {label}")
            for i, m in enumerate(entries[:5], 1):
                content_preview = m.content[:300]
                lines.append(f"{i}. [{m.importance:.0%}] {content_preview}")

        return "\n".join(lines)

    def _format_user_context(self, context: AgentContext) -> str:
        """格式化用户相关上下文"""
        parts = []

        if context.user_id:
            parts.append(f"Current User: {context.user_id}")
        if context.session_id:
            parts.append(f"Session: {context.session_id}")

        if not parts:
            return ""

        return "## Session Info\n" + "\n".join(parts)

    def _truncate_history(self, messages: list[Message]) -> list[Message]:
        """按 token 预算截断历史消息

        策略：从最新消息往前保留，直到达到 token 预算上限。
        保留部分旧消息作为上下文摘要。
        """
        if not messages:
            return []

        # 估算每条消息的 token 数
        message_tokens = [self._estimate_tokens(m.content) for m in messages]

        total = sum(message_tokens)
        if total <= self._usable_tokens:
            return list(messages)

        # 从后往前保留
        kept = []
        used = 0
        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = message_tokens[i]
            if used + msg_tokens > self._usable_tokens:
                break
            kept.insert(0, messages[i])
            used += msg_tokens

        # 如果截掉了消息，在最前面加一个摘要标记
        if len(kept) < len(messages):
            truncated_count = len(messages) - len(kept)
            summary = Message(
                role=Role.SYSTEM,
                content=(
                    f"[{truncated_count} earlier messages have been summarized for brevity. "
                    f"Key context from earlier: the conversation started with the user's "
                    f"initial request and proceeded through several exchanges.]"
                ),
            )
            kept.insert(0, summary)

        return kept

    def build_with_memory_injection(self, context: AgentContext, query: str = "") -> list[Message]:
        """构建包含记忆注入的上下文（用于 graph context_node）

        与 build() 的区别：此方法专门为 context_node 设计，
        生成单独的记忆上下文消息，而非混合在系统消息中。
        """
        if not context.memories:
            return []

        memory_text = self._format_memories(context.memories)
        if not memory_text:
            return []

        return [
            Message(
                role=Role.SYSTEM,
                content=(
                    f"The following memories are relevant to the current conversation:\n\n"
                    f"{memory_text}\n\n"
                    f"Use these memories to provide a more personalized and informed response."
                ),
            )
        ]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算文本的 token 数量

        中文约 1.5 字符/token，英文约 4 字符/token。
        这里取保守估计。
        """
        if not text:
            return 0
        # 简单估算：字符数 / 平均每 token 字符数
        return max(1, len(text) // CHARS_PER_TOKEN)

    def get_budget_info(self) -> dict[str, Any]:
        """获取 token 预算信息"""
        return {
            "max_tokens": self.max_tokens,
            "system_reserve": self.system_reserve_tokens,
            "response_reserve": self.response_reserve_tokens,
            "usable": self._usable_tokens,
        }
