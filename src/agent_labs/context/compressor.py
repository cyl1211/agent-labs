"""
上下文压缩器

当对话历史超过 token 预算时，自动压缩旧消息。
压缩策略：
1. 滑动窗口：保留最近 N 条消息完整
2. 摘要压缩：将超出窗口的旧消息合并为摘要
3. 重要性加权：关键消息（含工具调用结果、错误）优先保留
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.types import Message, Role

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4


class ContextCompressor:
    """上下文压缩器

    负责检测对话长度，触发压缩，管理消息窗口。

    使用方式：
        compressor = ContextCompressor(max_tokens=100000, threshold_messages=30)
        result = compressor.compress(messages)
        # result.messages — 压缩后的消息列表
        # result.compressed — 是否发生了压缩
    """

    def __init__(
        self,
        max_tokens: int = 100000,
        threshold_messages: int = 30,
        keep_recent: int = 10,
        max_summary_length: int = 500,
    ):
        self.max_tokens = max_tokens
        self.threshold_messages = threshold_messages
        self.keep_recent = keep_recent
        self.max_summary_length = max_summary_length

    def should_compress(self, messages: list[Message]) -> bool:
        """判断是否需要压缩

        两个条件之一满足即触发：
        1. 消息数量超过阈值
        2. 估算 token 数超过预算的 80%
        """
        if len(messages) > self.threshold_messages:
            return True

        total_tokens = self._estimate_total_tokens(messages)
        return total_tokens > self.max_tokens * 0.8

    def compress(self, messages: list[Message]) -> CompressionResult:
        """压缩消息列表

        策略：
        1. 保留最近 keep_recent 条消息完整
        2. 将更早的消息压缩为摘要
        3. 工具调用结果消息保留（含重要执行信息）
        4. 错误消息优先保留

        Args:
            messages: 完整消息列表

        Returns:
            CompressionResult 包含压缩后的消息和元数据
        """
        if not messages:
            return CompressionResult(messages=[], compressed=False, summary="")

        # 不需要压缩
        if not self.should_compress(messages) or len(messages) <= self.keep_recent:
            return CompressionResult(messages=list(messages), compressed=False, summary="")

        # 分割：最近的消息 vs 旧消息
        recent = messages[-self.keep_recent :]
        older = messages[: -self.keep_recent]

        # 从旧消息中保留关键消息
        critical_from_older = self._extract_critical_messages(older)
        to_summarize = [m for m in older if m not in critical_from_older]

        # 生成摘要
        summary = self._generate_summary(to_summarize)

        # 构建压缩后的消息列表
        compressed_messages: list[Message] = []

        # 摘要消息
        if summary:
            compressed_messages.append(
                Message(
                    role=Role.SYSTEM,
                    content=f"[Conversation Summary] {summary}",
                )
            )

        # 保留的关键消息
        compressed_messages.extend(critical_from_older)

        # 分隔标记
        if critical_from_older:
            compressed_messages.append(
                Message(
                    role=Role.SYSTEM,
                    content=f"[{len(to_summarize)} earlier messages summarized. "
                    f"Showing {len(critical_from_older)} critical + "
                    f"{len(recent)} recent messages.]",
                )
            )

        # 最近的消息
        compressed_messages.extend(recent)

        logger.info(
            f"[Compressor] 压缩: {len(messages)} → {len(compressed_messages)} 条消息 "
            f"(摘要 {len(to_summarize)} 条, 保留 {len(critical_from_older)} 条关键)"
        )

        return CompressionResult(
            messages=compressed_messages,
            compressed=True,
            summary=summary,
            original_count=len(messages),
            compressed_count=len(compressed_messages),
            summarized_count=len(to_summarize),
        )

    def compress_with_token_budget(
        self, messages: list[Message], token_budget: int
    ) -> CompressionResult:
        """按 token 预算压缩

        确保压缩后的消息不超过 token_budget。
        """
        # 先做基本压缩
        result = self.compress(messages)

        # 如果仍然超出预算，进一步截断
        current_tokens = self._estimate_total_tokens(result.messages)
        if current_tokens <= token_budget:
            return result

        # 从前往后逐步移除消息，直到满足预算
        trimmed = list(result.messages)
        while self._estimate_total_tokens(trimmed) > token_budget and len(trimmed) > 1:
            # 跳过系统摘要消息
            for i, msg in enumerate(trimmed):
                if msg.role != Role.SYSTEM or "[Conversation Summary]" not in msg.content:
                    trimmed.pop(i)
                    break
            else:
                # 如果没有非摘要消息可移除，保留最后一条
                trimmed = trimmed[-1:]
                break

        result.messages = trimmed
        return result

    def _extract_critical_messages(self, messages: list[Message]) -> list[Message]:
        """从旧消息中提取关键消息

        以下类型的消息被认为是关键的：
        - 工具调用结果（含重要数据）
        - 错误相关消息
        - 用户明确标记为重要的消息
        """
        critical = []
        critical_keywords = ["重要", "critical", "关键", "记住"]
        for msg in messages:
            is_tool = msg.role == Role.TOOL
            has_error = "error" in msg.content.lower() or "错误" in msg.content
            is_important_user = msg.role == Role.USER and any(
                kw in msg.content.lower() for kw in critical_keywords
            )
            if is_tool or has_error or is_important_user:
                critical.append(msg)

        # 限制关键消息数量
        max_critical = max(5, self.keep_recent // 2)
        return critical[-max_critical:]

    def _generate_summary(self, messages: list[Message]) -> str:
        """生成消息摘要

        当前阶段：基于关键词提取的简单摘要。
        Phase 3：使用 LLM 生成高质量摘要。
        """
        if not messages:
            return ""

        summary_parts = []

        # 提取每条消息的核心内容
        for msg in messages:
            content = msg.content
            if not content:
                continue

            # 截取每条消息的前 100 字符作为要点
            snippet = content[:100].replace("\n", " ").strip()
            if snippet:
                prefix = {
                    Role.USER: "User asked",
                    Role.ASSISTANT: "Agent responded",
                    Role.TOOL: "Tool result",
                    Role.SYSTEM: "System note",
                }.get(msg.role, msg.role.value)

                summary_parts.append(f"{prefix}: {snippet}")

        # 合并为摘要
        summary = " | ".join(summary_parts)
        if len(summary) > self.max_summary_length:
            summary = summary[: self.max_summary_length - 3] + "..."

        return summary

    def _estimate_total_tokens(self, messages: list[Message]) -> int:
        """估算消息列表的总 token 数"""
        total = 0
        for msg in messages:
            total += max(1, len(msg.content) // CHARS_PER_TOKEN)
        return total

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算单个文本的 token 数"""
        if not text:
            return 0
        return max(1, len(text) // CHARS_PER_TOKEN)

    def get_stats(self, messages: list[Message]) -> dict[str, Any]:
        """获取消息统计信息"""
        total_tokens = self._estimate_total_tokens(messages)
        return {
            "message_count": len(messages),
            "estimated_tokens": total_tokens,
            "token_budget": self.max_tokens,
            "usage_percent": round(total_tokens / self.max_tokens * 100, 1)
            if self.max_tokens
            else 0,
            "needs_compression": self.should_compress(messages),
            "threshold_messages": self.threshold_messages,
            "keep_recent": self.keep_recent,
        }


class CompressionResult:
    """压缩结果"""

    __slots__ = (
        "messages",
        "compressed",
        "summary",
        "original_count",
        "compressed_count",
        "summarized_count",
    )

    def __init__(
        self,
        messages: list[Message],
        compressed: bool,
        summary: str,
        original_count: int = 0,
        compressed_count: int = 0,
        summarized_count: int = 0,
    ):
        self.messages = messages
        self.compressed = compressed
        self.summary = summary
        self.original_count = original_count
        self.compressed_count = compressed_count
        self.summarized_count = summarized_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "compressed": self.compressed,
            "original_count": self.original_count,
            "compressed_count": self.compressed_count,
            "summarized_count": self.summarized_count,
            "summary_preview": self.summary[:200] if self.summary else "",
        }
