"""
工具权限管理

基于 config/tools.yaml 的 permission_level 做访问控制。
与用户角色关联，实现细粒度的工具使用授权。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# 用户可用的角色
class UserRole:
    """用户角色常量"""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    DEVELOPER = "developer"

    # 角色优先级 (数值越大权限越高)
    _HIERARCHY = {
        ADMIN: 100,
        EDITOR: 50,
        DEVELOPER: 50,
        VIEWER: 10,
    }

    @classmethod
    def get_level(cls, role: str) -> int:
        """获取角色权限等级"""
        return cls._HIERARCHY.get(role, 0)

    @classmethod
    def is_valid(cls, role: str) -> bool:
        """检查角色是否有效"""
        return role in cls._HIERARCHY


@dataclass
class ToolPermissionConfig:
    """单个工具的权限配置"""

    name: str
    permission_level: str = "read"
    require_approval: bool = False
    sandbox_required: bool = False
    timeout_seconds: int = 60
    retry_count: int = 2
    enabled: bool = True
    allowed_roles: list[str] = field(default_factory=list)


class ToolPermissionManager:
    """工具权限管理器

    负责:
    - 从 YAML 配置加载工具权限
    - 运行时权限检查
    - 审批需求判断

    使用方式:
        manager = ToolPermissionManager()
        manager.load_from_config(settings.tools_config)
        can_use = manager.check("write_file", user_roles=["editor"])
    """

    def __init__(self):
        self._permissions: dict[str, ToolPermissionConfig] = {}
        self._permission_levels: dict[str, dict[str, Any]] = {}

    def load_from_config(self, tools_config: dict[str, Any]) -> None:
        """从配置加载工具权限

        Args:
            tools_config: 来自 Settings.tools_config 的配置
        """
        # 加载权限级别定义
        self._permission_levels = tools_config.get("permission_levels", {})
        if not self._permission_levels:
            # 从顶层加载（兼容嵌套在 tools_config 中的情况）
            pass

        # 加载工具配置
        tools = tools_config.get("tools", [])
        if not tools:
            logger.warning("[PermissionManager] 未找到工具配置")
            return

        for tool_cfg in tools:
            if not isinstance(tool_cfg, dict):
                continue
            name = tool_cfg.get("name", "")
            if not name:
                continue
            self._permissions[name] = ToolPermissionConfig(
                name=name,
                permission_level=tool_cfg.get("permission_level", "read"),
                require_approval=tool_cfg.get("require_approval", False),
                sandbox_required=tool_cfg.get("sandbox_required", False),
                timeout_seconds=tool_cfg.get("timeout_seconds", 60),
                retry_count=tool_cfg.get("retry_count", 2),
                enabled=tool_cfg.get("enabled", True),
                allowed_roles=tool_cfg.get("allowed_roles", []),
            )

        logger.info(f"[PermissionManager] 已加载 {len(self._permissions)} 个工具的权限配置")

    def register_tool(
        self,
        name: str,
        permission_level: str = "read",
        require_approval: bool = False,
        sandbox_required: bool = False,
        **kwargs,
    ) -> None:
        """动态注册工具权限（用于代码中注册的工具）"""
        self._permissions[name] = ToolPermissionConfig(
            name=name,
            permission_level=permission_level,
            require_approval=require_approval,
            sandbox_required=sandbox_required,
            **kwargs,
        )

    def get(self, tool_name: str) -> ToolPermissionConfig | None:
        """获取工具权限配置"""
        return self._permissions.get(tool_name)

    def check(
        self,
        tool_name: str,
        user_roles: list[str] | None = None,
    ) -> tuple[bool, str]:
        """检查用户是否有权限使用指定工具

        Args:
            tool_name: 工具名
            user_roles: 用户角色列表

        Returns:
            (是否允许, 原因说明)
        """
        user_roles = user_roles or ["viewer"]

        # 获取权限配置
        perm = self._permissions.get(tool_name)
        if perm is None:
            return True, "no_config"  # 未配置的工具默认允许

        # 检查是否启用
        if not perm.enabled:
            return False, f"工具 '{tool_name}' 已被禁用"

        # 检查角色白名单
        if perm.allowed_roles and not any(r in perm.allowed_roles for r in user_roles):
            return False, (f"工具 '{tool_name}' 仅限以下角色使用: {perm.allowed_roles}")

        # 根据权限级别检查
        level = perm.permission_level
        max_role_level = max(
            (UserRole.get_level(r) for r in user_roles),
            default=0,
        )

        if level == "read":
            return True, "read_auto_approved"
        elif level == "write":
            if max_role_level >= UserRole.get_level("editor"):
                return True, "write_approved"
            return False, f"工具 '{tool_name}' 需要 editor 或更高权限（write 操作）"
        elif level == "execute":
            if max_role_level >= UserRole.get_level("admin"):
                return True, "execute_approved"
            return False, f"工具 '{tool_name}' 需要 admin 权限（execute 操作）"

        return True, "default_allowed"

    def needs_approval(self, tool_name: str) -> bool:
        """检查工具是否需要人工审批"""
        perm = self._permissions.get(tool_name)
        if perm is None:
            return False
        return perm.require_approval

    def needs_sandbox(self, tool_name: str) -> bool:
        """检查工具是否需要沙箱执行"""
        perm = self._permissions.get(tool_name)
        if perm is None:
            return False
        return perm.sandbox_required

    def get_timeout(self, tool_name: str) -> int:
        """获取工具超时时间"""
        perm = self._permissions.get(tool_name)
        if perm is None:
            return 60
        return perm.timeout_seconds

    def get_retry_count(self, tool_name: str) -> int:
        """获取工具重试次数"""
        perm = self._permissions.get(tool_name)
        if perm is None:
            return 2
        return perm.retry_count

    def list_permissions(self) -> dict[str, dict[str, Any]]:
        """列出所有工具权限配置"""
        return {
            name: {
                "permission_level": perm.permission_level,
                "require_approval": perm.require_approval,
                "sandbox_required": perm.sandbox_required,
                "enabled": perm.enabled,
                "allowed_roles": perm.allowed_roles or ["*"],
            }
            for name, perm in self._permissions.items()
        }

    def get_accessible_tools(self, user_roles: list[str]) -> list[str]:
        """获取用户可访问的工具列表"""
        accessible = []
        for name in self._permissions:
            allowed, _ = self.check(name, user_roles)
            if allowed:
                accessible.append(name)
        return accessible

    # ---- 兼容 ToolExecutor.check_permission 的接口 ----

    def check_permission(self, tool_name: str, user_roles: list[str]) -> bool:
        """兼容 ToolExecutor.check_permission 的调用方式"""
        allowed, _ = self.check(tool_name, user_roles)
        return allowed
