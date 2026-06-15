"""
Tools API 路由

端点：
- GET  /tools — 列出所有工具
- POST /tools/execute — 直接执行工具（需权限）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..deps import get_tool_executor, get_tool_registry

router = APIRouter()


@router.get("")
async def list_tools():
    """列出所有可用工具及其定义"""
    executor = get_tool_executor()
    tools = executor.get_tool_definitions()
    return {"tools": tools, "count": len(tools)}


@router.post("/execute")
async def execute_tool(request: dict[str, Any]):
    """
    直接执行工具

    请求体：
    ```json
    {"name": "tool_name", "args": {"key": "value"}}
    ```
    """
    name = request.get("name", "")
    args = request.get("args", {})

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required")

    executor = get_tool_executor()
    result = await executor.execute(name, **args)
    return result.model_dump()
