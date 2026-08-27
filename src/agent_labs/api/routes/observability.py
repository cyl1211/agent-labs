"""Observability API 路由"""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import get_token_monitor, get_tracer

router = APIRouter()


@router.get("/traces")
async def list_traces(n: int = 10):
    """列出最近的 traces"""
    tracer = get_tracer()
    traces = tracer.get_recent_traces(n)
    return {
        "traces": [tracer.get_trace_summary(t) for t in traces],
        "count": len(traces),
    }


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """获取指定 trace 详情"""
    tracer = get_tracer()
    trace = tracer.get_trace(trace_id)
    if not trace:
        return {"error": "Trace not found"}, 404
    return tracer.get_trace_summary(trace)


@router.get("/dashboard")
async def get_dashboard():
    """获取监控仪表板"""
    monitor = get_token_monitor()
    return {
        "dashboard": monitor.render_dashboard(),
        "global_stats": monitor.get_global_stats(),
    }


@router.get("/stats")
async def get_stats():
    """获取全局统计"""
    monitor = get_token_monitor()
    return monitor.get_global_stats()


@router.get("/stats/sessions/{session_id}")
async def get_session_stats(session_id: str):
    """获取会话统计"""
    monitor = get_token_monitor()
    stats = monitor.get_session_stats(session_id)
    if not stats:
        return {"error": "Session not found"}, 404
    return stats
