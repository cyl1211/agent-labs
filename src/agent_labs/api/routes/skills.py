"""Skills API 路由"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..deps import get_skill_executor, get_skill_registry

router = APIRouter()


@router.get("")
async def list_skills():
    """列出所有可用技能"""
    registry = get_skill_registry()
    skills = [s.to_dict() for s in registry.get_all()]
    return {"skills": skills, "count": len(skills)}


@router.post("/execute")
async def execute_skill(request: dict[str, Any]):
    """执行技能"""
    from ...core.types import SkillContext

    name = request.get("name", "")
    if not name:
        return {"error": "'name' is required"}, 400

    executor = get_skill_executor()
    context = SkillContext(
        session_id=request.get("session_id", "default"),
        params=request.get("params", {}),
    )
    result = await executor.execute(name, context)
    return result.model_dump()
