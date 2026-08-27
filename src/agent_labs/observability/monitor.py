"""
Token 和性能监控

提供：
- Token 使用实时监控
- 按节点/会话/Agent 维度的统计
- 性能瓶颈检测
- 简单的文本仪表板
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token 使用统计"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        """估算成本 (USD)

        参考价格 (per 1M tokens):
        - Claude Opus: $15 input / $75 output
        - GPT-4o: $2.50 input / $10 output
        这里使用中等偏上的估算。
        """
        input_cost = self.input_tokens * 3.0 / 1_000_000
        output_cost = self.output_tokens * 15.0 / 1_000_000
        return input_cost + output_cost


@dataclass
class NodeStats:
    """单个节点的统计"""

    name: str
    call_count: int = 0
    total_duration_ms: float = 0.0
    total_tokens: int = 0
    error_count: int = 0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / max(self.call_count, 1)

    @property
    def error_rate(self) -> float:
        return self.error_count / max(self.call_count, 1)


@dataclass
class SessionStats:
    """会话级别的统计"""

    session_id: str
    start_time: float = 0.0
    iteration_count: int = 0
    tool_call_count: int = 0
    tokens: TokenUsage = field(default_factory=TokenUsage)
    node_stats: dict[str, NodeStats] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class TokenMonitor:
    """Token 和性能监控器

    使用方式：
        monitor = TokenMonitor()
        monitor.record_tokens(session_id="abc", node="decide", input=100, output=50)
        monitor.record_node(session_id="abc", node="decide", duration_ms=250)
        dashboard = monitor.render_dashboard()
    """

    def __init__(self, enabled: bool = True, budget_warning_threshold: float = 0.8):
        self.enabled = enabled
        self.budget_warning_threshold = budget_warning_threshold

        # 全局统计
        self._global_tokens = TokenUsage()
        self._global_node_stats: dict[str, NodeStats] = {}

        # 会话级别统计
        self._sessions: dict[str, SessionStats] = {}

        # 实时数据
        self._recent_records: list[dict[str, Any]] = []
        self._max_records = 500

    # ---- 记录 ----

    def record_tokens(
        self,
        session_id: str,
        node: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """记录 token 使用"""
        if not self.enabled:
            return

        session = self._get_or_create_session(session_id)
        session.tokens.add(input_tokens, output_tokens)
        self._global_tokens.add(input_tokens, output_tokens)

        # 更新节点统计
        ns = self._get_or_create_node_stats(session, node)
        ns.total_tokens += input_tokens + output_tokens

        gns = self._global_node_stats.setdefault(node, NodeStats(name=node))
        gns.total_tokens += input_tokens + output_tokens

        self._record(
            {
                "type": "token",
                "session_id": session_id,
                "node": node,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "timestamp": time.monotonic(),
            }
        )

    def record_node(
        self,
        session_id: str,
        node: str,
        duration_ms: float = 0.0,
        error: str = "",
    ) -> None:
        """记录节点执行"""
        if not self.enabled:
            return

        session = self._get_or_create_session(session_id)
        ns = self._get_or_create_node_stats(session, node)
        ns.call_count += 1
        ns.total_duration_ms += duration_ms
        if error:
            ns.error_count += 1

        gns = self._global_node_stats.setdefault(node, NodeStats(name=node))
        gns.call_count += 1
        gns.total_duration_ms += duration_ms
        if error:
            gns.error_count += 1

        if error:
            session.errors.append(f"[{node}] {error}")

    def record_tool_call(self, session_id: str) -> None:
        """记录工具调用"""
        if not self.enabled:
            return
        session = self._get_or_create_session(session_id)
        session.tool_call_count += 1

    def record_iteration(self, session_id: str) -> None:
        """记录循环迭代"""
        if not self.enabled:
            return
        session = self._get_or_create_session(session_id)
        session.iteration_count += 1

    # ---- 查询 ----

    def get_global_stats(self) -> dict[str, Any]:
        """获取全局统计"""
        return {
            "tokens": {
                "input": self._global_tokens.input_tokens,
                "output": self._global_tokens.output_tokens,
                "total": self._global_tokens.total_tokens,
                "estimated_cost_usd": round(self._global_tokens.estimated_cost_usd, 4),
            },
            "nodes": {
                name: {
                    "calls": ns.call_count,
                    "avg_duration_ms": round(ns.avg_duration_ms, 1),
                    "total_tokens": ns.total_tokens,
                    "error_rate": round(ns.error_rate, 3),
                }
                for name, ns in self._global_node_stats.items()
            },
            "active_sessions": len(self._sessions),
        }

    def get_session_stats(self, session_id: str) -> dict[str, Any] | None:
        """获取会话统计"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        return {
            "session_id": session.session_id,
            "iterations": session.iteration_count,
            "tool_calls": session.tool_call_count,
            "tokens": {
                "input": session.tokens.input_tokens,
                "output": session.tokens.output_tokens,
                "total": session.tokens.total_tokens,
            },
            "nodes": {
                name: {
                    "calls": ns.call_count,
                    "avg_duration_ms": round(ns.avg_duration_ms, 1),
                    "error_rate": round(ns.error_rate, 3),
                }
                for name, ns in session.node_stats.items()
            },
            "error_count": len(session.errors),
            "recent_errors": session.errors[-5:],
        }

    def check_budget(self, token_limit: int) -> tuple[bool, float, str]:
        """检查 token 是否接近预算上限

        Returns:
            (是否超限, 使用比例, 警告信息)
        """
        usage = self._global_tokens.total_tokens / max(token_limit, 1)
        if usage >= 1.0:
            return (
                True,
                usage,
                f"Token budget EXCEEDED: {self._global_tokens.total_tokens}/{token_limit}",
            )
        elif usage >= self.budget_warning_threshold:
            return False, usage, f"Token budget WARNING: {usage:.0%} used"
        return False, usage, "OK"

    def render_dashboard(self) -> str:
        """渲染文本仪表板"""
        lines = [
            "=" * 60,
            "  Agent-Labs Token & Performance Dashboard",
            "=" * 60,
            "",
            "--- Global Token Usage ---",
            f"  Input:  {self._global_tokens.input_tokens:>10,} tokens",
            f"  Output: {self._global_tokens.output_tokens:>10,} tokens",
            f"  Total:  {self._global_tokens.total_tokens:>10,} tokens",
            f"  Cost:   ${self._global_tokens.estimated_cost_usd:>10.4f}",
            "",
            "--- Node Performance ---",
        ]

        if self._global_node_stats:
            for name, ns in sorted(
                self._global_node_stats.items(),
                key=lambda x: x[1].total_duration_ms,
                reverse=True,
            ):
                lines.append(
                    f"  {name:<20} calls={ns.call_count:>5}  "
                    f"avg={ns.avg_duration_ms:>7.1f}ms  "
                    f"tokens={ns.total_tokens:>8,}  "
                    f"errors={ns.error_rate:.1%}"
                )
        else:
            lines.append("  (no data yet)")

        lines.extend(
            [
                "",
                "--- Active Sessions ---",
                f"  Count: {len(self._sessions)}",
            ]
        )

        for sid, session in list(self._sessions.items())[-5:]:
            lines.append(
                f"  {sid[:16]:<16} iter={session.iteration_count:>3}  "
                f"tools={session.tool_call_count:>3}  "
                f"tokens={session.tokens.total_tokens:>6,}"
            )

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    def reset_session(self, session_id: str) -> None:
        """重置会话统计"""
        self._sessions.pop(session_id, None)

    def reset_all(self) -> None:
        """重置所有统计"""
        self._global_tokens = TokenUsage()
        self._global_node_stats.clear()
        self._sessions.clear()
        self._recent_records.clear()

    # ---- 内部 ----

    def _get_or_create_session(self, session_id: str) -> SessionStats:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionStats(
                session_id=session_id,
                start_time=time.monotonic(),
            )
        return self._sessions[session_id]

    def _get_or_create_node_stats(self, session: SessionStats, node: str) -> NodeStats:
        if node not in session.node_stats:
            session.node_stats[node] = NodeStats(name=node)
        return session.node_stats[node]

    def _record(self, record: dict[str, Any]) -> None:
        self._recent_records.append(record)
        if len(self._recent_records) > self._max_records:
            self._recent_records = self._recent_records[-self._max_records :]
