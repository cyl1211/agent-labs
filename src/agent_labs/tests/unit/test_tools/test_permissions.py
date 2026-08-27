"""
Unit tests for tool and skill permissions
"""

import pytest

from agent_labs.skills.permissions import SkillPermissionManager
from agent_labs.tools.permissions import (
    ToolPermissionManager,
    UserRole,
)


class TestUserRole:
    def test_admin_is_highest(self):
        assert UserRole.get_level("admin") > UserRole.get_level("editor")
        assert UserRole.get_level("admin") > UserRole.get_level("viewer")

    def test_editor_and_developer_equal(self):
        assert UserRole.get_level("editor") == UserRole.get_level("developer")

    def test_viewer_is_valid(self):
        assert UserRole.is_valid("viewer")

    def test_unknown_role(self):
        assert not UserRole.is_valid("superuser")
        assert UserRole.get_level("superuser") == 0


class TestToolPermissionManager:
    @pytest.fixture
    def manager(self):
        mgr = ToolPermissionManager()
        mgr.register_tool("read_tool", permission_level="read")
        mgr.register_tool("write_tool", permission_level="write", require_approval=True)
        mgr.register_tool("exec_tool", permission_level="execute", sandbox_required=True)
        mgr.register_tool("disabled_tool", permission_level="read", enabled=False)
        return mgr

    def test_read_access_for_viewer(self, manager):
        allowed, reason = manager.check("read_tool", ["viewer"])
        assert allowed
        assert reason == "read_auto_approved"

    def test_write_denied_for_viewer(self, manager):
        allowed, reason = manager.check("write_tool", ["viewer"])
        assert not allowed
        assert "write" in reason.lower()

    def test_write_allowed_for_editor(self, manager):
        allowed, _ = manager.check("write_tool", ["editor"])
        assert allowed

    def test_execute_denied_for_editor(self, manager):
        allowed, reason = manager.check("exec_tool", ["editor"])
        assert not allowed

    def test_execute_allowed_for_admin(self, manager):
        allowed, _ = manager.check("exec_tool", ["admin"])
        assert allowed

    def test_disabled_tool_denied(self, manager):
        allowed, reason = manager.check("disabled_tool", ["admin"])
        assert not allowed
        assert "禁用" in reason

    def test_unregistered_tool_allowed(self, manager):
        allowed, reason = manager.check("unknown_tool", ["viewer"])
        assert allowed
        assert reason == "no_config"

    def test_needs_approval(self, manager):
        assert not manager.needs_approval("read_tool")
        assert manager.needs_approval("write_tool")

    def test_needs_sandbox(self, manager):
        assert not manager.needs_sandbox("read_tool")
        assert manager.needs_sandbox("exec_tool")

    def test_get_accessible_tools(self, manager):
        viewer_tools = manager.get_accessible_tools(["viewer"])
        assert "read_tool" in viewer_tools
        assert "write_tool" not in viewer_tools

        admin_tools = manager.get_accessible_tools(["admin"])
        assert "read_tool" in admin_tools
        assert "write_tool" in admin_tools
        assert "exec_tool" in admin_tools
        assert "disabled_tool" not in admin_tools

    def test_load_from_config(self):
        config = {
            "tools": [
                {
                    "name": "read_file",
                    "permission_level": "read",
                    "require_approval": False,
                    "enabled": True,
                    "timeout_seconds": 30,
                    "retry_count": 2,
                },
                {
                    "name": "write_file",
                    "permission_level": "write",
                    "require_approval": True,
                    "enabled": True,
                },
            ]
        }
        manager = ToolPermissionManager()
        manager.load_from_config(config)
        assert manager.get("read_file") is not None
        assert manager.get("write_file") is not None
        assert manager.get_timeout("read_file") == 30
        assert manager.get_retry_count("read_file") == 2

    def test_compat_check_permission(self, manager):
        assert manager.check_permission("read_tool", ["viewer"])
        assert not manager.check_permission("exec_tool", ["viewer"])


class TestSkillPermissionManager:
    @pytest.fixture
    def tool_perm(self):
        mgr = ToolPermissionManager()
        mgr.register_tool("read_file", permission_level="read")
        mgr.register_tool("write_file", permission_level="write", require_approval=True)
        mgr.register_tool("web_search", permission_level="read")
        mgr.register_tool("execute_command", permission_level="execute")
        return mgr

    @pytest.fixture
    def skill_perm(self, tool_perm):
        mgr = SkillPermissionManager(tool_perm)
        mgr.register_skill(
            "代码分析",
            required_tools=["read_file", "web_search"],
            require_approval=False,
        )
        mgr.register_skill(
            "代码重构",
            required_tools=["read_file", "write_file"],
        )
        return mgr

    def test_code_analysis_for_viewer(self, skill_perm):
        allowed, _ = skill_perm.check("代码分析", ["viewer"])
        assert allowed

    def test_code_refactor_denied_for_viewer(self, skill_perm):
        # 代码重构需要 write_file（write 权限），viewer 无权使用
        allowed, reason = skill_perm.check("代码重构", ["viewer"])
        assert not allowed

    def test_code_refactor_allowed_for_editor(self, skill_perm):
        allowed, _ = skill_perm.check("代码重构", ["editor"])
        assert allowed

    def test_needs_approval(self, skill_perm):
        # 代码分析不需要审批（read_file + web_search 都不需要）
        assert not skill_perm.needs_approval("代码分析")
        # 代码重构需要审批（write_file 需要审批）
        assert skill_perm.needs_approval("代码重构")

    def test_unregistered_skill_allowed(self, skill_perm):
        allowed, reason = skill_perm.check("未知技能", ["viewer"])
        assert allowed
        assert reason == "no_config"

    def test_get_accessible_skills(self, skill_perm):
        viewer_skills = skill_perm.get_accessible_skills(["viewer"])
        assert "代码分析" in viewer_skills
        assert "代码重构" not in viewer_skills

        editor_skills = skill_perm.get_accessible_skills(["editor"])
        assert "代码分析" in editor_skills
        assert "代码重构" in editor_skills

    def test_infer_permission_level(self, skill_perm):
        # 注册一个需要 execute 权限工具的技能
        skill_perm.register_skill("系统管理", required_tools=["execute_command"])
        allowed, _ = skill_perm.check("系统管理", ["editor"])
        assert not allowed

        allowed, _ = skill_perm.check("系统管理", ["admin"])
        assert allowed
