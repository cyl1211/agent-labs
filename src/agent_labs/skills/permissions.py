"""
技能权限管理

技能的权限取决于其 required_tools 中最高权限的工具。
例如，如果技能需要 write_file（write 权限），则技能本身也需要 write 权限。
"""

from __future__ import annotations

import logging
from typing import Any

from ..tools.permissions import ToolPermissionManager, UserRole

logger = logging.getLogger(__name__)


class SkillPermissionManager:
    """技能权限管理器

    技能的权限 = max(所需工具的权限级别)
    因为执行技能会间接调用其中的工具，所以需要同时检查技能和工具的权限。

    使用方式:
        skill_perm = SkillPermissionManager(tool_perm_manager)
        allowed, reason = skill_perm.check("代码分析", user_roles=["editor"])
    """

    def __init__(self, tool_perm_manager: ToolPermissionManager | None = None):
        self._tool_perm = tool_perm_manager or ToolPermissionManager()
        self._skill_perms: dict[str, dict[str, Any]] = {}

    def register_skill(
        self,
        skill_name: str,
        required_tools: list[str],
        custom_permission: str | None = None,
        require_approval: bool | None = None,
    ) -> None:
        """注册技能权限

        自动根据所需工具推断技能的最低权限要求。

        Args:
            skill_name: 技能名称
            required_tools: 所需工具名列表
            custom_permission: 自定义权限级别（覆盖自动推断）
            require_approval: 是否需要审批（覆盖自动推断）
        """
        # 取所需工具中最高的权限级别（可被 custom_permission 覆盖）
        effective_level = custom_permission or self._infer_permission_level(required_tools)

        needs_approval = require_approval
        if needs_approval is None:
            # 如果任一工具需要审批，技能也需要审批
            needs_approval = any(self._tool_perm.needs_approval(t) for t in required_tools)

        self._skill_perms[skill_name] = {
            "permission_level": effective_level,
            "required_tools": required_tools,
            "require_approval": needs_approval,
        }

        logger.info(
            f"[SkillPermission] 注册技能 '{skill_name}': "
            f"权限级别={effective_level}, 需审批={needs_approval}"
        )

    def _infer_permission_level(self, required_tools: list[str]) -> str:
        """根据所需工具推断权限级别

        权限级别: execute > write > read
        """
        level_rank = {"read": 0, "write": 1, "execute": 2}
        max_level = "read"
        max_rank = 0

        for tool_name in required_tools:
            perm = self._tool_perm.get(tool_name)
            if perm is None:
                continue
            rank = level_rank.get(perm.permission_level, 0)
            if rank > max_rank:
                max_rank = rank
                max_level = perm.permission_level

        return max_level

    def check(
        self,
        skill_name: str,
        user_roles: list[str] | None = None,
    ) -> tuple[bool, str]:
        """检查用户是否有权限使用技能

        检查流程:
        1. 验证技能所需的所有工具用户都有权限访问
        2. 验证用户角色满足技能本身的权限级别

        Args:
            skill_name: 技能名称
            user_roles: 用户角色列表

        Returns:
            (是否允许, 原因说明)
        """
        user_roles = user_roles or ["viewer"]

        skill_perm = self._skill_perms.get(skill_name)
        if skill_perm is None:
            return True, "no_config"  # 未注册的技能默认允许

        # 1. 检查所需工具的权限
        required_tools = skill_perm.get("required_tools", [])
        for tool_name in required_tools:
            allowed, reason = self._tool_perm.check(tool_name, user_roles)
            if not allowed:
                return False, (
                    f"技能 '{skill_name}' 需要工具 '{tool_name}'，但该工具不可用: {reason}"
                )

        # 2. 检查技能本身的权限级别
        level = skill_perm.get("permission_level", "read")
        max_role_level = max(
            (UserRole.get_level(r) for r in user_roles),
            default=0,
        )
        level_rank = {"read": 10, "write": 50, "execute": 100}

        required_rank = level_rank.get(level, 10)
        if max_role_level < required_rank:
            return False, (
                f"技能 '{skill_name}' 需要 {level} 级别权限，当前用户角色 {user_roles} 不满足"
            )

        return True, "approved"

    def needs_approval(self, skill_name: str) -> bool:
        """检查技能是否需要审批"""
        perm = self._skill_perms.get(skill_name)
        if perm is None:
            return False
        return perm.get("require_approval", False)

    def list_skill_permissions(self) -> dict[str, dict[str, Any]]:
        """列出所有技能权限"""
        return dict(self._skill_perms)

    def get_accessible_skills(self, user_roles: list[str]) -> list[str]:
        """获取用户可访问的技能列表"""
        accessible = []
        for name in self._skill_perms:
            allowed, _ = self.check(name, user_roles)
            if allowed:
                accessible.append(name)
        return accessible
