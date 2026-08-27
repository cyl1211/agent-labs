"""Unit tests for observability"""

from agent_labs.observability.monitor import TokenMonitor, TokenUsage
from agent_labs.observability.tracer import Tracer


class TestTracer:
    def test_start_trace(self):
        tracer = Tracer()
        trace = tracer.start_trace(session_id="test")
        assert trace.trace_id
        assert trace.session_id == "test"
        assert trace.status == "pending"

    def test_start_end_span(self):
        tracer = Tracer()
        trace = tracer.start_trace("test")
        span = tracer.start_span(trace, "decide_node")
        tracer.end_span(span, output_data={"action": "tool_call"}, tokens_used=100)
        assert span.status == "success"
        assert span.tokens_used == 100
        assert span.duration_ms >= 0
        assert len(trace.spans) == 1

    def test_span_with_error(self):
        tracer = Tracer()
        trace = tracer.start_trace("test")
        span = tracer.start_span(trace, "tool_node")
        tracer.end_span(span, error="execution failed")
        assert span.status == "error"
        assert len(trace.error_spans) == 1

    def test_end_trace_aggregates(self):
        tracer = Tracer()
        trace = tracer.start_trace("test")
        s1 = tracer.start_span(trace, "decide")
        tracer.end_span(s1, tokens_used=50)
        s2 = tracer.start_span(trace, "tool")
        tracer.end_span(s2, tokens_used=30)
        tracer.end_trace(trace)
        assert trace.total_tokens == 80
        assert trace.status == "success"

    def test_get_trace_summary(self):
        tracer = Tracer()
        trace = tracer.start_trace("test")
        span = tracer.start_span(trace, "decide")
        tracer.end_span(span, output_data={"x": 1})
        tracer.end_trace(trace)
        summary = tracer.get_trace_summary(trace)
        assert summary["trace_id"] == trace.trace_id
        assert summary["span_count"] == 1

    def test_get_recent_traces(self):
        tracer = Tracer(max_traces=5)
        for i in range(10):
            tracer.start_trace(f"sess_{i}")
        assert len(tracer.get_recent_traces()) <= 5

    def test_clear(self):
        tracer = Tracer()
        tracer.start_trace("test")
        tracer.clear()
        assert len(tracer.get_recent_traces()) == 0


class TestTokenMonitor:
    def test_record_tokens(self):
        monitor = TokenMonitor()
        monitor.record_tokens("s1", "decide", input_tokens=100, output_tokens=50)
        monitor.record_tokens("s1", "tool", input_tokens=20, output_tokens=10)
        stats = monitor.get_session_stats("s1")
        assert stats["tokens"]["total"] == 180

    def test_record_node(self):
        monitor = TokenMonitor()
        monitor.record_node("s1", "decide", duration_ms=250)
        monitor.record_node("s1", "decide", duration_ms=300)
        stats = monitor.get_session_stats("s1")
        node = stats["nodes"]["decide"]
        assert node["calls"] == 2
        assert node["avg_duration_ms"] > 0

    def test_global_stats(self):
        monitor = TokenMonitor()
        monitor.record_tokens("s1", "decide", input_tokens=100, output_tokens=50)
        monitor.record_tokens("s2", "decide", input_tokens=200, output_tokens=100)
        gs = monitor.get_global_stats()
        assert gs["tokens"]["total"] == 450
        assert gs["active_sessions"] == 2

    def test_check_budget_ok(self):
        monitor = TokenMonitor(budget_warning_threshold=0.8)
        monitor.record_tokens("s1", "d", input_tokens=100)
        over, usage, msg = monitor.check_budget(token_limit=10000)
        assert not over
        assert "WARNING" not in msg

    def test_check_budget_warning(self):
        monitor = TokenMonitor(budget_warning_threshold=0.8)
        monitor.record_tokens("s1", "d", input_tokens=9000)
        over, usage, msg = monitor.check_budget(token_limit=10000)
        assert not over
        assert "WARNING" in msg

    def test_check_budget_exceeded(self):
        monitor = TokenMonitor()
        monitor.record_tokens("s1", "d", input_tokens=11000)
        over, usage, msg = monitor.check_budget(token_limit=10000)
        assert over
        assert "EXCEEDED" in msg

    def test_render_dashboard(self):
        monitor = TokenMonitor()
        monitor.record_tokens("s1", "decide", input_tokens=100, output_tokens=50)
        monitor.record_node("s1", "decide", duration_ms=200)
        dashboard = monitor.render_dashboard()
        assert "Dashboard" in dashboard
        assert "150" in dashboard  # total tokens

    def test_reset(self):
        monitor = TokenMonitor()
        monitor.record_tokens("s1", "d", input_tokens=100)
        monitor.reset_all()
        gs = monitor.get_global_stats()
        assert gs["tokens"]["total"] == 0

    def test_token_usage_cost(self):
        usage = TokenUsage()
        usage.add(input_tokens=1000000, output_tokens=500000)
        assert usage.estimated_cost_usd > 0
