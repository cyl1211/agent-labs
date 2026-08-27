"""
请求追踪器

提供节点级和 span 级别的执行追踪。
记录每个节点的：
- 输入/输出
- 执行时间
- 错误信息
- Token 消耗
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TraceSpan:
    """追踪 span — 单次操作的执行记录"""

    span_id: str
    parent_id: str = ""
    name: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    tokens_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, success, error

    @property
    def is_error(self) -> bool:
        return self.status == "error"


@dataclass
class Trace:
    """追踪 — 一次完整请求的执行记录"""

    trace_id: str
    session_id: str = ""
    spans: list[TraceSpan] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_tokens: int = 0
    total_tool_calls: int = 0
    status: str = "pending"

    @property
    def total_duration_ms(self) -> float:
        if not self.start_time:
            return 0
        end = self.end_time or time.monotonic()
        return (end - self.start_time) * 1000

    @property
    def span_count(self) -> int:
        return len(self.spans)

    @property
    def error_spans(self) -> list[TraceSpan]:
        return [s for s in self.spans if s.is_error]


class Tracer:
    """请求追踪器

    管理 trace 和 span 的生命周期。

    使用方式：
        tracer = Tracer()
        trace = tracer.start_trace(session_id="abc")
        span = tracer.start_span(trace, "decide_node")
        # ... 执行 ...
        tracer.end_span(span, output={"action": "tool_call"})
        tracer.end_trace(trace)
    """

    def __init__(self, max_traces: int = 1000, enabled: bool = True):
        self.enabled = enabled
        self.max_traces = max_traces
        self._traces: dict[str, Trace] = {}
        self._span_counter: int = 0

    def start_trace(self, session_id: str = "") -> Trace:
        """开始一个新的 trace

        Args:
            session_id: 关联的会话 ID

        Returns:
            Trace 对象
        """
        trace_id = f"trace_{len(self._traces)}_{int(time.monotonic() * 1000)}"
        trace = Trace(
            trace_id=trace_id,
            session_id=session_id,
            start_time=time.monotonic(),
        )
        self._traces[trace_id] = trace

        # 容量管理
        if len(self._traces) > self.max_traces:
            oldest = next(iter(self._traces))
            del self._traces[oldest]

        if self.enabled:
            logger.debug(f"[Tracer] 开始 trace: {trace_id}")

        return trace

    def start_span(
        self,
        trace: Trace,
        name: str,
        parent_span: TraceSpan | None = None,
        input_data: dict[str, Any] | None = None,
    ) -> TraceSpan:
        """开始一个新的 span

        Args:
            trace: 所属 trace
            name: span 名称 (如 "decide_node", "tool_node")
            parent_span: 父 span
            input_data: 输入数据

        Returns:
            TraceSpan 对象
        """
        self._span_counter += 1
        span = TraceSpan(
            span_id=f"span_{self._span_counter}",
            parent_id=parent_span.span_id if parent_span else "",
            name=name,
            start_time=time.monotonic(),
            input_data=input_data or {},
            status="running",
        )
        trace.spans.append(span)

        if self.enabled:
            logger.debug(f"[Tracer] 开始 span: {name} (trace={trace.trace_id})")

        return span

    def end_span(
        self,
        span: TraceSpan,
        output_data: dict[str, Any] | None = None,
        error: str = "",
        tokens_used: int = 0,
    ) -> None:
        """结束一个 span

        Args:
            span: 要结束的 span
            output_data: 输出数据
            error: 错误信息
            tokens_used: 消耗的 token 数
        """
        now = time.monotonic()
        span.end_time = now
        span.duration_ms = (now - span.start_time) * 1000
        span.output_data = output_data or {}
        span.error = error
        span.tokens_used = tokens_used
        span.status = "error" if error else "success"

        if self.enabled:
            level = logging.ERROR if error else logging.DEBUG
            logger.log(
                level,
                f"[Tracer] 结束 span: {span.name} "
                f"({span.duration_ms:.1f}ms, tokens={tokens_used})"
                f"{' ERROR: ' + error if error else ''}",
            )

    def end_trace(self, trace: Trace, error: str = "") -> None:
        """结束一个 trace

        Args:
            trace: 要结束的 trace
            error: 整体错误信息
        """
        trace.end_time = time.monotonic()
        trace.status = "error" if error else "success"
        trace.total_tokens = sum(s.tokens_used for s in trace.spans)
        trace.total_tool_calls = sum(
            1 for s in trace.spans if s.name == "tool_node" and s.status == "success"
        )

        if self.enabled:
            logger.info(
                f"[Tracer] 结束 trace: {trace.trace_id} "
                f"({trace.total_duration_ms:.1f}ms, "
                f"{trace.span_count} spans, "
                f"{trace.total_tokens} tokens, "
                f"{trace.total_tool_calls} tool calls)"
            )

    def get_trace(self, trace_id: str) -> Trace | None:
        """获取指定 trace"""
        return self._traces.get(trace_id)

    def get_recent_traces(self, n: int = 10) -> list[Trace]:
        """获取最近的 N 个 trace"""
        traces = list(self._traces.values())
        traces.sort(key=lambda t: t.start_time, reverse=True)
        return traces[:n]

    def get_trace_summary(self, trace: Trace) -> dict[str, Any]:
        """获取 trace 摘要"""
        return {
            "trace_id": trace.trace_id,
            "session_id": trace.session_id,
            "status": trace.status,
            "duration_ms": trace.total_duration_ms,
            "span_count": trace.span_count,
            "total_tokens": trace.total_tokens,
            "total_tool_calls": trace.total_tool_calls,
            "error_spans": len(trace.error_spans),
            "spans": [
                {
                    "name": s.name,
                    "duration_ms": s.duration_ms,
                    "tokens_used": s.tokens_used,
                    "status": s.status,
                    "error": s.error[:100] if s.error else "",
                }
                for s in trace.spans
            ],
        }

    def clear(self) -> None:
        """清空所有 trace"""
        self._traces.clear()
        self._span_counter = 0
