"""
Session API 路由

端点：
- GET  /sessions — 列出会话
- POST /sessions — 创建会话
- GET  /sessions/{id} — 获取会话状态
- DELETE /sessions/{id} — 关闭会话
- GET  /sessions/{id}/history — 获取消息历史
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import get_session_manager

router = APIRouter()


@router.post("")
async def create_session(request: dict):
    """创建新会话"""
    agent_id = request.get("agent_id", "ReactAgent:react")
    sm = get_session_manager()
    session_id = await sm.create(agent_id=agent_id)
    return {"session_id": session_id, "agent_id": agent_id}


@router.get("")
async def list_sessions(status: str | None = None):
    """列出所有会话"""
    sm = get_session_manager()
    sessions = await sm.list_sessions(status=status)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取会话状态"""
    sm = get_session_manager()
    state = await sm.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return state.model_dump()


@router.delete("/{session_id}")
async def close_session(session_id: str):
    """关闭会话"""
    sm = get_session_manager()
    await sm.close(session_id)
    return {"session_id": session_id, "status": "closed"}


@router.get("/{session_id}/history")
async def get_history(session_id: str, limit: int = 50):
    """获取会话消息历史"""
    sm = get_session_manager()
    state = await sm.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await sm.get_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": [m.model_dump() for m in messages]}
