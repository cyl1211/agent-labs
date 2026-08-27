"""Approval API 路由"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..deps import get_approval_manager

router = APIRouter()


@router.get("/pending")
async def list_pending(session_id: str = ""):
    """列出待审批的请求"""
    mgr = get_approval_manager()
    pending = mgr.get_pending(session_id=session_id)
    return {"pending": [r.to_dict() for r in pending], "count": len(pending)}


@router.post("/{request_id}/approve")
async def approve_request(request_id: str, body: dict[str, Any] | None = None):
    """批准审批请求"""
    mgr = get_approval_manager()
    comment = (body or {}).get("comment", "")
    result = mgr.approve(request_id, comment=comment)
    if not result:
        return {"error": "Request not found or already processed"}, 404
    return {"status": "approved", "request": result.to_dict()}


@router.post("/{request_id}/reject")
async def reject_request(request_id: str, body: dict[str, Any] | None = None):
    """拒绝审批请求"""
    mgr = get_approval_manager()
    reason = (body or {}).get("reason", "")
    result = mgr.reject(request_id, reason=reason)
    if not result:
        return {"error": "Request not found or already processed"}, 404
    return {"status": "rejected", "request": result.to_dict()}


@router.get("/stats")
async def get_approval_stats():
    """获取审批统计"""
    mgr = get_approval_manager()
    return mgr.get_stats()
